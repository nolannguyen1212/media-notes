"""handle_script/handle_audio: the standalone audio feature's two job
kinds (docs/services/worker.md). Unlike every handler in dispatch.py,
neither has a media_id/workflow_id — on success each commits its result
straight through content's Complete* RPCs; on failure each calls content's
FailStandaloneAudioJob directly rather than publishing to
mn.processing.step.failed.v1, since there is no conductor workflow to
notify.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid

from deps import Deps
from errors import classify
from events import AudioJobCommand
from providers import gemini, tts

logger = logging.getLogger(__name__)


def _probe_duration_ms(mp3_bytes: bytes) -> int:
    with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
        tmp.write(mp3_bytes)
        tmp.flush()
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp.name],
            capture_output=True, check=False, timeout=30,
        )
    try:
        return round(float(result.stdout.decode().strip()) * 1000)
    except (ValueError, AttributeError):
        return 0


def handle_script(cmd: AudioJobCommand, deps: Deps) -> None:
    with deps.limits.for_step("standalone_script").acquire():
        script_text = gemini.draft_audio_script(cmd.input_text)
    deps.content.complete_script_draft(job_id=cmd.job_id, script_text=script_text)


def handle_audio(cmd: AudioJobCommand, deps: Deps) -> None:
    voice = cmd.voice or deps.tts_voice
    with deps.limits.for_step("standalone_audio").acquire():
        audio_bytes = tts.generate_audio_summary(cmd.input_text, voice)
        duration_ms = _probe_duration_ms(audio_bytes)

    object_key = f"standalone-audio/{cmd.job_id}/{uuid.uuid4()}.mp3"
    deps.objects.put_object(object_key, audio_bytes, content_type="audio/mpeg")

    deps.content.complete_standalone_audio(
        job_id=cmd.job_id, object_key=object_key, mime_type="audio/mpeg",
        duration_ms=duration_ms, voice=voice,
    )


_HANDLERS = {
    "script": handle_script,
    "audio": handle_audio,
}


def dispatch(cmd: AudioJobCommand, deps: Deps) -> None:
    """Routes cmd to its handler by kind and reports any failure straight
    to content — there is no mn.processing.step.failed.v1 equivalent for
    a job with no workflow to notify.
    """
    handler = _HANDLERS.get(cmd.kind)
    if handler is None:
        logger.error("no handler for audio job kind=%s, failing job=%s", cmd.kind, cmd.job_id)
        deps.content.fail_standalone_audio_job(job_id=cmd.job_id, error_code="unknown_kind")
        return

    try:
        handler(cmd, deps)
    except Exception as e:  # noqa: BLE001 - every exception must be classified and reported, not raised
        error_code, _retriable = classify(e)
        logger.warning("audio job kind=%s job=%s failed error_code=%s: %s", cmd.kind, cmd.job_id, error_code, e)
        deps.content.fail_standalone_audio_job(job_id=cmd.job_id, error_code=error_code)
        return

    logger.info("audio job kind=%s job=%s completed", cmd.kind, cmd.job_id)

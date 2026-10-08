"""handle_keywords: reads the committed transcript, runs Gemini, replaces
the stored keyword set through content.
"""

from __future__ import annotations

from deps import Deps
from events import StepCommand
from providers import gemini


def handle(cmd: StepCommand, deps: Deps) -> None:
    transcript = deps.content.get_transcript(cmd.media_id)

    with deps.limits.for_step(cmd.step).acquire():
        keywords = gemini.extract_keywords(transcript.segments, cmd.prompt_override)

    deps.content.store_keywords(
        idempotency_key=cmd.idempotency_key,
        media_id=cmd.media_id,
        workflow_id=cmd.workflow_id,
        attempt=cmd.attempt,
        keywords=keywords,
    )

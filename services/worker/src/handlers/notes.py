"""handle_notes: reads the committed transcript, runs Gemini, commits one
Markdown note document through content.
"""

from __future__ import annotations

from deps import Deps
from events import StepCommand
from providers import gemini

NOTE_FORMAT = "markdown"


def handle(cmd: StepCommand, deps: Deps) -> None:
    transcript = deps.content.get_transcript(cmd.media_id)

    with deps.limits.for_step(cmd.step).acquire():
        body = gemini.generate_notes(transcript.segments, cmd.prompt_override)

    deps.content.store_notes(
        idempotency_key=cmd.idempotency_key,
        media_id=cmd.media_id,
        workflow_id=cmd.workflow_id,
        attempt=cmd.attempt,
        format=NOTE_FORMAT,
        body=body,
    )

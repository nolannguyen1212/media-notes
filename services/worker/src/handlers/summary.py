"""handle_summary: reads the committed transcript, runs Gemini, commits a
structured summary through content.
"""

from __future__ import annotations

from clients.content_client import SummarySentence as ContentSentence
from deps import Deps
from events import StepCommand
from providers import gemini

SUMMARY_TYPE = "short"
PROMPT_VERSION = "v1"


def handle(cmd: StepCommand, deps: Deps) -> None:
    transcript = deps.content.get_transcript(cmd.media_id)

    with deps.limits.for_step(cmd.step).acquire():
        text, sentences = gemini.summarize(transcript.segments, cmd.prompt_override)

    deps.content.store_summary(
        idempotency_key=cmd.idempotency_key,
        media_id=cmd.media_id,
        workflow_id=cmd.workflow_id,
        attempt=cmd.attempt,
        summary_type=SUMMARY_TYPE,
        text=text,
        model=deps.gemini_model,
        prompt_version=PROMPT_VERSION,
        sentences=[
            ContentSentence(sentence_index=s.sentence_index, text=s.text, cited_segment_indexes=s.cited_segment_indexes)
            for s in sentences
        ],
    )

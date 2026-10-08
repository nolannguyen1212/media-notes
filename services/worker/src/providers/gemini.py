"""Gemini enrichment: summary, keywords, keypoints, notes. Adapted from
apps/worker/src/summarizer.py and extractor.py, reshaped to content.proto's
structured output (sentence-level citations, segment-ranged keypoints)
instead of the v1 API's plain-text/ref-index shape.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Protocol

from google import genai
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class Segment(Protocol):
    """Structural type for a transcript segment: satisfied by both
    providers.whisper.Segment (transcribe's own output) and
    clients.content_client.TranscriptSegment (read back from content for
    every later enrichment step) without either module depending on the
    other.
    """

    segment_index: int
    text: str

MAX_RETRIES = 3

_make_client: Callable[[], genai.Client] | None = None
_model_name = "gemini-2.5-flash-lite"


def configure(make_client: Callable[[], genai.Client], model_name: str) -> None:
    global _make_client, _model_name
    _make_client = make_client
    _model_name = model_name


def _transcript_prompt_text(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.segment_index}] {s.text}" for s in segments)


def _custom_instructions_block(custom_instructions: str | None) -> str:
    """Formats the caller's saved system prompt (Settings > Prompts) as a
    prompt section, or "" when none was saved. Placed ahead of the
    transcript so it augments, rather than overrides, the structural/
    format instructions already in each prompt.
    """
    if not custom_instructions:
        return ""
    return f"Additional instructions from the user:\n{custom_instructions}\n\n"


def _call(prompt: str) -> str:
    if _make_client is None:
        raise RuntimeError("Gemini client not configured")
    client = _make_client()
    response = client.models.generate_content(model=_model_name, contents=prompt)
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _call_with_retry(prompt: str, parse: Callable[[str], object]) -> object:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return parse(_call(prompt))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = e
            logger.warning("gemini call attempt %d failed: %s", attempt, e)
    raise RuntimeError(f"gemini call failed after {MAX_RETRIES} attempts: {last_error}")


class _SentenceRef(BaseModel):
    sentence_index: int
    text: str
    cited_segment_indexes: list[int] = []


class _SummaryResponse(BaseModel):
    sentences: list[_SentenceRef]


def summarize(
    segments: list[Segment], custom_instructions: str | None = None
) -> tuple[str, list[_SentenceRef]]:
    """Returns (full_summary_text, sentences), each sentence citing the
    transcript segment indexes it draws from — content.proto's
    SummarySentence shape.
    """
    prompt = (
        "You are a summarization assistant. Given the following transcript, "
        "numbered by segment, produce a JSON object with a single key "
        '"sentences": an array of objects, each with "sentence_index" '
        "(0-based), \"text\" (one sentence of the summary), and "
        '"cited_segment_indexes" (the transcript segment indexes that '
        "sentence is drawn from).\n\n"
        f"{_custom_instructions_block(custom_instructions)}"
        f"Transcript:\n{_transcript_prompt_text(segments)}\n\n"
        "Respond with valid JSON only, no markdown."
    )

    def parse(raw: str) -> _SummaryResponse:
        return _SummaryResponse.model_validate(json.loads(raw))

    parsed: _SummaryResponse = _call_with_retry(prompt, parse)  # type: ignore[assignment]
    full_text = " ".join(s.text for s in parsed.sentences)
    return full_text, parsed.sentences


class _Keyword(BaseModel):
    keyword: str
    score: float


def extract_keywords(
    segments: list[Segment], custom_instructions: str | None = None
) -> list[tuple[str, float, int]]:
    """Returns up to 10 (keyword, score, position) tuples, ranked by
    Gemini's own relevance score (content.proto's Keyword shape).
    """
    prompt = (
        "Extract up to 10 keywords from the following transcript, each "
        "with a relevance score between 0 and 1. Return a JSON array of "
        'objects: [{"keyword": "...", "score": 0.0}, ...], most relevant '
        "first. No markdown.\n\n"
        f"{_custom_instructions_block(custom_instructions)}"
        f"Transcript:\n{_transcript_prompt_text(segments)}"
    )

    def parse(raw: str) -> list[_Keyword]:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("expected a JSON array")
        return [_Keyword.model_validate(item) for item in data[:10]]

    keywords: list[_Keyword] = _call_with_retry(prompt, parse)  # type: ignore[assignment]
    return [(k.keyword, k.score, i) for i, k in enumerate(keywords)]


class _Keypoint(BaseModel):
    text: str
    start_segment: int
    end_segment: int


def extract_keypoints(
    segments: list[Segment], custom_instructions: str | None = None
) -> list[tuple[int, str, int, int]]:
    """Returns 3-5 (point_index, text, start_segment, end_segment)
    tuples, each keypoint's segment range drawn from the numbered
    transcript (content.proto's Keypoint shape)."""
    prompt = (
        "Identify 3 to 5 keypoints from the following numbered transcript "
        "segments. Return a JSON array of objects: "
        '[{"text": "...", "start_segment": 0, "end_segment": 2}, ...], '
        "where start_segment/end_segment are the transcript segment "
        "indexes the keypoint summarizes. No markdown.\n\n"
        f"{_custom_instructions_block(custom_instructions)}"
        f"Transcript:\n{_transcript_prompt_text(segments)}"
    )

    def parse(raw: str) -> list[_Keypoint]:
        data = json.loads(raw)
        if not isinstance(data, list) or not (1 <= len(data) <= 8):
            raise ValueError(f"expected 1-8 keypoints, got {data!r}")
        return [_Keypoint.model_validate(item) for item in data]

    keypoints: list[_Keypoint] = _call_with_retry(prompt, parse)  # type: ignore[assignment]
    return [(i, kp.text, kp.start_segment, kp.end_segment) for i, kp in enumerate(keypoints)]


def draft_audio_script(description: str) -> str:
    """Drafts narration text from a loose description, for the standalone
    audio feature's "chat with AI" mode (docs/services/worker.md). Plain
    prose in, plain prose out — no transcript, no JSON structure, unlike
    every other Gemini call in this module.
    """
    prompt = (
        "You are a scriptwriting assistant. Write a short narration script "
        "(a few sentences to a short paragraph, suitable for text-to-speech) "
        "based on the following description. Respond with the narration "
        "text only — no markdown, no preamble, no quotation marks.\n\n"
        f"Description:\n{description}"
    )
    return _call(prompt)


class _Notes(BaseModel):
    notes: str


def generate_notes(segments: list[Segment], custom_instructions: str | None = None) -> str:
    """Returns Markdown notes body (content.proto's Note.body)."""
    prompt = (
        "Generate detailed notes from the following transcript in Markdown "
        'format. Return a JSON object {"notes": "..."} containing the '
        "markdown string. No markdown code fences around the JSON itself.\n\n"
        f"{_custom_instructions_block(custom_instructions)}"
        f"Transcript:\n{_transcript_prompt_text(segments)}"
    )

    def parse(raw: str) -> _Notes:
        return _Notes.model_validate(json.loads(raw))

    parsed: _Notes = _call_with_retry(prompt, parse)  # type: ignore[assignment]
    return parsed.notes

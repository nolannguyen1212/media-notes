"""Unit tests for providers/llm.py's JSON parsing/retry/fallback logic
against fake adapters — no live provider calls, matching the project-wide
"no live provider calls in unit tests" rule.
"""

import json
from dataclasses import dataclass

import pytest

from providers import llm


@dataclass
class FakeSegment:
    segment_index: int
    text: str


SEGMENTS = [FakeSegment(0, "hello"), FakeSegment(1, "world")]


class FakeAdapter:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate(self, prompt: str) -> str:
        return self._responses.pop(0)


class FailingAdapter:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("provider unavailable")


def _configure(payload: str | list[str]) -> None:
    responses = [payload] if isinstance(payload, str) else payload
    llm.configure([("fake", FakeAdapter(responses))])


@pytest.fixture(autouse=True)
def _reset_llm_config():
    yield
    llm._providers = []  # noqa: SLF001 - test isolation


def test_summarize_parses_sentences_with_citations():
    payload = json.dumps({"sentences": [
        {"sentence_index": 0, "text": "It happened.", "cited_segment_indexes": [0]},
        {"sentence_index": 1, "text": "Then more.", "cited_segment_indexes": [1]},
    ]})
    _configure(payload)

    text, sentences = llm.summarize(SEGMENTS)

    assert text == "It happened. Then more."
    assert len(sentences) == 2
    assert sentences[0].cited_segment_indexes == [0]


def test_summarize_strips_markdown_code_fences():
    payload = "```json\n" + json.dumps({"sentences": [{"sentence_index": 0, "text": "x", "cited_segment_indexes": []}]}) + "\n```"
    _configure(payload)

    text, _ = llm.summarize(SEGMENTS)

    assert text == "x"


def test_summarize_retries_on_invalid_json_then_succeeds():
    good = json.dumps({"sentences": [{"sentence_index": 0, "text": "ok", "cited_segment_indexes": []}]})
    _configure(["not json", good])

    text, _ = llm.summarize(SEGMENTS)

    assert text == "ok"


def test_summarize_raises_after_exhausting_retries():
    _configure(["not json", "still not json", "nope"])

    with pytest.raises(RuntimeError):
        llm.summarize(SEGMENTS)


def test_extract_keywords_orders_by_response_and_assigns_position():
    payload = json.dumps([{"keyword": "alpha", "score": 0.9}, {"keyword": "beta", "score": 0.4}])
    _configure(payload)

    keywords = llm.extract_keywords(SEGMENTS)

    assert keywords == [("alpha", 0.9, 0), ("beta", 0.4, 1)]


def test_extract_keypoints_carries_segment_range():
    payload = json.dumps([{"text": "kp", "start_segment": 0, "end_segment": 1}])
    _configure(payload)

    keypoints = llm.extract_keypoints(SEGMENTS)

    assert keypoints == [(0, "kp", 0, 1)]


def test_generate_notes_returns_markdown_body():
    payload = json.dumps({"notes": "# Notes\n- one"})
    _configure(payload)

    notes = llm.generate_notes(SEGMENTS)

    assert notes == "# Notes\n- one"


def test_falls_back_to_next_provider_when_primary_raises():
    payload = json.dumps({"notes": "# ok"})
    llm.configure([("primary", FailingAdapter()), ("fallback", FakeAdapter([payload]))])

    notes = llm.generate_notes(SEGMENTS)

    assert notes == "# ok"


def test_raises_when_every_provider_fails():
    llm.configure([("a", FailingAdapter()), ("b", FailingAdapter())])

    with pytest.raises(RuntimeError):
        llm.generate_notes(SEGMENTS)

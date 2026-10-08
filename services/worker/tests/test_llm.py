"""Unit tests for providers/llm.py's JSON parsing/retry logic against a
fake client — no live Groq API calls, matching the project-wide "no live
provider calls in unit tests" rule.
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


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def create(self, model, messages):
        return FakeResponse(self._responses.pop(0))


class FakeChat:
    def __init__(self, responses: list[str]) -> None:
        self.completions = FakeCompletions(responses)


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.chat = FakeChat(responses)


@pytest.fixture(autouse=True)
def _reset_llm_config():
    yield
    llm._make_client = None  # noqa: SLF001 - test isolation


def test_summarize_parses_sentences_with_citations():
    payload = json.dumps({"sentences": [
        {"sentence_index": 0, "text": "It happened.", "cited_segment_indexes": [0]},
        {"sentence_index": 1, "text": "Then more.", "cited_segment_indexes": [1]},
    ]})
    llm.configure(lambda: FakeClient([payload]), "test-model")

    text, sentences = llm.summarize(SEGMENTS)

    assert text == "It happened. Then more."
    assert len(sentences) == 2
    assert sentences[0].cited_segment_indexes == [0]


def test_summarize_strips_markdown_code_fences():
    payload = "```json\n" + json.dumps({"sentences": [{"sentence_index": 0, "text": "x", "cited_segment_indexes": []}]}) + "\n```"
    llm.configure(lambda: FakeClient([payload]), "test-model")

    text, _ = llm.summarize(SEGMENTS)

    assert text == "x"


def test_summarize_retries_on_invalid_json_then_succeeds():
    good = json.dumps({"sentences": [{"sentence_index": 0, "text": "ok", "cited_segment_indexes": []}]})
    # _make_client is called fresh on every _call(); reuse one FakeClient
    # instance so its response queue is actually consumed across retries
    # instead of being reset each call.
    client = FakeClient(["not json", good])
    llm.configure(lambda: client, "test-model")

    text, _ = llm.summarize(SEGMENTS)

    assert text == "ok"


def test_summarize_raises_after_exhausting_retries():
    llm.configure(lambda: FakeClient(["not json", "still not json", "nope"]), "test-model")

    with pytest.raises(RuntimeError):
        llm.summarize(SEGMENTS)


def test_extract_keywords_orders_by_response_and_assigns_position():
    payload = json.dumps([{"keyword": "alpha", "score": 0.9}, {"keyword": "beta", "score": 0.4}])
    llm.configure(lambda: FakeClient([payload]), "test-model")

    keywords = llm.extract_keywords(SEGMENTS)

    assert keywords == [("alpha", 0.9, 0), ("beta", 0.4, 1)]


def test_extract_keypoints_carries_segment_range():
    payload = json.dumps([{"text": "kp", "start_segment": 0, "end_segment": 1}])
    llm.configure(lambda: FakeClient([payload]), "test-model")

    keypoints = llm.extract_keypoints(SEGMENTS)

    assert keypoints == [(0, "kp", 0, 1)]


def test_generate_notes_returns_markdown_body():
    payload = json.dumps({"notes": "# Notes\n- one"})
    llm.configure(lambda: FakeClient([payload]), "test-model")

    notes = llm.generate_notes(SEGMENTS)

    assert notes == "# Notes\n- one"

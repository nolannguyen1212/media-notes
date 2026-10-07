"""Kafka wiring: consumes mn.processing.step.requested.v1 and produces
mn.processing.step.failed.v1, per ADR 0003 and docs/services/worker.md.
Topic and consumer-group names must match conductor's
internal/events/topics.go exactly.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from kafka import KafkaConsumer, KafkaProducer

logger = logging.getLogger(__name__)

STEP_REQUESTED_TOPIC = "mn.processing.step.requested.v1"
STEP_FAILED_TOPIC = "mn.processing.step.failed.v1"
CONSUMER_GROUP = "conductor-worker-steps"

# AUDIO_JOB_REQUESTED_TOPIC is content's standalone-audio-job topic
# (content/internal/events.AudioJobRequestedTopic) — a media-independent
# script-draft or audio-generation request, never routed through
# conductor. Consumed by the same worker pool, on the same consumer
# group, as mn.processing.step.requested.v1.
AUDIO_JOB_REQUESTED_TOPIC = "mn.audio.job.requested.v1"


@dataclass
class StepCommand:
    """Decoded mn.processing.step.requested.v1 payload — conductor's
    internal/store.dispatchStep payload shape.
    """

    event_id: str
    media_id: str
    workflow_id: str
    step_id: str
    step: str
    attempt: int
    idempotency_key: str
    # Only present for a summary_audio command whose workflow selected a
    # non-default voice (conductor's dispatchStep omits this field
    # otherwise) — see handlers/summary_audio.py.
    voice: str | None = None
    # Only present when the caller saved a custom system prompt for this
    # step's section (conductor's dispatchStep/promptOverrideForStep omits
    # this field otherwise) — appended to the LLM prompt in providers/gemini.py.
    prompt_override: str | None = None


def parse_step_command(raw: bytes) -> StepCommand:
    data = json.loads(raw)
    return StepCommand(
        event_id=data["event_id"],
        media_id=data["media_id"],
        workflow_id=data["workflow_id"],
        step_id=data["step_id"],
        step=data["step"],
        attempt=int(data["attempt"]),
        idempotency_key=data["idempotency_key"],
        voice=data.get("voice"),
        prompt_override=data.get("prompt_override"),
    )


@dataclass
class AudioJobCommand:
    """Decoded mn.audio.job.requested.v1 payload —
    content/internal/store.AudioJobRepository.create's outbox payload
    shape. Has no media_id/workflow_id: standalone audio jobs never touch
    conductor.
    """

    event_id: str
    job_id: str
    kind: str
    input_text: str
    voice: str | None = None


def parse_audio_job_command(raw: bytes) -> AudioJobCommand:
    data = json.loads(raw)
    return AudioJobCommand(
        event_id=data["event_id"],
        job_id=data["job_id"],
        kind=data["kind"],
        input_text=data["input_text"],
        voice=data.get("voice") or None,
    )


def new_consumer(brokers: list[str]) -> KafkaConsumer:
    # transcribe blocks the main loop for the whole Whisper decode (can run
    # well past kafka-python's 5min default), so max_poll_interval_ms must
    # cover the slowest single step or the group evicts us mid-job and the
    # eventual commit() raises CommitFailedError.
    return KafkaConsumer(
        STEP_REQUESTED_TOPIC,
        AUDIO_JOB_REQUESTED_TOPIC,
        bootstrap_servers=brokers,
        group_id=CONSUMER_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_interval_ms=1_800_000,
    )


def new_producer(brokers: list[str]) -> KafkaProducer:
    return KafkaProducer(bootstrap_servers=brokers)


def publish_step_failed(
    producer: KafkaProducer,
    *,
    media_id: str,
    workflow_id: str,
    step: str,
    attempt: int,
    error_code: str,
    retriable: bool,
) -> None:
    """Publishes classified failure metadata only — never text, media
    bytes, or a provider response (worker.md, ADR 0003).
    """
    payload = {
        "event_id": str(uuid.uuid4()),
        "media_id": media_id,
        "workflow_id": workflow_id,
        "step": step,
        "attempt": attempt,
        "error_code": error_code,
        "retriable": retriable,
    }
    producer.send(STEP_FAILED_TOPIC, key=media_id.encode(), value=json.dumps(payload).encode())
    producer.flush()
    logger.info("published step failed event=%s attempt=%d error_code=%s retriable=%s",
                step, attempt, error_code, retriable)


def run_consumer(consumer: KafkaConsumer, handle, should_stop, *, poll_timeout_ms: int = 1000) -> None:
    """Polls until should_stop() reports true, checked after every poll
    cycle — including one that returned no messages. `for message in
    consumer` (plain iteration) blocks indefinitely when idle and never
    re-checks a stop signal, which left SIGTERM unable to end the process
    until the next message arrived; polling with a timeout fixes that.
    Commits the offset only after handle succeeds — worker.md: "Commit
    the Kafka offset only after that call succeeds."
    """
    while not should_stop():
        records = consumer.poll(timeout_ms=poll_timeout_ms)
        for messages in records.values():
            for message in messages:
                handle(message)
                consumer.commit()
                if should_stop():
                    return

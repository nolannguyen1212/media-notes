"""Command main runs conductor-worker: consumes
mn.processing.step.requested.v1, dispatches by step kind, runs the
matching provider, commits durable results through media/content, and
reports classified failures. Stateless (docs/services/worker.md): no
database of its own, deployed as a Kafka consumer-group pool.
"""

from __future__ import annotations

import logging
import signal

from dotenv import load_dotenv
from google import genai

import dispatch
import events
from clients.content_client import ContentClient
from clients.media_client import MediaClient
from clients.objectstore import ObjectStore
from config import load_config
from deps import Deps
from handlers import audio_job
from limits import build_limits
from providers import gemini, whisper

logger = logging.getLogger(__name__)

_running = True


def _handle_sigterm(signum: int, frame: object) -> None:
    global _running
    logger.info("SIGTERM received, finishing the current message then stopping")
    _running = False


def _make_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def main() -> None:
    load_dotenv()
    cfg = load_config()

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logger.info("loading whisper model=%s", cfg.whisper_model)
    whisper.load_model(cfg.whisper_model)

    gemini.configure(lambda: _make_gemini_client(cfg.google_api_key), cfg.gemini_model)

    media_client = MediaClient(cfg.media_grpc_addr)
    content_client = ContentClient(cfg.content_grpc_addr)
    object_store = ObjectStore(
        endpoint=cfg.minio_endpoint, access_key=cfg.minio_access_key, secret_key=cfg.minio_secret_key,
        secure=cfg.minio_use_ssl, bucket=cfg.minio_media_bucket,
    )
    deps = Deps(
        media=media_client, content=content_client, objects=object_store,
        limits=build_limits(cfg), gemini_model=cfg.gemini_model, tts_voice=cfg.tts_voice,
    )

    consumer = events.new_consumer(cfg.kafka_brokers)
    producer = events.new_producer(cfg.kafka_brokers)

    def handle(message) -> None:
        if message.topic == events.AUDIO_JOB_REQUESTED_TOPIC:
            try:
                audio_cmd = events.parse_audio_job_command(message.value)
            except (KeyError, ValueError, TypeError) as e:
                logger.error("undecodable audio job command, skipping: %s", e)
                return
            audio_job.dispatch(audio_cmd, deps)
            return

        try:
            cmd = events.parse_step_command(message.value)
        except (KeyError, ValueError, TypeError) as e:
            logger.error("undecodable step command, skipping: %s", e)
            return

        outcome = dispatch.dispatch(cmd, deps)
        if not outcome.ok:
            events.publish_step_failed(
                producer,
                media_id=cmd.media_id, workflow_id=cmd.workflow_id, step=cmd.step, attempt=cmd.attempt,
                error_code=outcome.error_code, retriable=outcome.retriable,
            )

    try:
        events.run_consumer(consumer, handle, should_stop=lambda: not _running)
    finally:
        consumer.close()
        producer.close()
        media_client.close()
        content_client.close()

    logger.info("worker stopped cleanly")


if __name__ == "__main__":
    main()

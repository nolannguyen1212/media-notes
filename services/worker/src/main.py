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
from openai import OpenAI

import dispatch
import events
from clients.content_client import ContentClient
from clients.media_client import MediaClient
from clients.objectstore import ObjectStore
from config import Config, load_config
from deps import Deps
from handlers import audio_job
from limits import build_limits
from providers import llm, whisper

logger = logging.getLogger(__name__)

_running = True


def _handle_sigterm(signum: int, frame: object) -> None:
    global _running
    logger.info("SIGTERM received, finishing the current message then stopping")
    _running = False


class _RotatingAdapter:
    def __init__(self, client: OpenAI, models: list[str]) -> None:
        self._client = client
        self._models = models

    def generate(self, prompt: str) -> str:
        last_error: Exception | None = None
        for model in self._models:
            try:
                response = self._client.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
                if not text or not text.strip():
                    raise ValueError("empty response")
                return text
            except Exception as e:  # noqa: BLE001
                logger.warning("openrouter model %s failed, trying next: %s", model, e)
                last_error = e
        raise RuntimeError(f"all openrouter models failed: {last_error}")


def _build_llm_providers(cfg: Config) -> list[tuple[str, llm.Adapter]]:
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=cfg.openrouter_api_key)
    return [("openrouter", _RotatingAdapter(client, cfg.openrouter_models))]


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

    llm.configure(_build_llm_providers(cfg))

    media_client = MediaClient(cfg.media_grpc_addr)
    content_client = ContentClient(cfg.content_grpc_addr)
    object_store = ObjectStore(
        endpoint=cfg.minio_endpoint, access_key=cfg.minio_access_key, secret_key=cfg.minio_secret_key,
        secure=cfg.minio_use_ssl, bucket=cfg.minio_media_bucket,
    )
    deps = Deps(
        media=media_client, content=content_client, objects=object_store,
        limits=build_limits(cfg), llm_model=cfg.openrouter_models[0], tts_voice=cfg.tts_voice,
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

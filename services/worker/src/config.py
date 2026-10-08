"""Runtime configuration for conductor-worker, loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split_csv(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


@dataclass(frozen=True)
class Config:
    kafka_brokers: list[str]

    media_grpc_addr: str
    content_grpc_addr: str

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_use_ssl: bool
    minio_media_bucket: str

    google_api_key: str
    gemini_model: str
    whisper_model: str
    tts_voice: str

    # Per-step-kind concurrency bound (worker.md: "acquires a bounded
    # capability semaphore"). ADR 0007's aggregate cross-replica quota
    # reservation is conductor's job, not implemented yet — this is only
    # this process's local limit.
    max_concurrent_whisper: int
    max_concurrent_gemini: int
    max_concurrent_tts: int
    max_concurrent_thumbnail: int

    step_timeout_seconds: int

    log_level: str = field(default="INFO")


def load_config() -> Config:
    return Config(
        kafka_brokers=_split_csv(os.environ.get("KAFKA_BROKERS", "localhost:9092")),
        media_grpc_addr=os.environ.get("WORKER_MEDIA_GRPC_ADDR", "localhost:19095"),
        content_grpc_addr=os.environ.get("WORKER_CONTENT_GRPC_ADDR", "localhost:9095"),
        minio_endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9002"),
        minio_access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        minio_use_ssl=os.environ.get("MINIO_USE_SSL", "false").lower() == "true",
        minio_media_bucket=os.environ.get("MINIO_MEDIA_BUCKET", "media"),
        google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        whisper_model=os.environ.get("WHISPER_MODEL", "base"),
        tts_voice=os.environ.get("WORKER_TTS_VOICE", "en-US-AriaNeural"),
        max_concurrent_whisper=int(os.environ.get("WORKER_MAX_CONCURRENT_WHISPER", "1")),
        max_concurrent_gemini=int(os.environ.get("WORKER_MAX_CONCURRENT_GEMINI", "4")),
        max_concurrent_tts=int(os.environ.get("WORKER_MAX_CONCURRENT_TTS", "2")),
        max_concurrent_thumbnail=int(os.environ.get("WORKER_MAX_CONCURRENT_THUMBNAIL", "2")),
        step_timeout_seconds=int(os.environ.get("WORKER_STEP_TIMEOUT_SECONDS", "600")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

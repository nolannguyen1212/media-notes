"""Per-step-kind local admission: a bounded capability semaphore and
timeout, per docs/services/worker.md ("acquires a bounded capability
semaphore, applies a deadline"). This is only this process's local bound;
ADR 0007's aggregate cross-replica provider quota reservation belongs to
conductor and is not implemented yet.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from config import Config


class CapacityUnavailable(Exception):
    """Raised when a step cannot acquire its semaphore before its
    deadline. Classified as retriable in dispatch.py: the workflow should
    try again once local capacity frees up.
    """


@dataclass
class StepLimiter:
    semaphore: threading.Semaphore
    timeout_seconds: int

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if not self.semaphore.acquire(timeout=self.timeout_seconds):
            raise CapacityUnavailable("local capacity semaphore acquisition timed out")
        try:
            yield
        finally:
            self.semaphore.release()


@dataclass
class Limits:
    whisper: StepLimiter
    gemini: StepLimiter
    tts: StepLimiter
    thumbnail: StepLimiter

    def for_step(self, step: str) -> StepLimiter:
        return _STEP_TO_LIMITER[step](self)


_STEP_TO_LIMITER = {
    "transcribe": lambda limits: limits.whisper,
    "summary": lambda limits: limits.gemini,
    "keywords": lambda limits: limits.gemini,
    "keypoints": lambda limits: limits.gemini,
    "notes": lambda limits: limits.gemini,
    "summary_audio": lambda limits: limits.tts,
    "generate_thumbnail": lambda limits: limits.thumbnail,
    # Standalone audio jobs (docs/services/worker.md) share the same
    # Gemini/TTS capacity bounds as their media-bound counterparts —
    # there is no separate provider quota to size for them.
    "standalone_script": lambda limits: limits.gemini,
    "standalone_audio": lambda limits: limits.tts,
}


def build_limits(cfg: Config) -> Limits:
    return Limits(
        whisper=StepLimiter(threading.Semaphore(cfg.max_concurrent_whisper), cfg.step_timeout_seconds),
        gemini=StepLimiter(threading.Semaphore(cfg.max_concurrent_gemini), cfg.step_timeout_seconds),
        tts=StepLimiter(threading.Semaphore(cfg.max_concurrent_tts), cfg.step_timeout_seconds),
        thumbnail=StepLimiter(threading.Semaphore(cfg.max_concurrent_thumbnail), cfg.step_timeout_seconds),
    )

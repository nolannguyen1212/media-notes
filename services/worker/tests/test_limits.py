import threading

import pytest

from limits import CapacityUnavailable, Limits, StepLimiter, build_limits
from config import load_config


def test_acquire_releases_on_exit():
    limiter = StepLimiter(threading.Semaphore(1), timeout_seconds=1)
    with limiter.acquire():
        assert limiter.semaphore.acquire(blocking=False) is False
    assert limiter.semaphore.acquire(blocking=False) is True
    limiter.semaphore.release()


def test_acquire_times_out_when_capacity_exhausted():
    limiter = StepLimiter(threading.Semaphore(1), timeout_seconds=0)
    with limiter.acquire():
        with pytest.raises(CapacityUnavailable):
            with limiter.acquire():
                pass  # pragma: no cover - must never be entered


def test_for_step_maps_every_known_step_kind():
    limits = Limits(
        whisper=StepLimiter(threading.Semaphore(1), 1),
        gemini=StepLimiter(threading.Semaphore(1), 1),
        tts=StepLimiter(threading.Semaphore(1), 1),
        thumbnail=StepLimiter(threading.Semaphore(1), 1),
    )
    assert limits.for_step("transcribe") is limits.whisper
    assert limits.for_step("summary") is limits.gemini
    assert limits.for_step("keywords") is limits.gemini
    assert limits.for_step("keypoints") is limits.gemini
    assert limits.for_step("notes") is limits.gemini
    assert limits.for_step("summary_audio") is limits.tts
    assert limits.for_step("generate_thumbnail") is limits.thumbnail


def test_build_limits_uses_config_bounds(monkeypatch):
    monkeypatch.setenv("WORKER_MAX_CONCURRENT_WHISPER", "3")
    cfg = load_config()
    limits = build_limits(cfg)
    assert limits.whisper.semaphore._value == 3  # noqa: SLF001 - asserting the configured bound took effect

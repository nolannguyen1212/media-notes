"""Step failure classification: worker.md requires emitting "only
classified small metadata" to mn.processing.step.failed.v1. ADR 0007's
rule of thumb: provider 429/timeout/unavailable is retriable; auth,
invalid input, and safety rejection are terminal unless a step
explicitly says otherwise.
"""

from __future__ import annotations

import grpc

from limits import CapacityUnavailable


class StepError(Exception):
    """Base for a step handler's own classified failure. A provider
    adapter or step handler raises this directly when it already knows
    the right classification (e.g. a safety-filtered LLM response is
    terminal, not retriable)."""

    def __init__(self, error_code: str, retriable: bool, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.retriable = retriable


class RetriableStepError(StepError):
    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(error_code, True, message)


class TerminalStepError(StepError):
    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(error_code, False, message)


_RETRIABLE_GRPC_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.ABORTED,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.UNKNOWN,
}


def classify(exc: Exception) -> tuple[str, bool]:
    """Returns (error_code, retriable) for exc."""
    if isinstance(exc, StepError):
        return exc.error_code, exc.retriable
    if isinstance(exc, CapacityUnavailable):
        return "capacity_unavailable", True
    if isinstance(exc, grpc.RpcError):
        code = exc.code()
        return f"grpc_{code.name.lower()}", code in _RETRIABLE_GRPC_CODES
    if isinstance(exc, TimeoutError):
        return "timeout", True
    # Unclassified: default to retriable rather than silently DLQ-ing a
    # workflow over a bug we can't yet name — conductor's max-attempts
    # bound still applies, so this doesn't retry forever.
    return "internal_error", True

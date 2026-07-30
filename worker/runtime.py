"""Stoppable single-Worker polling runtime for the M1 deployment."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from worker.errors import WorkerError


@dataclass(frozen=True, slots=True)
class PollPolicy:
    """Fixed idle polling plus bounded retry backoff."""

    idle_seconds: float = 5.0
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.idle_seconds < 0 or self.initial_backoff_seconds <= 0:
            raise ValueError("poll intervals must be positive")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max backoff must be at least the initial backoff")


@dataclass(slots=True)
class RuntimeCounters:
    """Process-local counters that never contain tenant or media data."""

    claimed: int = 0
    idle: int = 0
    retryable_failures: int = 0


def run_forever(
    run_once: Callable[[], object | None],
    *,
    stop_event: Event,
    policy: PollPolicy,
    wait: Callable[[float], bool] | None = None,
) -> RuntimeCounters:
    """Poll until stopped, retrying only failures explicitly marked retryable."""

    wait_for_stop = wait or stop_event.wait
    counters = RuntimeCounters()
    backoff = policy.initial_backoff_seconds

    while not stop_event.is_set():
        try:
            result = run_once()
        except WorkerError as exc:
            if not exc.retryable:
                raise
            counters.retryable_failures += 1
            if wait_for_stop(backoff):
                break
            backoff = min(backoff * 2, policy.max_backoff_seconds)
            continue

        backoff = policy.initial_backoff_seconds
        if result is None:
            counters.idle += 1
            if wait_for_stop(policy.idle_seconds):
                break
        else:
            counters.claimed += 1

    return counters

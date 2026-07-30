from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from worker.errors import WorkerError, WorkerErrorCode
from worker.runtime import PollPolicy, run_forever


def _retryable_job_store_error() -> WorkerError:
    return WorkerError(
        WorkerErrorCode.JOB_STORE_FAILED,
        "synthetic retryable failure",
        retryable=True,
    )


def test_run_forever_waits_after_idle_and_continues_after_work() -> None:
    results = iter([None, "done"])
    stop = threading.Event()
    waits: list[float] = []

    def run_once() -> object | None:
        result = next(results)
        if result == "done":
            stop.set()
        return result

    counters = run_forever(
        run_once,
        stop_event=stop,
        policy=PollPolicy(
            idle_seconds=5.0,
            initial_backoff_seconds=1.0,
            max_backoff_seconds=8.0,
        ),
        wait=lambda seconds: waits.append(seconds) or False,
    )

    assert waits == [5.0]
    assert counters.claimed == 1
    assert counters.idle == 1
    assert counters.retryable_failures == 0


def test_retryable_failures_use_bounded_backoff_and_reset_after_response() -> None:
    outcomes: Iterator[object | None | WorkerError] = iter(
        [
            _retryable_job_store_error(),
            _retryable_job_store_error(),
            None,
            _retryable_job_store_error(),
        ]
    )
    waits: list[float] = []
    stop = threading.Event()

    def run_once() -> object | None:
        item = next(outcomes)
        if len(waits) == 3:
            stop.set()
        if isinstance(item, WorkerError):
            raise item
        return item

    counters = run_forever(
        run_once,
        stop_event=stop,
        policy=PollPolicy(
            idle_seconds=5,
            initial_backoff_seconds=1,
            max_backoff_seconds=2,
        ),
        wait=lambda seconds: waits.append(seconds) or False,
    )

    assert waits == [1, 2, 5, 1]
    assert counters.idle == 1
    assert counters.retryable_failures == 3


def test_non_retryable_failure_exits_without_waiting() -> None:
    waits: list[float] = []
    failure = WorkerError(
        WorkerErrorCode.JOB_STORE_AUTH_FAILED,
        "synthetic auth failure",
        retryable=False,
    )

    with pytest.raises(WorkerError) as raised:
        run_forever(
            lambda: (_ for _ in ()).throw(failure),
            stop_event=threading.Event(),
            policy=PollPolicy(),
            wait=lambda seconds: waits.append(seconds) or False,
        )

    assert raised.value is failure
    assert waits == []


def test_stop_before_entry_makes_zero_calls() -> None:
    stop = threading.Event()
    stop.set()
    calls = 0

    def run_once() -> object | None:
        nonlocal calls
        calls += 1
        return None

    counters = run_forever(run_once, stop_event=stop, policy=PollPolicy())

    assert calls == 0
    assert counters.claimed == 0
    assert counters.idle == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"idle_seconds": -1}, "poll intervals"),
        ({"initial_backoff_seconds": 0}, "poll intervals"),
        (
            {"initial_backoff_seconds": 2, "max_backoff_seconds": 1},
            "max backoff",
        ),
    ],
)
def test_poll_policy_rejects_invalid_values(
    kwargs: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        PollPolicy(**kwargs)

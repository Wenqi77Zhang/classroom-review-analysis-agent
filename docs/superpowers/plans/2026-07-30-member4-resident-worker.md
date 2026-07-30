# Member 4 M1 Resident Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the remote one-shot Worker entry point with a stoppable, single-instance M1 polling service while preserving heartbeat, secret, cleanup, and lease-loss safety.

**Architecture:** A focused `worker/runtime.py` owns polling and bounded retry policy; `worker/runner.py` remains responsible for CLI wiring, signals, HTTP store construction, and one claimed task. Pipeline cancellation is changed to fail closed without writing after lease loss. This plan intentionally does not add multi-Worker fencing, metrics HTTP, containers, or backend code.

**Tech Stack:** Python 3.13, `threading.Event`, existing `httpx`, Pydantic task contracts, pytest 9.1, Ruff 0.16.

## Global Constraints

- Use the repository root `.venv`; do not depend on global Python packages.
- Keep `WORKER_SERVICE_TOKEN` environment-only; do not add a CLI token option.
- M1 supports exactly one deployed Worker until member 3 freezes `lease_id` fencing.
- Empty claim responses are normal idle state, not failures.
- Do not record task IDs, owner IDs, media text, paths, signed URLs, or tokens in runtime counters or public errors.
- Do not modify `backend/`, the generic Agent orchestrator, or deployment containers in this plan.
- Do not commit `.agents/`, `skills-lock.json`, media, transcripts, model files, or local configuration.

---

## File Structure

- Create `worker/runtime.py`: polling policy, counters, bounded backoff, and the stoppable loop.
- Modify `worker/runner.py`: signal wiring, `--once`, environment-backed polling options, and loop integration.
- Modify `worker/pipeline.py`: stop/lease-loss must not write a new task state.
- Modify `worker/errors.py`: add a stable non-retryable authentication failure without exposing response bodies.
- Modify `worker/job_store.py`: classify 401/403 as non-retryable and preserve bounded retry for transport/5xx failures.
- Create `tests/unit/test_worker_runtime.py`: deterministic loop and cancellation tests.
- Modify `tests/unit/test_worker.py`: runner argument and post-stop persistence regression tests.
- Modify `worker/media-worker-guide.md`: single-Worker operating instructions and known concurrency limitation.

### Task 1: Deterministic Polling Runtime

**Files:**
- Create: `worker/runtime.py`
- Create: `tests/unit/test_worker_runtime.py`

**Interfaces:**
- Consumes: `run_once: Callable[[], object | None]`, `stop_event: threading.Event`.
- Produces: `PollPolicy`, `RuntimeCounters`, and `run_forever(...) -> RuntimeCounters`.

- [ ] **Step 1: Write failing idle and success tests**

```python
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
        policy=PollPolicy(idle_seconds=5.0, initial_backoff_seconds=1.0, max_backoff_seconds=8.0),
        wait=lambda seconds: waits.append(seconds) or False,
    )

    assert waits == [5.0]
    assert counters.claimed == 1
    assert counters.idle == 1
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_runtime.py -q`
Expected: FAIL because `worker.runtime` does not exist.

- [ ] **Step 3: Implement the policy, counters, and idle loop**

```python
@dataclass(frozen=True, slots=True)
class PollPolicy:
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
```

- [ ] **Step 4: Add bounded retry and stop tests**

```python
from collections.abc import Iterator


def _retryable_job_store_error() -> WorkerError:
    return WorkerError(
        WorkerErrorCode.JOB_STORE_FAILED,
        "synthetic retryable failure",
        retryable=True,
    )


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
        if isinstance(item, WorkerError):
            raise item
        if len(waits) == 3:
            stop.set()
        return item

    run_forever(
        run_once,
        stop_event=stop,
        policy=PollPolicy(idle_seconds=5, initial_backoff_seconds=1, max_backoff_seconds=2),
        wait=lambda seconds: waits.append(seconds) or False,
    )
    assert waits == [1, 2, 5, 1]
```

Also assert that a non-retryable `WorkerError` exits immediately and that `stop_event` set before entry makes zero calls.

- [ ] **Step 5: Run runtime tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_runtime.py -q`
Expected: PASS.

- [ ] **Step 6: Commit the polling unit**

```bash
git add worker/runtime.py tests/unit/test_worker_runtime.py
git commit -m "feat(worker): add resident polling runtime"
```

### Task 2: Runner CLI, Signal, and Loop Integration

**Files:**
- Modify: `worker/runner.py`
- Modify: `worker/job_store.py`
- Modify: `worker/errors.py`
- Modify: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: `PollPolicy` and `run_forever` from Task 1.
- Produces: `_run_remote(args, stop_event) -> RuntimeCounters | None` and CLI options `--once`, `--poll-interval`, `--max-backoff`.

- [ ] **Step 1: Write failing parser and remote-loop tests**

```python
class ClosingFakeStore:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _remote_args(*, once: bool) -> argparse.Namespace:
    return argparse.Namespace(
        video=None,
        output=None,
        model="tiny",
        language=None,
        api_base_url="http://127.0.0.1:8000",
        worker_id="test-worker",
        lease_seconds=300,
        object_root=None,
        once=once,
        poll_interval=5.0,
        max_backoff=30.0,
    )


def test_remote_parser_defaults_to_resident_single_worker() -> None:
    args = _build_parser().parse_args(["--api-base-url", "http://127.0.0.1:8000"])
    assert args.once is False
    assert args.poll_interval == 5.0
    assert args.max_backoff == 30.0


def test_once_mode_claims_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    fake_store = ClosingFakeStore()
    monkeypatch.setenv("WORKER_SERVICE_TOKEN", "test-only-token")
    monkeypatch.setattr("worker.runner.run_claimed_once", lambda *a, **k: calls.append("claim"))
    monkeypatch.setattr("worker.runner.LocalWhisperAdapter", lambda *a, **k: object())
    monkeypatch.setattr("worker.runner.HttpJobStore", lambda *a, **k: fake_store)
    assert _run_remote(_remote_args(once=True), threading.Event()) is None
    assert calls == ["claim"]
    assert fake_store.closed is True
```

This proves both one-shot compatibility and deterministic resource closure.

- [ ] **Step 2: Run the targeted tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py -k "parser_defaults or once_mode" -q`
Expected: FAIL because the options and `_run_remote` do not exist.

- [ ] **Step 3: Add CLI options with environment defaults**

```python
parser.add_argument("--once", action="store_true")
parser.add_argument(
    "--poll-interval",
    type=float,
    default=float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5")),
)
parser.add_argument(
    "--max-backoff",
    type=float,
    default=float(os.getenv("WORKER_MAX_BACKOFF_SECONDS", "30")),
)
```

Validate non-negative polling and `max_backoff >= 1` before constructing the store.

- [ ] **Step 4: Extract `_run_remote` and use `run_forever`**

Construct `HttpJobStore`, `InternalTaskClaimRequest`, and the existing process callback once. In `--once` mode call `run_claimed_once` once. Otherwise pass a zero-argument closure to `run_forever`. Always close the store in `finally`.

- [ ] **Step 5: Classify authentication and transient store failures**

Add `WorkerErrorCode.JOB_STORE_AUTH_FAILED` with the stable public message
`"Worker 服务凭据无效或无权访问内部接口。"` and platform code
`ErrorCode.UNAUTHENTICATED`.

In `HttpJobStore._request`, classify responses before calling `raise_for_status()`:

```python
if response.status_code in {401, 403}:
    raise WorkerError(
        WorkerErrorCode.JOB_STORE_AUTH_FAILED,
        "内部任务接口拒绝 Worker 凭据。",
        retryable=False,
    )
if response.status_code >= 500 or response.status_code in {408, 429}:
    raise WorkerError(
        WorkerErrorCode.JOB_STORE_FAILED,
        f"后端内部接口暂时不可用：{method} {path}",
        retryable=True,
    )
if response.is_error:
    raise WorkerError(
        WorkerErrorCode.JOB_STORE_FAILED,
        f"后端内部接口拒绝请求：{method} {path}",
        retryable=False,
    )
```

Map `httpx.RequestError` to retryable `JOB_STORE_FAILED`. Tests must prove that
401/403 exit the resident loop immediately, while 429, 500, and connection errors
use bounded retry. Do not include response bodies, headers, signed URLs, or tokens
in exception messages.

- [ ] **Step 6: Add signal wiring without mutating handlers in tests**

```python
def _install_signal_handlers(stop_event: threading.Event) -> None:
    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
```

Only call this from `main()` in remote mode on the main thread. Test the callback by monkeypatching `signal.signal` and invoking the captured handler.

- [ ] **Step 7: Run runner tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_runtime.py -q`
Expected: PASS.

- [ ] **Step 8: Commit runner integration**

```bash
git add worker/runner.py worker/job_store.py worker/errors.py tests/unit/test_worker.py
git commit -m "feat(worker): run remote worker continuously"
```

### Task 3: Stop Without Post-Lease Writes

**Files:**
- Modify: `worker/pipeline.py`
- Modify: `worker/runner.py`
- Modify: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: `WorkerErrorCode.STOPPED` and the existing stop event.
- Produces: the invariant “after stop/lease loss, no new state, transcript, or evidence write occurs.”

- [ ] **Step 1: Change the existing stop regression to require zero writes**

```python
with pytest.raises(WorkerError) as raised:
    run_pipeline(task, AsrMustNotRun(), store, stop_event=stop)

assert raised.value.code is WorkerErrorCode.STOPPED
assert task.task_id not in store.transcripts
assert task.task_id not in store.events
```

Add a second test that sets the stop event immediately after ASR returns and asserts no transcript or later event is saved.

- [ ] **Step 2: Run the stop tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py -k "lease_stop or stopped" -q`
Expected: FAIL because `run_pipeline` currently writes `FAILED` for `STOPPED`.

- [ ] **Step 3: Re-raise STOPPED before failure persistence**

```python
except WorkerError as exc:
    pipeline_failure = exc
    if exc.code is WorkerErrorCode.STOPPED:
        raise
    store.update_state(
        task.task_id,
        _state(
            current_stage,
            TaskStatus.FAILED,
            0.0,
            task.trace_id,
            message=f"{exc.code.value}: {public_worker_error_message(exc.code)}",
            error_code=exc.platform_code,
        ),
    )
    raise
```

In the `finally` cleanup failure branch, if `pipeline_failure` is `STOPPED`, attach
the cleanup error as an exception note and perform no store write. In
`_process_claimed_media`, do not synthesize a failure update when
`exc.code is STOPPED`.

- [ ] **Step 4: Run all Worker tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_runtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit lease-loss safety**

```bash
git add worker/pipeline.py worker/runner.py tests/unit/test_worker.py
git commit -m "fix(worker): stop writes after lease loss"
```

### Task 4: Runtime Documentation and Verification

**Files:**
- Modify: `worker/media-worker-guide.md`
- Modify: `.env.example`
- Modify: `reports/contributions/member-4.md`

**Interfaces:**
- Consumes: the final CLI and environment names from Tasks 1–3.
- Produces: reproducible single-Worker start instructions and an explicit concurrency limitation.

- [ ] **Step 1: Document exact remote operation**

Add:

```text
export WORKER_SERVICE_TOKEN
python -m worker.runner \
  --api-base-url http://127.0.0.1:8000
```

Document `--once` as diagnosis-only, `WORKER_POLL_INTERVAL_SECONDS=5`,
`WORKER_MAX_BACKOFF_SECONDS=30`, graceful shutdown behavior, and “M1 deploys one Worker only until member 3 lands lease fencing.”

- [ ] **Step 2: Add the non-secret environment default**

Add `WORKER_MAX_BACKOFF_SECONDS=30` immediately after `WORKER_POLL_INTERVAL_SECONDS=5` in `.env.example`.

- [ ] **Step 3: Run focused and static verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_runtime.py -q
.venv/bin/python -m ruff check worker tests/unit/test_worker.py tests/unit/test_worker_runtime.py
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Commit documentation**

```bash
git add .env.example worker/media-worker-guide.md reports/contributions/member-4.md
git commit -m "docs(worker): document resident single-worker mode"
```

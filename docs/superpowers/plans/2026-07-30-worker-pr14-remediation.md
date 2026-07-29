# PR #14 Worker Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭 PR #14 剩余 Worker 阻断项，使真实视频转写阶段遵守冻结状态机、租约、证据时间戳、清理和内部 HTTP 契约，并形成可复现的脱敏验收证据。

**Architecture:** `worker/runner.py` 负责从成员 3 的内部接口领取任务并独立续租，`worker/pipeline.py` 只完成媒体阶段并把结果整批交给后端，不宣告整项任务成功。`worker/stages/` 严格处理真实媒体，所有错误通过 `WorkerErrorCode` 稳定暴露；单元测试以 `httpx.MockTransport` 和小型临时 WAV 隔离外部依赖，真实视频只在本地集成验收中使用。

**Tech Stack:** Python 3.13、Pydantic 2、httpx、pytest、FFmpeg、openai-whisper、GitHub Actions。

## Global Constraints

- 后端 Schema 与 `docs/interface-contracts.md` 以最新 `main` 为准，本轮不修改冻结跨模块 Schema。
- 使用普通 merge 和普通 push；禁止 rebase、`reset --hard` 与 force push。
- `worker/` 只加工媒体与证据；不实现成员 5 的分析和报告职责。
- 不提交视频、音频、模型权重、完整逐字稿、密钥、Cookie 或对象存储签名 URL。
- 两个真实样例仅记录公开课程页、访问日期、使用依据、文件指纹和脱敏 ASR 摘要。
- 常规 CI 不安装 `openai-whisper`；真实 ASR 依赖继续保留在 `worker` 可选依赖中。

---

## File Map

- `worker/errors.py`：Worker 稳定错误码及平台错误码映射。
- `worker/job_store.py`：本地持久化边界与冻结内部 HTTP 接口客户端。
- `worker/runner.py`：本地真实视频入口、HTTP 领取入口和 heartbeat 生命周期。
- `worker/pipeline.py`：抽取、转写、持久化、阶段状态与清理的最短纵向链路。
- `worker/stages/extract_audio.py`：FFmpeg 抽取及稳定错误码。
- `worker/stages/transcribe.py`：真实音频时长读取和 ASR 时间戳严格校验。
- `worker/cleanup.py`：幂等、失败可观察的临时媒体清理。
- `worker/adapters/asr.py`：Whisper 适配器及上游失败映射。
- `tests/unit/test_worker.py`：状态、租约、时间戳、清理、错误码与 HTTP 契约回归测试。
- `tests/integration/test_video_pipeline.py`：两段本地真实视频的差异化转写验收。
- `tests/fixtures/fixture-catalog.md`：公开来源、使用依据和脱敏验收摘要。
- `docs/ai-collaboration-log.md`：本轮 AI 协作、人工确认与验证结论。

### Task 1: Merge Latest Main Without Rewriting History

**Files:**
- Preserve: all existing branch commits and files from `origin/main`

**Interfaces:**
- Consumes: remote branch `origin/main`
- Produces: merge commit whose second parent is the latest `origin/main`

- [x] **Step 1: Fetch and inspect divergence**

Run: `git fetch origin main`

Run: `git rev-list --left-right --count HEAD...origin/main`

Expected before merge: the feature branch may be both ahead and behind.

- [x] **Step 2: Merge the latest baseline**

Run: `git merge --no-ff origin/main`

Expected: ordinary merge commit, no force push and no loss of `7065fb2`.

- [x] **Step 3: Verify the branch is no longer behind**

Run: `git rev-list --left-right --count HEAD...origin/main`

Expected: right-hand count is `0`.

### Task 2: Separate Stage Completion From Terminal Task Success

**Files:**
- Modify: `worker/pipeline.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: `run_pipeline(task, adapter, store, *, stop_event=None)`
- Produces: transcript persistence followed by `TaskStage.TRANSCRIBE`, `TaskStatus.RUNNING`, `progress=1.0`

- [ ] **Step 1: Add a regression assertion for non-terminal completion**

In `test_pipeline_persists_transcript_and_real_states`, assert:

```python
assert events[-1].stage is TaskStage.TRANSCRIBE
assert events[-1].status is TaskStatus.RUNNING
assert events[-1].progress == 1.0
assert all(event.status is not TaskStatus.SUCCEEDED for event in events)
```

- [ ] **Step 2: Run the state test**

Run: `.venv/bin/pytest tests/unit/test_worker.py::test_pipeline_persists_transcript_and_real_states -q`

Expected before the fix: failure on `SUCCEEDED`; expected after the fix: one passing test.

- [ ] **Step 3: Implement the frozen handoff**

After `save_transcript`, write:

```python
_state(
    TaskStage.TRANSCRIBE,
    TaskStatus.RUNNING,
    1.0,
    task.trace_id,
    message="逐字稿已生成，等待下一阶段",
)
```

Do not write `TaskStatus.SUCCEEDED` anywhere in the Worker pipeline.

- [ ] **Step 4: Re-run the focused test**

Run: `.venv/bin/pytest tests/unit/test_worker.py::test_pipeline_persists_transcript_and_real_states -q`

Expected: pass.

### Task 3: Claim Tasks and Maintain the Lease

**Files:**
- Modify: `worker/job_store.py`
- Modify: `worker/runner.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: `HttpJobStore.claim()`, `HttpJobStore.heartbeat()`, `InternalTaskClaimRequest`
- Produces: `HeartbeatLease` and `run_claimed_once(store, request, process, *, heartbeat_interval_seconds=None)`

- [ ] **Step 1: Add claim and heartbeat lifecycle tests**

Cover these exact behaviors:

```python
assert run_claimed_once(empty_store, request, process) is None
assert empty_store.heartbeats == []
assert len(renewing_store.heartbeats) >= 2
assert stop_event.is_set() is True  # after heartbeat failure
```

Also assert a stopped lease prevents `save_transcript`.

- [ ] **Step 2: Run lifecycle tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'claim or heartbeat or lease_stop'`

Expected before the fix: missing lifecycle behavior; expected after the fix: all selected tests pass.

- [ ] **Step 3: Implement independent periodic renewal**

`HeartbeatLease` must:

```python
self.interval_seconds = interval_seconds or max(1.0, lease_seconds / 3)
self.stop_event = threading.Event()
self._finished = threading.Event()
```

Its thread immediately calls `store.heartbeat(...)`, repeats until `_finished`, records `WorkerError`, and sets `stop_event` on renewal failure. `__exit__` must signal, join, and raise `STOPPED` if the thread leaks.

- [ ] **Step 4: Add the remote runner path**

The remote CLI accepts `--api-base-url`, `--service-token`, `--worker-id`, `--lease-seconds`, and `--object-root`. It claims only:

```python
stages=[TaskStage.EXTRACT_AUDIO, TaskStage.TRANSCRIBE]
```

The claimed video `object_key` must resolve under `object_root`; traversal or a missing video asset raises `INPUT_NOT_FOUND`.

- [ ] **Step 5: Re-run lifecycle tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'claim or heartbeat or lease_stop'`

Expected: pass without leaked background threads.

### Task 4: Reject Invalid Evidence Timestamps

**Files:**
- Modify: `worker/stages/transcribe.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: a real WAV header and `AsrResult.segments`
- Produces: `InternalTranscriptWrite` or stable `INVALID_TIMESTAMP` / `TRANSCRIPT_SCHEMA_INVALID`

- [ ] **Step 1: Parameterize invalid timestamp cases**

Test `NaN`, positive infinity, negative start, zero duration, inverted duration, segment end beyond audio duration, overlapping segments, and a positive sub-millisecond interval that collapses after rounding.

Each invalid segment must satisfy:

```python
with pytest.raises(WorkerError) as raised:
    transcribe_audio(audio_path, adapter)
assert raised.value.code is WorkerErrorCode.INVALID_TIMESTAMP
```

Also test an unreadable WAV returns `TRANSCRIPT_SCHEMA_INVALID`.

- [ ] **Step 2: Run strict timestamp tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'transcribe'`

Expected before the fix: clamped or forged segments pass; expected after the fix: all cases are rejected.

- [ ] **Step 3: Implement real-duration validation**

Read `frame_count / frame_rate` with `wave.open`. For every ASR segment require finite, non-negative values, `end > start`, `start >= previous_end`, and `end <= duration_seconds`. After `round(seconds * 1000)`, require `end_ms > start_ms`.

- [ ] **Step 4: Re-run strict timestamp tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'transcribe'`

Expected: pass; no `max(start_ms + 1, ...)` or negative clamping remains.

### Task 5: Make Temporary Media Cleanup Failures Observable

**Files:**
- Modify: `worker/cleanup.py`
- Modify: `worker/pipeline.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: temporary file or directory path
- Produces: idempotent success or retryable `WorkerError(CLEANUP_FAILED)`

- [ ] **Step 1: Add permission-error and pipeline precedence tests**

Patch `shutil.rmtree` to raise `PermissionError`. Assert:

```python
assert raised.value.code is WorkerErrorCode.CLEANUP_FAILED
assert raised.value.retryable is True
```

Test successful media processing plus cleanup failure becomes `FAILED`; test primary processing failure plus cleanup failure preserves the primary exception and adds a cleanup note.

- [ ] **Step 2: Run cleanup tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'cleanup'`

Expected before the fix: deletion failure is swallowed; expected after the fix: all selected tests pass.

- [ ] **Step 3: Remove silent deletion**

Keep missing targets idempotent, call `unlink()` or `shutil.rmtree()` without `ignore_errors=True`, and wrap `OSError` as:

```python
WorkerError(
    WorkerErrorCode.CLEANUP_FAILED,
    "临时媒体清理失败。",
    retryable=True,
)
```

- [ ] **Step 4: Re-run cleanup tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'cleanup'`

Expected: pass.

### Task 6: Align Stable Error Codes and Test the HTTP Contract

**Files:**
- Modify: `worker/errors.py`
- Modify: `worker/adapters/asr.py`
- Modify: `worker/stages/extract_audio.py`
- Modify: `worker/job_store.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: frozen internal paths and Pydantic request/response models
- Produces: stable Worker errors and bearer-authenticated HTTP requests

- [ ] **Step 1: Assert the exact error-code set**

The test must compare `set(WorkerErrorCode)` with:

```python
{
    "INPUT_NOT_FOUND",
    "FFMPEG_NOT_FOUND",
    "AUDIO_EXTRACTION_FAILED",
    "AUDIO_EXTRACTION_TIMEOUT",
    "ASR_UNAVAILABLE",
    "ASR_TIMEOUT",
    "INVALID_TIMESTAMP",
    "TRANSCRIPT_SCHEMA_INVALID",
    "UPSTREAM_UNAVAILABLE",
    "CLEANUP_FAILED",
    "JOB_STORE_FAILED",
    "STOPPED",
}
```

- [ ] **Step 2: Add `httpx.MockTransport` contract tests**

Assert claim `204 -> None`, claim `200` parsing, `Authorization: Bearer <token>`, and these exact paths:

```text
POST  /api/internal/tasks/claim
POST  /api/internal/tasks/{task_id}/heartbeat
PATCH /api/internal/tasks/{task_id}/state
POST  /api/internal/tasks/{task_id}/transcript
```

Assert timeout, connection failure, and non-2xx responses become retryable `JOB_STORE_FAILED`. Assert transcript segments are sent in one batch with timestamps and trace ID.

- [ ] **Step 3: Run error and HTTP tests**

Run: `.venv/bin/pytest tests/unit/test_worker.py -q -k 'error_codes or http_job_store'`

Expected: pass.

- [ ] **Step 4: Run Worker lint**

Run: `.venv/bin/ruff check worker tests/unit/test_worker.py`

Expected: no findings.

- [ ] **Step 5: Commit the executable remediation**

Stage only Worker source and unit tests. Do not stage `.agents/` or `skills-lock.json`.

Run: `git commit -m "fix(worker): enforce leases and evidence contracts"`

Expected: one reviewable code-and-tests commit.

### Task 7: Record the Two Confirmed Public Course Sources

**Files:**
- Modify: `tests/fixtures/fixture-catalog.md`
- Test: `tests/integration/test_video_pipeline.py`

**Interfaces:**
- Consumes: two user-confirmed course URLs and two local MP4 files
- Produces: no media files; only source metadata, SHA-256 fingerprints, and short ASR summaries

- [ ] **Step 1: Record the confirmed source pages**

Use exactly:

```text
https://www.icourse163.org/course/XDU-1207042802?tid=1470983523
https://www.icourse163.org/course/HEPSVE-1002152002?tid=1003158005
```

Record access date `2026-07-29` and this usage basis: the pages were publicly accessible and the files were used only for local team functional verification; the project does not assert an open-content licence and does not redistribute the videos or full transcripts.

- [ ] **Step 2: Re-run the real-video integration test**

Run:

```bash
CLASSROOM_TEST_VIDEOS='/Users/abc/Downloads/人工智能导论.mp4:/Users/abc/Downloads/语文基础模块上册.mp4' WHISPER_MODEL=tiny .venv/bin/pytest tests/integration/test_video_pipeline.py -q -s
```

Expected: two videos produce non-empty, timestamped, different transcripts; local inputs and model cache remain untracked.

- [ ] **Step 3: Generate the current local output summaries**

Run the local runner once per file into `/tmp/classroom-worker-results-v2/`. Record only duration, file size, file SHA-256, language, segment count, first/last ranges, and a SHA-256 of the concatenated transcript text. Do not copy transcript text into the repository.

- [ ] **Step 4: Verify no media entered Git**

Run: `git status --short`

Run: `git ls-files | rg '\.(mp4|wav|mp3|m4a|bin|pt)$'`

Expected: no tracked video, extracted audio, or model file.

- [ ] **Step 5: Commit the evidence catalogue**

Run: `git commit -m "docs(worker): record real ASR verification evidence"`

Expected: only the fixture catalogue and related documentation are committed.

### Task 8: Update AI Collaboration Evidence and PR Description

**Files:**
- Modify: `docs/ai-collaboration-log.md`
- External update: GitHub PR #14 description

**Interfaces:**
- Consumes: final test commands, commit IDs, user confirmation, and real-video summaries
- Produces: truthful collaboration and verification record

- [ ] **Step 1: Append the collaboration record**

Record that Codex helped inspect PR feedback, merge `main`, implement and test the Worker fixes, while the user manually confirmed both course URLs and the limited verification usage basis. Record installed helper skills as local/untracked and do not claim an independent human code audit.

- [ ] **Step 2: Run full local gates**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check backend worker agent tests
git diff --check
```

Run the frontend test, type-check, and production-build commands defined by its package scripts.

Expected: all gates pass, or the PR description names any unrelated environmental limitation precisely.

- [ ] **Step 3: Commit the collaboration record**

Run: `git commit -m "docs(worker): document PR 14 AI-assisted verification"`

Expected: a documentation-only commit.

- [ ] **Step 4: Push without rewriting history**

Run: `git push origin member-4/media-pipeline`

Expected: normal fast-forward update to the feature branch.

- [ ] **Step 5: Replace the empty PR template**

PR #14 must list the implemented state boundary, heartbeat, timestamp rejection, cleanup behavior, error-code alignment, HTTP contract tests, two source URLs, anonymized real-ASR summaries, privacy constraints, exact local verification commands, and remaining object-storage integration boundary. Check only statements supported by completed tests.

- [ ] **Step 6: Monitor GitHub Actions and mergeability**

Wait for the new workflow run. Expected: `frontend-check`, `backend-check`, and scaffold/sensitive-file gates pass; PR reports no merge conflict with current `main`.

## Self-Review

- Spec coverage: every P1 item and synchronization requirement from the latest PR review maps to Tasks 1–8.
- Placeholder scan: the plan contains no deferred implementation placeholders; the word `TODO` appears only in the global prohibition against misrepresenting incomplete work.
- Type consistency: `run_pipeline`, `run_claimed_once`, `HeartbeatLease`, `HttpJobStore`, and the frozen backend schema names match their repository definitions.

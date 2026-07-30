# PR #27 Compatibility Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the transcript-first remote chain while keeping translation, courseware parsing, and evidence indexing as tested but unconnected internal capabilities.

**Architecture:** `run_pipeline` treats translation as an opt-in stage selected by a configured `TranslationAdapter`; the remote runner currently supplies none and hands off immediately after a complete transcript. A reported-stage floor prevents a reclaimed `transcribe` task from writing `extract_audio`, while both generic and professional bilingual gates restrict translation completeness checks to transcript evidence.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, SQLAlchemy async, PostgreSQL, HTTPX ASGI transport, Pytest, Ruff

## Global Constraints

- Do not download or configure a real translation model.
- Do not add backend schemas, migrations, evidence APIs, `lease_id`, or evidence versions.
- Do not register member 4 skills in the generic Agent runner.
- Do not connect translation, courseware parsing, or independent evidence indexing to the remote vertical chain.
- Preserve the existing transcript-based `handoff-agent` route from `main`.
- Treat lease-expiry recovery as same-stage continuation, not teacher retry.
- Keep M1 limited to one Worker until member 3 freezes lease fencing.
- Do not commit videos, full transcripts, model weights, secrets, `.agents/`, or `skills-lock.json`.
- Use ordinary commits and pushes; never force-push.

---

### Task 1: Make Translation Opt-In in the Pipeline

**Files:**
- Modify: `worker/pipeline.py:44-126`
- Modify: `tests/unit/test_worker.py:440-505`

**Interfaces:**
- Consumes: `TranslationAdapter | None` already accepted by `run_pipeline`.
- Produces: `run_pipeline(..., translation_adapter=None)` ending at `transcribe / running / 1.0`; configured adapters retain the existing translated result.

- [ ] **Step 1: Update the transcript-only test to express the compatibility contract**

Change `test_pipeline_persists_transcript_and_real_states` so its final assertions are:

```python
    final_event = store.events[task.task_id][-1]
    assert final_event.status is TaskStatus.RUNNING
    assert final_event.stage is TaskStage.TRANSCRIBE
    assert final_event.progress == 1.0
    assert result.translated_segments == 0
    assert all(
        event.stage is not TaskStage.TRANSLATE
        for event in store.events[task.task_id]
    )
```

Add an English no-adapter regression test:

```python
def test_pipeline_without_adapter_preserves_english_original_and_skips_translate(
    tmp_path: Path,
) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "english.wav"
    _silent_wav(source)
    store = RecordingTranscriptStore()
    task = PipelineTask(input_path=source)

    result = run_pipeline(
        task,
        FakeAsr(
            AsrResult(
                language="en",
                segments=(AsrSegment(0.0, 0.8, "Explain AI."),),
            )
        ),
        store,
    )

    assert result.translated_segments == 0
    assert len(store.transcript_writes) == 1
    assert store.transcript_writes[0].segments[0].text == "Explain AI."
    assert store.transcript_writes[0].segments[0].translation is None
    assert store.events[task.task_id][-1].stage is TaskStage.TRANSCRIBE
```

- [ ] **Step 2: Run the two tests and verify the old behavior fails**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_worker.py::test_pipeline_persists_transcript_and_real_states \
  tests/unit/test_worker.py::test_pipeline_without_adapter_preserves_english_original_and_skips_translate \
  -q
```

Expected: the existing pipeline reports `translate`, and the English run raises `TRANSLATION_UNAVAILABLE`.

- [ ] **Step 3: Return after transcript persistence when no adapter is configured**

In `worker/pipeline.py`, immediately after the successful
`transcribe / running / 1.0` state write, add:

```python
        if translation_adapter is None:
            return PipelineResult(
                task_id=task.task_id,
                transcript_segments=len(transcript.segments),
                translated_segments=0,
                duration_ms=transcript.duration_ms,
            )
```

Leave `translate_transcript` fail-closed when called directly with `None`; only the pipeline chooses not to call it.

- [ ] **Step 4: Run translation and pipeline tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_worker.py::test_pipeline_persists_transcript_and_real_states \
  tests/unit/test_worker.py::test_pipeline_without_adapter_preserves_english_original_and_skips_translate \
  tests/unit/test_worker.py::test_pipeline_persists_original_then_aligned_translation \
  tests/unit/test_worker_translation.py \
  -q
```

Expected: all pass; direct missing-adapter translation tests still return `TRANSLATION_UNAVAILABLE`.

- [ ] **Step 5: Commit the opt-in translation behavior**

```bash
git add worker/pipeline.py tests/unit/test_worker.py
git commit -m "fix(worker): keep remote chain transcript-first"
```

---

### Task 2: Preserve the Stage on an Expired-Lease Reclaim

**Files:**
- Modify: `worker/pipeline.py:44-80`
- Modify: `worker/runner.py:194-221`
- Modify: `tests/unit/test_worker.py:440-550`
- Modify: `tests/unit/test_worker.py:1040-1130`

**Interfaces:**
- Consumes: `InternalTaskClaim.stage` from the existing backend claim response.
- Produces: `run_pipeline(..., reported_stage_floor: TaskStage)` and a remote runner that passes `claim.stage`.

- [ ] **Step 1: Add a failing reclaimed-transcribe pipeline test**

```python
def test_reclaimed_transcribe_does_not_report_extract_audio(
    tmp_path: Path,
) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "reclaimed.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)

    run_pipeline(
        task,
        FakeAsr(
            AsrResult(
                language="zh",
                segments=(AsrSegment(0.0, 0.8, "恢复转写"),),
            )
        ),
        store,
        reported_stage_floor=TaskStage.TRANSCRIBE,
    )

    assert store.events[task.task_id]
    assert all(
        event.stage is TaskStage.TRANSCRIBE
        for event in store.events[task.task_id]
    )
```

- [ ] **Step 2: Run the test and verify the new argument is missing**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_worker.py::test_reclaimed_transcribe_does_not_report_extract_audio \
  -q
```

Expected: fail because `run_pipeline` does not accept `reported_stage_floor`.

- [ ] **Step 3: Add the reported-stage floor**

Change the `run_pipeline` signature:

```python
def run_pipeline(
    task: PipelineTask,
    adapter: AsrAdapter,
    store: JobStore,
    *,
    stop_event: Event | None = None,
    translation_adapter: TranslationAdapter | None = None,
    reported_stage_floor: TaskStage = TaskStage.EXTRACT_AUDIO,
) -> PipelineResult:
```

Validate and initialize the stage:

```python
    if reported_stage_floor not in {
        TaskStage.UPLOADED,
        TaskStage.EXTRACT_AUDIO,
        TaskStage.TRANSCRIBE,
    }:
        raise ValueError("reported_stage_floor must be a media input stage")
    current_stage = (
        TaskStage.TRANSCRIBE
        if reported_stage_floor is TaskStage.TRANSCRIBE
        else TaskStage.EXTRACT_AUDIO
    )
```

Wrap both extraction state writes so only a new/early task reports them:

```python
        if current_stage is TaskStage.EXTRACT_AUDIO:
            store.update_state(
                task.task_id,
                _state(
                    current_stage,
                    TaskStatus.RUNNING,
                    0.05,
                    task.trace_id,
                    message="正在抽取音频",
                ),
            )
        extract_audio(task.input_path, audio_path)
        _raise_if_stopped(stop_event)
        if current_stage is TaskStage.EXTRACT_AUDIO:
            store.update_state(
                task.task_id,
                _state(
                    current_stage,
                    TaskStatus.RUNNING,
                    1.0,
                    task.trace_id,
                    message="音频抽取完成",
                ),
            )
```

The following assignment to `current_stage = TaskStage.TRANSCRIBE` remains unchanged.

- [ ] **Step 4: Pass the claimed stage from the remote runner**

In `_process_claimed_media`, extend the existing call:

```python
            result = run_pipeline(
                PipelineTask(
                    task_id=claim.task_id,
                    trace_id=claim.trace_id,
                    input_path=input_path,
                ),
                adapter,
                store,
                stop_event=stop,
                translation_adapter=translation_adapter,
                reported_stage_floor=claim.stage,
            )
```

- [ ] **Step 5: Add a remote handoff regression test**

Monkeypatch the download and media functions while preserving real state calls:

```python
def test_reclaimed_transcribe_completes_without_backward_state_and_hands_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "claimed.wav"
    _silent_wav(source)
    claim = _claim().model_copy(update={"stage": TaskStage.TRANSCRIBE})
    store = FakeClaimingStore(claim)

    @contextmanager
    def claimed_path(*_: object):
        yield source

    monkeypatch.setattr("worker.runner._claimed_input_path", claimed_path)

    result = _process_claimed_media(
        claim,
        threading.Event(),
        store,  # type: ignore[arg-type]
        FakeAsr(
            AsrResult(
                language="zh",
                segments=(AsrSegment(0.0, 0.8, "续租恢复"),),
            )
        ),
        None,
        "worker-reclaimed",
    )

    assert result.transcript_segments == 1
    assert all(
        event.stage is TaskStage.TRANSCRIBE
        for event in store.events[claim.task_id]
    )
    assert store.handoffs == [
        (claim.task_id, InternalAgentHandoff(worker_id="worker-reclaimed"))
    ]
```

Add `contextmanager` to the existing `contextlib` imports in the test file.

- [ ] **Step 6: Run the reclaimed-stage and remote-runner tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_worker.py::test_reclaimed_transcribe_does_not_report_extract_audio \
  tests/unit/test_worker.py::test_reclaimed_transcribe_completes_without_backward_state_and_hands_off \
  tests/unit/test_worker.py::test_download_failure_is_persisted_as_retryable_task_failure \
  -q
```

Expected: all pass; a download failure before pipeline start still records `extract_audio`.

- [ ] **Step 7: Commit the lease-recovery behavior**

```bash
git add worker/pipeline.py worker/runner.py tests/unit/test_worker.py
git commit -m "fix(worker): resume reclaimed transcript stage safely"
```

---

### Task 3: Limit Bilingual Translation Checks to Transcript Evidence

**Files:**
- Modify: `agent/orchestrator.py:213-228`
- Modify: `agent/validators/evidence_gate.py:22-36`
- Modify: `tests/unit/test_agent.py:630-675`
- Modify: `tests/unit/test_member4_domain_rules.py:135-165`

**Interfaces:**
- Consumes: `EvidenceItem.reference.source_type`.
- Produces: identical translation-completeness semantics in generic and professional evidence gates.

- [ ] **Step 1: Add a generic-gate Chinese courseware test**

Add a helper argument to `_evidence` in `tests/unit/test_agent.py`:

```python
    source_type: EvidenceSourceType = EvidenceSourceType.TRANSCRIPT,
```

Construct the reference by source:

```python
    reference = (
        EvidenceReference(
            source_type=source_type,
            asset_id=uuid4(),
            page_no=2,
            quote=text,
        )
        if source_type is EvidenceSourceType.COURSEWARE
        else EvidenceReference(
            source_type=source_type,
            start_ms=start_ms,
            end_ms=end_ms,
            quote=text,
        )
    )
```

Use `reference=reference` in the returned `EvidenceItem`, then add:

```python
@pytest.mark.asyncio
async def test_bilingual_contract_does_not_require_translation_for_courseware() -> None:
    task_id = uuid4()
    owner_id = uuid4()
    evidence = _evidence(
        task_id=task_id,
        owner_id=owner_id,
        source_type=EvidenceSourceType.COURSEWARE,
        text="中文课件内容",
        translation=None,
    )
    provider = FakeProvider(_model_data(evidence.id))
    analysis_input = AnalysisInput(
        task_id=task_id,
        owner_id=owner_id,
        contract=AnalysisContract(
            goal="双语复盘",
            focus_areas=["讲解"],
            bilingual_required=True,
            confirmed=True,
        ),
        evidence=[evidence],
    )

    result = await AgentOrchestrator(
        providers=ProviderRouter(local=provider)
    ).analyze(analysis_input)

    assert result.conclusions.conclusions
    assert len(provider.requests) == 1
```

- [ ] **Step 2: Add professional-gate courseware tests**

```python
@pytest.mark.parametrize(
    "validator",
    [
        lambda evidence: validate_computer_ai_evidence(
            evidence,
            requires_visual_proof=True,
            bilingual_required=True,
        ),
        lambda evidence: validate_humanities_evidence(
            evidence,
            bilingual_required=True,
        ),
    ],
)
def test_professional_bilingual_gate_ignores_courseware_translation(
    validator,
) -> None:
    validator(
        [
            _evidence(
                EvidenceSourceType.COURSEWARE,
                text="中文课件内容",
                translation=None,
            )
        ]
    )
```

Keep `test_professional_rules_require_translation_when_bilingual` unchanged to prove transcript failure remains.

- [ ] **Step 3: Run the new tests and verify both gates reject courseware**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_agent.py::test_bilingual_contract_does_not_require_translation_for_courseware \
  tests/unit/test_member4_domain_rules.py::test_professional_bilingual_gate_ignores_courseware_translation \
  tests/unit/test_agent.py::test_bilingual_contract_rejects_missing_translation_before_model_call \
  tests/unit/test_member4_domain_rules.py::test_professional_rules_require_translation_when_bilingual \
  -q
```

Expected: the two courseware tests fail; the transcript rejection tests pass.

- [ ] **Step 4: Narrow the generic gate**

Replace the bilingual condition in `AgentOrchestrator._validate_evidence_policy`:

```python
        if contract.bilingual_required and any(
            item.reference.source_type is EvidenceSourceType.TRANSCRIPT
            and not (item.translation or "").strip()
            for item in evidence
        ):
```

`EvidenceSourceType` is already imported by `agent/orchestrator.py`; do not add a new dependency.

- [ ] **Step 5: Narrow the professional gate**

Replace `_require_translation`’s condition:

```python
    if bilingual_required and any(
        item.reference.source_type is EvidenceSourceType.TRANSCRIPT
        and not (item.translation or "").strip()
        for item in evidence
    ):
```

- [ ] **Step 6: Run all Agent and professional-rule tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_agent.py \
  tests/unit/test_member4_domain_rules.py \
  -q
```

Expected: all pass, including transcript fail-closed coverage.

- [ ] **Step 7: Commit the bilingual gate correction**

```bash
git add \
  agent/orchestrator.py \
  agent/validators/evidence_gate.py \
  tests/unit/test_agent.py \
  tests/unit/test_member4_domain_rules.py
git commit -m "fix(agent): scope bilingual gate to transcripts"
```

---

### Task 4: Add a Real FastAPI Lease-Reclaim State-Machine Combination

**Files:**
- Modify: `tests/integration/test_processing_api.py:1-20`
- Modify: `tests/integration/test_processing_api.py:450-510`

**Interfaces:**
- Consumes: existing `/api/internal/tasks/claim`, `/state`, `/transcript`, and `/handoff-agent` routes.
- Produces: PostgreSQL-backed regression coverage for expired `transcribe` lease recovery.

- [ ] **Step 1: Add integration-test imports**

```python
from datetime import UTC, datetime, timedelta

from backend.app.models import ProcessingTask, User
```

Replace the current `from backend.app.models import User` import rather than duplicating it.

- [ ] **Step 2: Extend the retry task into a transcribe lease-reclaim scenario**

After asserting `retried.json()["retry_count"] == 1`, add:

```python
            reclaimed_source = await client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-before-expiry", "stages": ["uploaded"]},
                headers=worker_headers,
            )
            assert reclaimed_source.status_code == 200
            assert reclaimed_source.json()["task_id"] == retry_task_id

            reached_transcribe = await client.patch(
                f"/api/internal/tasks/{retry_task_id}/state",
                json={
                    "stage": "transcribe",
                    "status": "running",
                    "progress": 0.5,
                },
                headers=worker_headers,
            )
            assert reached_transcribe.status_code == 200

            async with factory.begin() as session:
                expired_task = await session.get(ProcessingTask, uuid.UUID(retry_task_id))
                assert expired_task is not None
                expired_task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

            reclaimed_transcribe = await client.post(
                "/api/internal/tasks/claim",
                json={
                    "worker_id": "worker-after-expiry",
                    "stages": ["transcribe"],
                },
                headers=worker_headers,
            )
            assert reclaimed_transcribe.status_code == 200
            assert reclaimed_transcribe.json()["task_id"] == retry_task_id
            assert reclaimed_transcribe.json()["stage"] == "transcribe"

            backward_state = await client.patch(
                f"/api/internal/tasks/{retry_task_id}/state",
                json={
                    "stage": "extract_audio",
                    "status": "running",
                    "progress": 0.1,
                },
                headers=worker_headers,
            )
            assert backward_state.status_code == 409
            assert backward_state.json()["error"]["code"] == "STATE_CONFLICT"

            resumed_transcript = await client.post(
                f"/api/internal/tasks/{retry_task_id}/transcript",
                json={
                    "source_language": "zh",
                    "duration_ms": 1000,
                    "segments": [
                        {
                            "index": 0,
                            "start_ms": 0,
                            "end_ms": 800,
                            "text": "租约恢复后的新逐字稿。",
                        }
                    ],
                },
                headers=worker_headers,
            )
            assert resumed_transcript.status_code == 201

            completed_transcribe = await client.patch(
                f"/api/internal/tasks/{retry_task_id}/state",
                json={
                    "stage": "transcribe",
                    "status": "running",
                    "progress": 1.0,
                },
                headers=worker_headers,
            )
            assert completed_transcribe.status_code == 200

            resumed_handoff = await client.post(
                f"/api/internal/tasks/{retry_task_id}/handoff-agent",
                json={"worker_id": "worker-after-expiry"},
                headers=worker_headers,
            )
            assert resumed_handoff.status_code == 200
            assert resumed_handoff.json()["stage"] == "analyze"
            assert resumed_handoff.json()["status"] == "queued"

            async with factory() as session:
                handed_off_task = await session.get(
                    ProcessingTask,
                    uuid.UUID(retry_task_id),
                )
                assert handed_off_task is not None
                assert handed_off_task.claimed_by is None
                assert handed_off_task.lease_expires_at is None
```

- [ ] **Step 3: Run the PostgreSQL integration test**

Run:

```bash
TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  .venv/bin/python -m pytest \
  tests/integration/test_processing_api.py::test_shortest_processing_chain_and_retry \
  -q
```

Expected with PostgreSQL configured: pass. Expected without `TEST_DATABASE_URL`: one explicit skip. Do not report a local skip as a passed real-database test; PR CI must execute it.

- [ ] **Step 4: Run schema and backend state tests**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_backend.py \
  tests/unit/test_worker.py \
  -q
```

Expected: all pass.

- [ ] **Step 5: Commit the FastAPI combination**

```bash
git add tests/integration/test_processing_api.py
git commit -m "test(api): cover expired transcript lease recovery"
```

---

### Task 5: Document the Compatibility Boundary and Revalidate PR #27

**Files:**
- Modify: `worker/media-worker-guide.md:35-120`
- Modify: `agent/agent-module-guide.md:29-45`
- Modify: `docs/ai-collaboration-log.md:1-8`
- Modify: PR #27 description or add a PR #27 comment

**Interfaces:**
- Consumes: verified behavior from Tasks 1-4.
- Produces: an auditable handoff that does not claim remote translation/courseware/evidence integration.

- [ ] **Step 1: Update the Worker guide**

Record all of the following exact facts:

```markdown
- 远程 Worker 未配置真实 TranslationAdapter 时停在 transcribe 完成点，并通过现有
  handoff-agent 交给 Agent，不进入 translate。
- translate、parse_courseware 和 build_evidence_index 是经过单元测试的内部能力，
  尚未接入远程纵向链路。
- transcribe 租约过期后可以同阶段恢复；本地重新准备音频不回写更早数据库阶段。
- 真实模型、课件/独立证据持久化、第二段完整远程复验和阶段化教师重试仍未完成。
```

- [ ] **Step 2: Update the Agent guide and collaboration log**

State that:

```markdown
- 双语完整性只检查 transcript 证据的逐句译文；courseware、video 和 frame 继续使用
  页码、时间或画面定位，不因没有 translation 字段被拒绝。
- 这次修改是 PR #27 审核后的兼容修复，不代表成员 4 接管通用 Agent 编排。
```

Add the exact test results only after the commands in Step 3 finish.

- [ ] **Step 3: Run the complete local verification set**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check backend agent worker tests
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
bash verify.sh
bash scripts/check-secrets.sh
git diff --check
```

Expected: all non-environment-gated checks pass. Record the precise pass/skip counts; keep PostgreSQL and real-video skips explicit.

- [ ] **Step 4: Commit the documentation**

```bash
git add \
  worker/media-worker-guide.md \
  agent/agent-module-guide.md \
  docs/ai-collaboration-log.md
git commit -m "docs(worker): record transcript-first compatibility boundary"
```

- [ ] **Step 5: Verify branch scope before pushing**

```bash
git status --short --branch
git diff origin/main...HEAD --check
git rev-list --left-right --count origin/main...HEAD
```

Expected: `.agents/` and `skills-lock.json` remain untracked; no other uncommitted files; branch is not behind current `origin/main`.

- [ ] **Step 6: Push without rewriting history**

```bash
git push origin member-4/media-pipeline
```

Expected: ordinary fast-forward update of PR #27.

- [ ] **Step 7: Update PR #27 and wait for CI**

Add a PR comment containing:

```markdown
已按兼容优先建议完成：

- 无真实 TranslationAdapter 时远程链停在 transcribe 完成点并继续 Agent 交接；
- 翻译、课件解析和证据索引保留为内部测试能力，尚未接入远程纵向链路；
- transcribe 租约过期重领不再回写 extract_audio；
- 双语门禁不再误拒绝没有 translation 字段的课件/视频/画面证据；
- 增加 FastAPI + PostgreSQL 的租约过期重领、同阶段恢复和交接组合测试。

未下载模型，未新增后端接口，未接管通用 Agent 编排。
```

Wait until `backend-check`, `frontend-check`, and `scaffold` are terminal. Fix only verified failures and rerun affected checks before another push.

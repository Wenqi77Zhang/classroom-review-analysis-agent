from __future__ import annotations

import json
import shutil
import threading
import time
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import (
    InternalTaskClaim,
    InternalTaskClaimRequest,
    InternalTaskHeartbeat,
    InternalTaskStateUpdate,
    PrivacyMode,
    TaskStage,
    TaskStatus,
)
from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode
from worker.job_store import HttpJobStore, LocalJobStore
from worker.pipeline import run_pipeline
from worker.runner import run_claimed_once
from worker.stages.extract_audio import extract_audio
from worker.stages.transcribe import transcribe_audio
from worker.types import AsrResult, AsrSegment, PipelineTask


class FakeAsr:
    def __init__(self, result: AsrResult) -> None:
        self.result = result

    def transcribe(self, audio_path: Path) -> AsrResult:
        assert audio_path.stat().st_size > 44
        return self.result


class FakeClaimingStore(LocalJobStore):
    def __init__(
        self,
        claim: InternalTaskClaim | None,
        *,
        heartbeat_failure: WorkerError | None = None,
    ) -> None:
        super().__init__()
        self.claim_result = claim
        self.heartbeat_failure = heartbeat_failure
        self.claim_requests: list[InternalTaskClaimRequest] = []
        self.heartbeat_calls = 0

    def claim(self, request: InternalTaskClaimRequest) -> InternalTaskClaim | None:
        self.claim_requests.append(request)
        return self.claim_result

    def heartbeat(self, *_: object) -> None:
        self.heartbeat_calls += 1
        if self.heartbeat_failure is not None:
            raise self.heartbeat_failure


def _claim() -> InternalTaskClaim:
    return InternalTaskClaim(
        task_id=uuid4(),
        classroom_id=uuid4(),
        owner_id=uuid4(),
        stage=TaskStage.TRANSCRIBE,
        privacy_mode=PrivacyMode.LOCAL,
        assets=[],
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        trace_id="trace-claim",
    )


def _silent_wav(path: Path, seconds: int = 1) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 2 * 8000 * seconds)


def test_worker_error_codes_match_media_design() -> None:
    expected = {
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
    assert {code.value for code in WorkerErrorCode} == expected


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "work"
    target.mkdir()
    (target / "audio.wav").write_bytes(b"temporary")
    cleanup_path(target)
    cleanup_path(target)
    assert not target.exists()


def test_cleanup_failure_is_retryable_and_observable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "work"
    target.mkdir()

    def deny_cleanup(_: Path) -> None:
        raise PermissionError("occupied")

    monkeypatch.setattr(shutil, "rmtree", deny_cleanup)

    with pytest.raises(WorkerError) as raised:
        cleanup_path(target)

    assert raised.value.code is WorkerErrorCode.CLEANUP_FAILED
    assert raised.value.retryable is True


def test_extract_audio_produces_16khz_mono_pcm(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "source.wav"
    target = tmp_path / "target.wav"
    _silent_wav(source)

    extract_audio(source, target)

    with wave.open(str(target), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 16000
        assert audio.getsampwidth() == 2


def test_extract_audio_rejects_missing_input(tmp_path: Path) -> None:
    with pytest.raises(WorkerError) as raised:
        extract_audio(tmp_path / "missing.mp4", tmp_path / "audio.wav")
    assert raised.value.code is WorkerErrorCode.INPUT_NOT_FOUND


def test_transcribe_converts_seconds_to_frozen_schema(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    _silent_wav(audio, seconds=2)
    adapter = FakeAsr(
        AsrResult(
            language="zh",
            segments=(
                AsrSegment(0.1254, 1.5004, "第一句"),
                AsrSegment(1.5004, 1.9004, "第二句"),
            ),
        )
    )

    transcript = transcribe_audio(audio, adapter, trace_id="trace-test")

    assert transcript.source_language == "zh"
    assert [segment.index for segment in transcript.segments] == [0, 1]
    assert transcript.segments[0].start_ms == 125
    assert transcript.segments[0].end_ms == 1500
    assert transcript.segments[1].start_ms == 1500
    assert transcript.segments[1].end_ms == 1900
    assert transcript.duration_ms == 2000
    assert all(segment.speaker is None for segment in transcript.segments)


@pytest.mark.parametrize(
    ("segments", "reason"),
    [
        ((AsrSegment(float("nan"), 0.5, "x"),), "非有限"),
        ((AsrSegment(0.0, float("inf"), "x"),), "非有限"),
        ((AsrSegment(-0.1, 0.5, "x"),), "负数"),
        ((AsrSegment(0.5, 0.5, "x"),), "空区间"),
        ((AsrSegment(0.8, 0.2, "x"),), "倒序"),
        ((AsrSegment(0.5, 1.1, "x"),), "超出音频"),
        (
            (
                AsrSegment(0.0, 0.6, "first"),
                AsrSegment(0.5, 0.9, "overlap"),
            ),
            "非单调",
        ),
        ((AsrSegment(0.0001, 0.0004, "rounds-empty"),), "毫秒空区间"),
    ],
)
def test_transcribe_rejects_invalid_timestamps(
    tmp_path: Path,
    segments: tuple[AsrSegment, ...],
    reason: str,
) -> None:
    audio = tmp_path / "audio.wav"
    _silent_wav(audio)

    with pytest.raises(WorkerError) as raised:
        transcribe_audio(audio, FakeAsr(AsrResult(language="zh", segments=segments)))

    assert raised.value.code is WorkerErrorCode.INVALID_TIMESTAMP, reason


def test_transcribe_rejects_unreadable_audio_duration(tmp_path: Path) -> None:
    audio = tmp_path / "broken.wav"
    audio.write_bytes(b"not a wav")

    with pytest.raises(WorkerError) as raised:
        transcribe_audio(
            audio,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0, 0.5, "x"),))),
        )

    assert raised.value.code is WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID


def test_pipeline_persists_transcript_and_real_states(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)
    adapter = FakeAsr(
        AsrResult(language="zh", segments=(AsrSegment(0.0, 0.8, "真实输入结果"),))
    )

    result = run_pipeline(task, adapter, store)

    assert result.transcript_segments == 1
    assert store.transcripts[task.task_id].segments[0].text == "真实输入结果"
    final_event = store.events[task.task_id][-1]
    assert final_event.status is TaskStatus.RUNNING
    assert final_event.stage is TaskStage.TRANSCRIBE
    assert final_event.progress == 1.0
    assert all(
        event.status is not TaskStatus.SUCCEEDED
        for event in store.events[task.task_id]
    )


def test_claim_204_equivalent_does_not_start_heartbeat() -> None:
    store = FakeClaimingStore(None)
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )

    result = run_claimed_once(store, request, lambda *_: "unexpected")

    assert result is None
    assert store.claim_requests == [request]
    assert store.heartbeat_calls == 0


def test_claimed_task_heartbeats_periodically_and_stops() -> None:
    store = FakeClaimingStore(_claim())
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )

    def process(_: InternalTaskClaim, stop: threading.Event) -> str:
        assert not stop.is_set()
        deadline = time.monotonic() + 1
        while store.heartbeat_calls < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        return "done"

    result = run_claimed_once(
        store,
        request,
        process,
        heartbeat_interval_seconds=0.01,
    )
    calls_after_return = store.heartbeat_calls
    time.sleep(0.03)

    assert result == "done"
    assert calls_after_return >= 2
    assert store.heartbeat_calls == calls_after_return


def test_process_failure_stops_heartbeat_thread() -> None:
    store = FakeClaimingStore(_claim())
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )
    failure = WorkerError(
        WorkerErrorCode.UPSTREAM_UNAVAILABLE,
        "ASR failed",
        retryable=True,
    )

    def process(_: InternalTaskClaim, __: threading.Event) -> None:
        deadline = time.monotonic() + 1
        while store.heartbeat_calls < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        raise failure

    with pytest.raises(WorkerError) as raised:
        run_claimed_once(
            store,
            request,
            process,
            heartbeat_interval_seconds=0.01,
        )

    calls_after_failure = store.heartbeat_calls
    time.sleep(0.03)
    assert raised.value is failure
    assert store.heartbeat_calls == calls_after_failure


def test_heartbeat_failure_sets_stop_and_fails_claimed_task() -> None:
    failure = WorkerError(
        WorkerErrorCode.JOB_STORE_FAILED,
        "heartbeat failed",
        retryable=True,
    )
    store = FakeClaimingStore(_claim(), heartbeat_failure=failure)
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )

    def process(_: InternalTaskClaim, stop: threading.Event) -> None:
        assert stop.wait(timeout=1)

    with pytest.raises(WorkerError) as raised:
        run_claimed_once(
            store,
            request,
            process,
            heartbeat_interval_seconds=0.01,
        )

    assert raised.value is failure
    assert store.heartbeat_calls == 1


def test_pipeline_does_not_persist_after_lease_stop(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)
    stop = threading.Event()
    stop.set()

    class AsrMustNotRun:
        def transcribe(self, _: Path) -> AsrResult:
            raise AssertionError("ASR must not start after the lease is stopped")

    with pytest.raises(WorkerError) as raised:
        run_pipeline(
            task,
            AsrMustNotRun(),
            store,
            stop_event=stop,
        )

    assert raised.value.code is WorkerErrorCode.STOPPED
    assert task.task_id not in store.transcripts
    assert store.events[task.task_id][-1].status is TaskStatus.FAILED


def test_pipeline_records_actionable_failure(tmp_path: Path) -> None:
    store = LocalJobStore()
    task = PipelineTask(input_path=tmp_path / "missing.mp4")

    with pytest.raises(WorkerError):
        run_pipeline(
            task,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0, 1, "x"),))),
            store,
        )

    event = store.events[task.task_id][-1]
    assert event.status is TaskStatus.FAILED
    assert event.error_code is ErrorCode.RESOURCE_NOT_FOUND


def test_pipeline_cleanup_failure_overrides_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)

    def cleanup_fails(_: Path) -> None:
        raise WorkerError(
            WorkerErrorCode.CLEANUP_FAILED,
            "cannot remove",
            retryable=True,
        )

    monkeypatch.setattr("worker.pipeline.cleanup_path", cleanup_fails)

    with pytest.raises(WorkerError) as raised:
        run_pipeline(
            task,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0, 0.8, "x"),))),
            store,
        )

    assert raised.value.code is WorkerErrorCode.CLEANUP_FAILED
    assert store.events[task.task_id][-1].status is TaskStatus.FAILED


def test_pipeline_preserves_primary_failure_when_cleanup_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalJobStore()
    task = PipelineTask(input_path=tmp_path / "missing.mp4")

    def cleanup_fails(_: Path) -> None:
        raise WorkerError(
            WorkerErrorCode.CLEANUP_FAILED,
            "cannot remove",
            retryable=True,
        )

    monkeypatch.setattr("worker.pipeline.cleanup_path", cleanup_fails)

    with pytest.raises(WorkerError) as raised:
        run_pipeline(
            task,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0, 0.8, "x"),))),
            store,
        )

    assert raised.value.code is WorkerErrorCode.INPUT_NOT_FOUND
    assert "CLEANUP_FAILED" in "\n".join(raised.value.__notes__)
    assert store.events[task.task_id][-1].error_code is ErrorCode.INTERNAL_ERROR


def test_http_job_store_claim_204_path_and_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(handler),
    )
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )
    try:
        assert store.claim(request) is None
    finally:
        store.close()

    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/internal/tasks/claim"
    assert seen[0].headers["Authorization"] == "Bearer worker-secret"


def test_http_job_store_claim_parses_frozen_contract() -> None:
    expected = _claim()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=expected.model_dump(mode="json"))

    store = HttpJobStore(
        "https://backend.example/",
        "token",
        transport=httpx.MockTransport(handler),
    )
    try:
        actual = store.claim(
            InternalTaskClaimRequest(
                worker_id="worker-test",
                stages=[TaskStage.TRANSCRIBE],
                lease_seconds=30,
            )
        )
    finally:
        store.close()

    assert actual == expected


def test_http_job_store_heartbeat_state_and_batch_transcript_paths() -> None:
    seen: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(204)

    task_id = uuid4()
    transcript = InternalTranscriptWrite(
        source_language="zh",
        duration_ms=1000,
        trace_id="trace-http",
        segments=[
            InternalTranscriptSegmentWrite(
                index=0,
                start_ms=0,
                end_ms=800,
                text="脱敏测试",
            )
        ],
    )
    store = HttpJobStore(
        "https://backend.example",
        "token",
        transport=httpx.MockTransport(handler),
    )
    try:
        store.heartbeat(
            task_id,
            InternalTaskHeartbeat(worker_id="worker-test", lease_seconds=60),
        )
        store.update_state(
            task_id,
            InternalTaskStateUpdate(
                stage=TaskStage.TRANSCRIBE,
                status=TaskStatus.RUNNING,
                progress=1.0,
                trace_id="trace-http",
            ),
        )
        store.save_transcript(task_id, transcript)
    finally:
        store.close()

    assert [(method, path) for method, path, _ in seen] == [
        ("POST", f"/api/internal/tasks/{task_id}/heartbeat"),
        ("PATCH", f"/api/internal/tasks/{task_id}/state"),
        ("POST", f"/api/internal/tasks/{task_id}/transcript"),
    ]
    assert seen[0][2] == {"worker_id": "worker-test", "lease_seconds": 60}
    assert seen[2][2] == transcript.model_dump(mode="json")


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503, json={"error": {"code": "UPSTREAM_UNAVAILABLE"}}),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("offline"),
    ],
)
def test_http_job_store_maps_http_timeout_and_connection_failures(
    failure: httpx.Response | httpx.HTTPError,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, httpx.Response):
            failure.request = request
            return failure
        failure.request = request
        raise failure

    store = HttpJobStore(
        "https://backend.example",
        "token",
        timeout_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(WorkerError) as raised:
            store.claim(
                InternalTaskClaimRequest(
                    worker_id="worker-test",
                    stages=[TaskStage.TRANSCRIBE],
                    lease_seconds=30,
                )
            )
    finally:
        store.close()

    assert raised.value.code is WorkerErrorCode.JOB_STORE_FAILED
    assert raised.value.retryable is True

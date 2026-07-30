from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
import wave
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from backend.app.schemas.agent_runtime import InternalAgentHandoff
from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import (
    AnalysisContract,
    AssetKind,
    InternalAssetRead,
    InternalTaskClaim,
    InternalTaskClaimRequest,
    InternalTaskHeartbeat,
    InternalTaskStateUpdate,
    PrivacyMode,
    TaskStage,
    TaskStatus,
    UploadStatus,
)
from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.adapters.asr import LocalWhisperAdapter
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode
from worker.job_store import HttpJobStore, LocalJobStore
from worker.pipeline import run_pipeline
from worker.runner import (
    WORKER_CLAIM_STAGES,
    _build_parser,
    _claimed_input_path,
    _install_signal_handlers,
    _process_claimed_media,
    _run_remote,
    run_claimed_once,
)
from worker.stages.extract_audio import extract_audio
from worker.stages.transcribe import transcribe_audio
from worker.types import AsrResult, AsrSegment, PipelineTask, TranslationBatch


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
        self.handoffs: list[tuple[object, InternalAgentHandoff]] = []

    def claim(self, request: InternalTaskClaimRequest) -> InternalTaskClaim | None:
        self.claim_requests.append(request)
        return self.claim_result

    def heartbeat(self, *_: object) -> None:
        self.heartbeat_calls += 1
        if self.heartbeat_failure is not None:
            raise self.heartbeat_failure

    def handoff_agent(
        self,
        task_id: object,
        handoff: InternalAgentHandoff,
    ) -> None:
        self.handoffs.append((task_id, handoff))


class RecordingTranscriptStore(LocalJobStore):
    def __init__(self) -> None:
        super().__init__()
        self.transcript_writes: list[InternalTranscriptWrite] = []

    def save_transcript(
        self,
        task_id,
        transcript: InternalTranscriptWrite,
    ) -> None:
        self.transcript_writes.append(transcript.model_copy(deep=True))
        super().save_transcript(task_id, transcript)


class FakePipelineTranslation:
    model_name = "fake-translation-for-tests"

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch:
        assert source_language == "en"
        assert target_language == "zh"
        return TranslationBatch(
            translations=tuple(f"[测试译文]{text}" for text in texts),
            model_name=self.model_name,
        )


def _claim() -> InternalTaskClaim:
    return InternalTaskClaim(
        task_id=uuid4(),
        classroom_id=uuid4(),
        owner_id=uuid4(),
        stage=TaskStage.TRANSCRIBE,
        privacy_mode=PrivacyMode.LOCAL,
        assets=[],
        analysis_contract=AnalysisContract(
            goal="Review the lesson",
            focus_areas=["content structure"],
            evidence_requirements=["timestamped transcript"],
            confirmed=True,
        ),
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
        "OBJECT_DOWNLOAD_FAILED",
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
        "JOB_STORE_AUTH_FAILED",
        "TRANSLATION_UNAVAILABLE",
        "TRANSLATION_TIMEOUT",
        "TRANSLATION_SCHEMA_INVALID",
        "UNSUPPORTED_LANGUAGE",
        "COURSEWARE_UNSUPPORTED",
        "COURSEWARE_PARSE_FAILED",
        "EVIDENCE_INDEX_INVALID",
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


def test_extract_audio_does_not_expose_ffmpeg_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "tenant-a" / "private-class.mp4"
    source.parent.mkdir()
    source.write_bytes(b"not-a-real-video")
    target = tmp_path / "audio.wav"
    sensitive = r"C:\private\tenant-a\class.mp4 applicationKey=do-not-persist"

    class FailedProcess:
        returncode = 1
        stderr = sensitive

    monkeypatch.setattr("worker.stages.extract_audio.shutil.which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        "worker.stages.extract_audio.subprocess.run",
        lambda *_args, **_kwargs: FailedProcess(),
    )

    with pytest.raises(WorkerError) as raised:
        extract_audio(source, target)

    assert raised.value.code is WorkerErrorCode.AUDIO_EXTRACTION_FAILED
    assert sensitive not in str(raised.value)
    assert "applicationKey" not in str(raised.value)
    assert str(source) not in str(raised.value)


def test_remote_runner_has_no_cli_service_token_option() -> None:
    help_text = _build_parser().format_help()

    assert "--service-token" not in help_text
    assert "WORKER_SERVICE_TOKEN" not in help_text


def test_remote_runner_claims_newly_uploaded_tasks_without_object_root() -> None:
    args = _build_parser().parse_args(["--api-base-url", "http://127.0.0.1:8000"])

    assert args.object_root is None
    assert WORKER_CLAIM_STAGES == [
        TaskStage.UPLOADED,
        TaskStage.EXTRACT_AUDIO,
        TaskStage.TRANSCRIBE,
    ]


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


class ClosingFakeStore:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_remote_parser_defaults_to_resident_single_worker() -> None:
    args = _build_parser().parse_args(["--api-base-url", "http://127.0.0.1:8000"])

    assert args.once is False
    assert args.poll_interval == 5.0
    assert args.max_backoff == 30.0


def test_once_mode_claims_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    fake_store = ClosingFakeStore()
    monkeypatch.setenv("WORKER_SERVICE_TOKEN", "test-only-token")
    monkeypatch.setattr(
        "worker.runner.run_claimed_once",
        lambda *args, **kwargs: calls.append("claim"),
    )
    monkeypatch.setattr("worker.runner.LocalWhisperAdapter", lambda *args, **kwargs: object())
    monkeypatch.setattr("worker.runner.HttpJobStore", lambda *args, **kwargs: fake_store)

    assert _run_remote(_remote_args(once=True), threading.Event()) is None
    assert calls == ["claim"]
    assert fake_store.closed is True


def test_signal_handlers_request_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers: dict[int, object] = {}
    stop = threading.Event()

    monkeypatch.setattr(
        "worker.runner.signal.signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )

    _install_signal_handlers(stop)
    assert not stop.is_set()

    handler = handlers[2]
    assert callable(handler)
    handler(2, None)
    assert stop.is_set()


def test_process_stop_event_reaches_active_claim() -> None:
    store = FakeClaimingStore(_claim())
    request = InternalTaskClaimRequest(
        worker_id="worker-test",
        stages=[TaskStage.TRANSCRIBE],
        lease_seconds=30,
    )
    process_stop = threading.Event()

    def process(_: InternalTaskClaim, stop: threading.Event) -> str:
        assert not stop.is_set()
        process_stop.set()
        assert stop.wait(timeout=0.2)
        return "stopped"

    result = run_claimed_once(
        store,
        request,
        process,
        process_stop_event=process_stop,
    )

    assert result == "stopped"


def test_transcribe_converts_seconds_to_frozen_schema(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    _silent_wav(audio, seconds=2)
    adapter = FakeAsr(
        AsrResult(
            language="zh",
            segments=(
                AsrSegment(0.1254, 1.5000000000000002, "第一句"),
                AsrSegment(1.5, 1.9004, "第二句"),
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


def test_local_whisper_disables_nondeterministic_temperature_fallback(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "audio.wav"
    _silent_wav(audio)
    calls: list[dict[str, object]] = []

    class FakeWhisperModel:
        def transcribe(self, _: str, **options: object) -> dict[str, object]:
            calls.append(options)
            return {
                "language": "zh",
                "segments": [{"start": 0.0, "end": 0.8, "text": "固定结果"}],
            }

    adapter = LocalWhisperAdapter()
    adapter._model = FakeWhisperModel()

    result = adapter.transcribe(audio)

    assert result.segments[0].text == "固定结果"
    assert calls == [
        {
            "language": None,
            "fp16": False,
            "verbose": False,
            "temperature": 0.0,
            "condition_on_previous_text": False,
        }
    ]


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
    assert result.translated_segments == 0
    assert store.transcripts[task.task_id].segments[0].text == "真实输入结果"
    final_event = store.events[task.task_id][-1]
    assert final_event.status is TaskStatus.RUNNING
    assert final_event.stage is TaskStage.TRANSCRIBE
    assert final_event.progress == 1.0
    assert all(
        event.stage is not TaskStage.TRANSLATE
        for event in store.events[task.task_id]
    )
    assert all(
        event.status is not TaskStatus.SUCCEEDED
        for event in store.events[task.task_id]
    )


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


def test_reclaimed_transcribe_does_not_report_extract_audio(tmp_path: Path) -> None:
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


def test_pipeline_persists_original_then_aligned_translation(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
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
        translation_adapter=FakePipelineTranslation(),
    )

    assert [event.stage for event in store.events[task.task_id]][-2:] == [
        TaskStage.TRANSLATE,
        TaskStage.TRANSLATE,
    ]
    assert len(store.transcript_writes) == 2
    assert store.transcript_writes[0].segments[0].translation is None
    assert store.transcript_writes[1].segments[0].text == "Explain AI."
    assert (
        store.transcript_writes[1].segments[0].translation
        == "[测试译文]Explain AI."
    )
    assert result.translated_segments == 1


def test_pipeline_stop_during_translation_keeps_only_original_write(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = RecordingTranscriptStore()
    task = PipelineTask(input_path=source)
    stop = threading.Event()

    class StopAfterTranslation(FakePipelineTranslation):
        def translate_batch(
            self,
            texts: tuple[str, ...],
            *,
            source_language: str,
            target_language: str,
        ) -> TranslationBatch:
            result = super().translate_batch(
                texts,
                source_language=source_language,
                target_language=target_language,
            )
            stop.set()
            return result

    with pytest.raises(WorkerError) as raised:
        run_pipeline(
            task,
            FakeAsr(
                AsrResult(
                    language="en",
                    segments=(AsrSegment(0.0, 0.8, "Explain AI."),),
                )
            ),
            store,
            stop_event=stop,
            translation_adapter=StopAfterTranslation(),
        )

    assert raised.value.code is WorkerErrorCode.STOPPED
    assert len(store.transcript_writes) == 1
    assert store.transcript_writes[0].segments[0].translation is None
    assert store.events[task.task_id][-1].stage is TaskStage.TRANSLATE
    assert store.events[task.task_id][-1].progress == 0.0


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
    assert task.task_id not in store.events


def test_pipeline_does_not_persist_transcript_after_stop_during_asr(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is required")
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)
    stop = threading.Event()

    class StopAfterAsr:
        def transcribe(self, _: Path) -> AsrResult:
            stop.set()
            return AsrResult(
                language="zh",
                segments=(AsrSegment(0.0, 0.8, "不得写入"),),
            )

    with pytest.raises(WorkerError) as raised:
        run_pipeline(task, StopAfterAsr(), store, stop_event=stop)

    assert raised.value.code is WorkerErrorCode.STOPPED
    assert task.task_id not in store.transcripts
    assert len(store.events[task.task_id]) == 3
    assert store.events[task.task_id][-1].stage is TaskStage.TRANSCRIBE
    assert store.events[task.task_id][-1].progress == 0.0


def test_pipeline_cleanup_failure_after_stop_does_not_write_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "class.wav"
    _silent_wav(source)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)
    stop = threading.Event()
    stop.set()

    def cleanup_fails(_: Path) -> None:
        raise WorkerError(
            WorkerErrorCode.CLEANUP_FAILED,
            "synthetic cleanup failure",
            retryable=True,
        )

    monkeypatch.setattr("worker.pipeline.cleanup_path", cleanup_fails)

    with pytest.raises(WorkerError) as raised:
        run_pipeline(
            task,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0.0, 0.8, "x"),))),
            store,
            stop_event=stop,
        )

    assert raised.value.code is WorkerErrorCode.STOPPED
    assert "CLEANUP_FAILED" in "\n".join(raised.value.__notes__)
    assert task.task_id not in store.events
    assert task.task_id not in store.transcripts


def test_pipeline_failure_event_does_not_persist_sensitive_worker_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "private-class.mp4"
    source.write_bytes(b"video")
    store = LocalJobStore()
    task = PipelineTask(input_path=source)
    sensitive = r"C:\private\tenant-a\class.mp4 applicationKey=do-not-persist"

    def fail_extract(*_: object, **__: object) -> None:
        raise WorkerError(WorkerErrorCode.AUDIO_EXTRACTION_FAILED, sensitive)

    monkeypatch.setattr("worker.pipeline.extract_audio", fail_extract)

    with pytest.raises(WorkerError):
        run_pipeline(
            task,
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0.0, 0.1, "x"),))),
            store,
        )

    persisted = store.events[task.task_id][-1].message or ""
    assert sensitive not in persisted
    assert "applicationKey" not in persisted
    assert persisted == "AUDIO_EXTRACTION_FAILED: 课堂视频音频抽取失败。"


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
            FakeAsr(AsrResult(language="zh", segments=(AsrSegment(0, 0.8, "中文"),))),
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


def test_http_job_store_treats_json_null_as_empty_queue() -> None:
    store = HttpJobStore(
        "https://backend.example",
        "token",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=None)),
    )
    try:
        assert (
            store.claim(
                InternalTaskClaimRequest(
                    worker_id="worker-test",
                    stages=[TaskStage.UPLOADED],
                )
            )
            is None
        )
    finally:
        store.close()


def _download_asset(
    *,
    size_bytes: int,
    url: str = "https://storage.example/object",
    verified_etag: str | None = "verified-etag",
):
    return InternalAssetRead(
        id=uuid4(),
        classroom_id=uuid4(),
        kind=AssetKind.VIDEO,
        filename="authorized-test.mp4",
        content_type="video/mp4",
        size_bytes=size_bytes,
        upload_status=UploadStatus.UPLOADED,
        object_key="owners/test/classrooms/test/assets/test/source",
        created_at=datetime.now(UTC),
        download_url=url,
        verified_etag=verified_etag,
    )


def test_http_job_store_downloads_without_forwarding_service_token(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    payload = b"real-video-bytes"

    def download_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=payload,
            headers={"ETag": '"verified-etag"'},
        )

    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(204)),
        download_transport=httpx.MockTransport(download_handler),
    )
    target = tmp_path / "source-media"
    try:
        store.download_asset(_download_asset(size_bytes=len(payload)), target)
    finally:
        store.close()

    assert target.read_bytes() == payload
    assert seen[0].url == "https://storage.example/object"
    assert "Authorization" not in seen[0].headers


@pytest.mark.parametrize("payload", [b"short", b"content-that-is-too-long"])
def test_http_job_store_rejects_size_mismatch_and_removes_partial_file(
    tmp_path: Path,
    payload: bytes,
) -> None:
    expected_size = len(b"expected")
    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(204)),
        download_transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=payload,
                headers={"ETag": '"verified-etag"'},
            )
        ),
    )
    target = tmp_path / "partial"
    try:
        with pytest.raises(WorkerError) as raised:
            store.download_asset(_download_asset(size_bytes=expected_size), target)
    finally:
        store.close()

    assert raised.value.code is WorkerErrorCode.OBJECT_DOWNLOAD_FAILED
    assert raised.value.retryable is True
    assert not target.exists()


@pytest.mark.parametrize("response_etag", [None, '"different-etag"'])
def test_http_job_store_rejects_missing_or_changed_verified_etag(
    tmp_path: Path,
    response_etag: str | None,
) -> None:
    payload = b"same-size-content"
    headers = {"ETag": response_etag} if response_etag is not None else {}
    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(204)),
        download_transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=payload, headers=headers)
        ),
    )
    target = tmp_path / "replaced-object"
    try:
        with pytest.raises(WorkerError) as raised:
            store.download_asset(_download_asset(size_bytes=len(payload)), target)
    finally:
        store.close()

    assert raised.value.code is WorkerErrorCode.OBJECT_DOWNLOAD_FAILED
    assert not target.exists()


def test_http_job_store_download_failure_hides_presigned_url(tmp_path: Path) -> None:
    sensitive_url = "https://storage.example/object?X-Amz-Signature=must-not-leak"
    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(204)),
        download_transport=httpx.MockTransport(
            lambda _: httpx.Response(403, text="forbidden")
        ),
    )
    try:
        with pytest.raises(WorkerError) as raised:
            store.download_asset(
                _download_asset(size_bytes=1, url=sensitive_url),
                tmp_path / "partial",
            )
    finally:
        store.close()

    assert sensitive_url not in str(raised.value)
    assert raised.value.__cause__ is None


def test_claimed_input_download_is_private_and_cleaned(tmp_path: Path) -> None:
    payload = b"downloaded-video"
    asset = _download_asset(size_bytes=len(payload))
    claim = _claim().model_copy(update={"assets": [asset]})
    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(204)),
        download_transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=payload,
                headers={"ETag": '"verified-etag"'},
            )
        ),
    )
    try:
        with _claimed_input_path(claim, store, None) as input_path:
            work_dir = input_path.parent
            assert input_path.read_bytes() == payload
            assert work_dir != tmp_path
        assert not work_dir.exists()
    finally:
        store.close()


def test_download_failure_is_persisted_as_retryable_task_failure() -> None:
    asset = _download_asset(
        size_bytes=1,
        url="https://storage.example/object?X-Amz-Signature=private",
    )
    claim = _claim().model_copy(
        update={
            "assets": [asset],
            "stage": TaskStage.UPLOADED,
        }
    )
    seen: list[tuple[str, dict[str, object]]] = []

    def backend_handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(204)

    store = HttpJobStore(
        "https://backend.example",
        "worker-secret",
        transport=httpx.MockTransport(backend_handler),
        download_transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    try:
        with pytest.raises(WorkerError) as raised:
            _process_claimed_media(
                claim,
                threading.Event(),
                store,
                FakeAsr(AsrResult(language="zh", segments=())),
                None,
                "worker-test",
            )
    finally:
        store.close()

    assert raised.value.code is WorkerErrorCode.OBJECT_DOWNLOAD_FAILED
    assert seen == [
        (
            f"/api/internal/tasks/{claim.task_id}/state",
            {
                "stage": "extract_audio",
                "status": "failed",
                "progress": 0.0,
                "message": "OBJECT_DOWNLOAD_FAILED: 课堂视频下载失败或文件不完整。",
                "error_code": "UPSTREAM_UNAVAILABLE",
                "trace_id": "trace-claim",
            },
        )
    ]


def test_reclaimed_transcribe_download_failure_stays_at_transcribe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _claim().model_copy(update={"stage": TaskStage.TRANSCRIBE})
    store = FakeClaimingStore(claim)

    @contextmanager
    def claimed_path(*_: object):
        raise WorkerError(
            WorkerErrorCode.OBJECT_DOWNLOAD_FAILED,
            "reclaimed media download failed",
            retryable=True,
        )
        yield Path("unreachable")

    monkeypatch.setattr("worker.runner._claimed_input_path", claimed_path)

    with pytest.raises(WorkerError) as raised:
        _process_claimed_media(
            claim,
            threading.Event(),
            store,  # type: ignore[arg-type]
            FakeAsr(AsrResult(language="zh", segments=())),
            None,
            "worker-reclaimed",
        )

    assert raised.value.code is WorkerErrorCode.OBJECT_DOWNLOAD_FAILED
    assert store.events[claim.task_id][-1].stage is TaskStage.TRANSCRIBE
    assert store.events[claim.task_id][-1].status is TaskStatus.FAILED


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

    def fake_extract_audio(_: Path, output_path: Path) -> Path:
        _silent_wav(output_path)
        return output_path

    monkeypatch.setattr("worker.runner._claimed_input_path", claimed_path)
    monkeypatch.setattr("worker.pipeline.extract_audio", fake_extract_audio)

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


def test_reclaimed_transcribe_cleanup_failure_stays_at_transcribe(
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
        raise WorkerError(
            WorkerErrorCode.CLEANUP_FAILED,
            "claimed media cleanup failed",
            retryable=True,
        )

    def fake_extract_audio(_: Path, output_path: Path) -> Path:
        _silent_wav(output_path)
        return output_path

    monkeypatch.setattr("worker.runner._claimed_input_path", claimed_path)
    monkeypatch.setattr("worker.pipeline.extract_audio", fake_extract_audio)

    with pytest.raises(WorkerError) as raised:
        _process_claimed_media(
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

    assert raised.value.code is WorkerErrorCode.CLEANUP_FAILED
    assert store.events[claim.task_id][-1].stage is TaskStage.TRANSCRIBE
    assert store.events[claim.task_id][-1].status is TaskStatus.FAILED
    assert store.handoffs == []


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
        store.handoff_agent(
            task_id,
            InternalAgentHandoff(worker_id="worker-test"),
        )
    finally:
        store.close()

    assert [(method, path) for method, path, _ in seen] == [
        ("POST", f"/api/internal/tasks/{task_id}/heartbeat"),
        ("PATCH", f"/api/internal/tasks/{task_id}/state"),
        ("POST", f"/api/internal/tasks/{task_id}/transcript"),
        ("POST", f"/api/internal/tasks/{task_id}/handoff-agent"),
    ]
    assert seen[0][2] == {"worker_id": "worker-test", "lease_seconds": 60}
    assert seen[2][2] == transcript.model_dump(mode="json")
    assert seen[3][2] == {"worker_id": "worker-test"}


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(429, json={"error": {"code": "RATE_LIMITED"}}),
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


@pytest.mark.parametrize("status_code", [401, 403])
def test_http_job_store_auth_failure_is_not_retried(status_code: int) -> None:
    store = HttpJobStore(
        "https://backend.example",
        "invalid-token",
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
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

    assert raised.value.code is WorkerErrorCode.JOB_STORE_AUTH_FAILED
    assert raised.value.platform_code is ErrorCode.UNAUTHENTICATED
    assert raised.value.retryable is False


def test_http_job_store_non_transient_client_failure_is_not_retried() -> None:
    store = HttpJobStore(
        "https://backend.example",
        "token",
        transport=httpx.MockTransport(lambda _: httpx.Response(422)),
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
    assert raised.value.retryable is False

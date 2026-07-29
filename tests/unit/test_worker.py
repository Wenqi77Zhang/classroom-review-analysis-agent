from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest

from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import TaskStatus
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode
from worker.job_store import LocalJobStore
from worker.pipeline import run_pipeline
from worker.stages.extract_audio import extract_audio
from worker.stages.transcribe import transcribe_audio
from worker.types import AsrResult, AsrSegment, PipelineTask


class FakeAsr:
    def __init__(self, result: AsrResult) -> None:
        self.result = result

    def transcribe(self, audio_path: Path) -> AsrResult:
        assert audio_path.stat().st_size > 44
        return self.result


def _silent_wav(path: Path, seconds: int = 1) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 2 * 8000 * seconds)


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "work"
    target.mkdir()
    (target / "audio.wav").write_bytes(b"temporary")
    cleanup_path(target)
    cleanup_path(target)
    assert not target.exists()


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
    audio.write_bytes(b"x" * 100)
    adapter = FakeAsr(
        AsrResult(
            language="zh",
            segments=(
                AsrSegment(0.1254, 1.5004, "第一句"),
                AsrSegment(1.5004, 1.5004, "边界句"),
            ),
        )
    )

    transcript = transcribe_audio(audio, adapter, trace_id="trace-test")

    assert transcript.source_language == "zh"
    assert [segment.index for segment in transcript.segments] == [0, 1]
    assert transcript.segments[0].start_ms == 125
    assert transcript.segments[0].end_ms == 1500
    assert transcript.segments[1].end_ms == transcript.segments[1].start_ms + 1
    assert all(segment.speaker is None for segment in transcript.segments)


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
    assert store.events[task.task_id][-1].status is TaskStatus.SUCCEEDED


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

"""Shortest real media pipeline: video -> WAV -> timestamped transcript."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import InternalTaskStateUpdate, TaskStage, TaskStatus
from worker.adapters.asr import AsrAdapter
from worker.cleanup import cleanup_path
from worker.errors import WorkerError
from worker.job_store import JobStore
from worker.stages.extract_audio import extract_audio
from worker.stages.transcribe import transcribe_audio
from worker.types import PipelineResult, PipelineTask


def _state(
    stage: TaskStage,
    status: TaskStatus,
    progress: float,
    trace_id: str,
    *,
    message: str | None = None,
    error_code: ErrorCode | None = None,
) -> InternalTaskStateUpdate:
    return InternalTaskStateUpdate(
        stage=stage,
        status=status,
        progress=progress,
        message=message,
        error_code=error_code,
        trace_id=trace_id,
    )


def run_pipeline(task: PipelineTask, adapter: AsrAdapter, store: JobStore) -> PipelineResult:
    work_dir = Path(tempfile.mkdtemp(prefix=f"classroom-worker-{task.task_id}-"))
    audio_path = work_dir / "audio.wav"
    current_stage = TaskStage.EXTRACT_AUDIO
    try:
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.RUNNING, 0.05, task.trace_id, message="正在抽取音频"),
        )
        extract_audio(task.input_path, audio_path)
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.RUNNING, 1.0, task.trace_id, message="音频抽取完成"),
        )

        current_stage = TaskStage.TRANSCRIBE
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.RUNNING, 0.0, task.trace_id, message="正在识别语音"),
        )
        transcript = transcribe_audio(audio_path, adapter, trace_id=task.trace_id)
        store.save_transcript(task.task_id, transcript)
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.SUCCEEDED, 1.0, task.trace_id, message="逐字稿已生成"),
        )
        return PipelineResult(
            task_id=task.task_id,
            transcript_segments=len(transcript.segments),
            duration_ms=transcript.duration_ms,
        )
    except WorkerError as exc:
        store.update_state(
            task.task_id,
            _state(
                current_stage,
                TaskStatus.FAILED,
                0.0,
                task.trace_id,
                message=f"{exc.code}: {exc}",
                error_code=exc.platform_code,
            ),
        )
        raise
    except Exception as exc:
        store.update_state(
            task.task_id,
            _state(
                current_stage,
                TaskStatus.FAILED,
                0.0,
                task.trace_id,
                message=f"未预期的 Worker 错误：{type(exc).__name__}",
                error_code=ErrorCode.INTERNAL_ERROR,
            ),
        )
        raise
    finally:
        cleanup_path(work_dir)

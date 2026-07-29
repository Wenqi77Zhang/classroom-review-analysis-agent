"""Shortest real media pipeline: video -> WAV -> timestamped transcript."""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Event

from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import InternalTaskStateUpdate, TaskStage, TaskStatus
from worker.adapters.asr import AsrAdapter
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode, public_worker_error_message
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


def _raise_if_stopped(stop_event: Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise WorkerError(
            WorkerErrorCode.STOPPED,
            "任务租约已停止，放弃继续处理或写入结果。",
            retryable=True,
        )


def run_pipeline(
    task: PipelineTask,
    adapter: AsrAdapter,
    store: JobStore,
    *,
    stop_event: Event | None = None,
) -> PipelineResult:
    work_dir = Path(tempfile.mkdtemp(prefix=f"classroom-worker-{task.task_id}-"))
    audio_path = work_dir / "audio.wav"
    current_stage = TaskStage.EXTRACT_AUDIO
    pipeline_failure: BaseException | None = None
    try:
        _raise_if_stopped(stop_event)
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.RUNNING, 0.05, task.trace_id, message="正在抽取音频"),
        )
        extract_audio(task.input_path, audio_path)
        _raise_if_stopped(stop_event)
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
        _raise_if_stopped(stop_event)
        store.save_transcript(task.task_id, transcript)
        store.update_state(
            task.task_id,
            _state(
                current_stage,
                TaskStatus.RUNNING,
                1.0,
                task.trace_id,
                message="逐字稿已生成，等待下一阶段",
            ),
        )
        return PipelineResult(
            task_id=task.task_id,
            transcript_segments=len(transcript.segments),
            duration_ms=transcript.duration_ms,
        )
    except WorkerError as exc:
        pipeline_failure = exc
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
    except Exception as exc:
        pipeline_failure = exc
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
        try:
            cleanup_path(work_dir)
        except WorkerError as cleanup_error:
            if pipeline_failure is not None:
                pipeline_failure.add_note(f"{cleanup_error.code}: {cleanup_error}")
                store.update_state(
                    task.task_id,
                    _state(
                        current_stage,
                        TaskStatus.FAILED,
                        0.0,
                        task.trace_id,
                        message=(
                            f"{type(pipeline_failure).__name__}; "
                            f"{cleanup_error.code}: 临时媒体清理失败"
                        ),
                        error_code=cleanup_error.platform_code,
                    ),
                )
            else:
                store.update_state(
                    task.task_id,
                    _state(
                        current_stage,
                        TaskStatus.FAILED,
                        0.0,
                        task.trace_id,
                        message=(
                            f"{cleanup_error.code.value}: "
                            f"{public_worker_error_message(cleanup_error.code)}"
                        ),
                        error_code=cleanup_error.platform_code,
                    ),
                )
                raise

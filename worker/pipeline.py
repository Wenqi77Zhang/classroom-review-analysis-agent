"""Shortest real media pipeline: video -> WAV -> timestamped transcript."""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Event

from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import InternalTaskStateUpdate, TaskStage, TaskStatus
from worker.adapters.asr import AsrAdapter
from worker.adapters.translation import TranslationAdapter
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode, public_worker_error_message
from worker.job_store import JobStore
from worker.stages.extract_audio import extract_audio
from worker.stages.import_translation import align_supplemental_translations
from worker.stages.transcribe import transcribe_audio
from worker.stages.translate import translate_transcript
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
    translation_adapter: TranslationAdapter | None = None,
    supplemental_translation_path: Path | None = None,
    reported_stage_floor: TaskStage = TaskStage.EXTRACT_AUDIO,
) -> PipelineResult:
    if reported_stage_floor not in {
        TaskStage.UPLOADED,
        TaskStage.EXTRACT_AUDIO,
        TaskStage.TRANSCRIBE,
        TaskStage.TRANSLATE,
    }:
        raise ValueError("reported_stage_floor must be a media input stage")

    work_dir = Path(tempfile.mkdtemp(prefix=f"classroom-worker-{task.task_id}-"))
    audio_path = work_dir / "audio.wav"
    stage_order = {
        TaskStage.UPLOADED: 0,
        TaskStage.EXTRACT_AUDIO: 1,
        TaskStage.TRANSCRIBE: 2,
        TaskStage.TRANSLATE: 3,
    }
    current_stage = (
        reported_stage_floor
        if stage_order[reported_stage_floor] > stage_order[TaskStage.EXTRACT_AUDIO]
        else TaskStage.EXTRACT_AUDIO
    )
    pipeline_failure: BaseException | None = None
    try:
        _raise_if_stopped(stop_event)
        if stage_order[reported_stage_floor] <= stage_order[TaskStage.EXTRACT_AUDIO]:
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
        if stage_order[reported_stage_floor] <= stage_order[TaskStage.EXTRACT_AUDIO]:
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

        current_stage = (
            reported_stage_floor
            if stage_order[reported_stage_floor] > stage_order[TaskStage.TRANSCRIBE]
            else TaskStage.TRANSCRIBE
        )
        if stage_order[reported_stage_floor] <= stage_order[TaskStage.TRANSCRIBE]:
            store.update_state(
                task.task_id,
                _state(
                    TaskStage.TRANSCRIBE,
                    TaskStatus.RUNNING,
                    0.0,
                    task.trace_id,
                    message="正在识别语音",
                ),
            )
        transcript = transcribe_audio(audio_path, adapter, trace_id=task.trace_id)
        _raise_if_stopped(stop_event)
        store.save_transcript(task.task_id, transcript)
        if stage_order[reported_stage_floor] <= stage_order[TaskStage.TRANSCRIBE]:
            store.update_state(
                task.task_id,
                _state(
                    TaskStage.TRANSCRIBE,
                    TaskStatus.RUNNING,
                    1.0,
                    task.trace_id,
                    message="逐字稿已生成，等待下一阶段",
                ),
            )

        if supplemental_translation_path is None and translation_adapter is None:
            return PipelineResult(
                task_id=task.task_id,
                transcript_segments=len(transcript.segments),
                translated_segments=0,
                duration_ms=transcript.duration_ms,
            )

        current_stage = TaskStage.TRANSLATE
        store.update_state(
            task.task_id,
            _state(current_stage, TaskStatus.RUNNING, 0.0, task.trace_id, message="正在逐句翻译"),
        )
        translated = (
            align_supplemental_translations(transcript, supplemental_translation_path)
            if supplemental_translation_path is not None
            else translate_transcript(
                transcript,
                translation_adapter,
                stop_event=stop_event,
            )
        )
        _raise_if_stopped(stop_event)
        store.save_transcript(task.task_id, translated)
        store.update_state(
            task.task_id,
            _state(
                current_stage,
                TaskStatus.RUNNING,
                1.0,
                task.trace_id,
                message="逐句翻译完成，等待下一阶段",
            ),
        )
        return PipelineResult(
            task_id=task.task_id,
            transcript_segments=len(transcript.segments),
            translated_segments=sum(
                bool((segment.translation or "").strip())
                for segment in translated.segments
            ),
            duration_ms=transcript.duration_ms,
        )
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
                stopped = (
                    isinstance(pipeline_failure, WorkerError)
                    and pipeline_failure.code is WorkerErrorCode.STOPPED
                )
                if not stopped:
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

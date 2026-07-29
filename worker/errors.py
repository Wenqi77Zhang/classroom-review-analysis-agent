"""Stable worker failures mapped to the platform error contract."""

from __future__ import annotations

from enum import StrEnum

from backend.app.schemas.common import ErrorCode


class WorkerErrorCode(StrEnum):
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    FFMPEG_NOT_FOUND = "FFMPEG_NOT_FOUND"
    AUDIO_EXTRACTION_FAILED = "AUDIO_EXTRACTION_FAILED"
    AUDIO_EXTRACTION_TIMEOUT = "AUDIO_EXTRACTION_TIMEOUT"
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"
    ASR_TIMEOUT = "ASR_TIMEOUT"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    TRANSCRIPT_SCHEMA_INVALID = "TRANSCRIPT_SCHEMA_INVALID"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    JOB_STORE_FAILED = "JOB_STORE_FAILED"
    STOPPED = "STOPPED"


_PUBLIC_MESSAGES: dict[WorkerErrorCode, str] = {
    WorkerErrorCode.INPUT_NOT_FOUND: "未找到可处理的课堂视频。",
    WorkerErrorCode.FFMPEG_NOT_FOUND: "媒体处理服务缺少 FFmpeg。",
    WorkerErrorCode.AUDIO_EXTRACTION_FAILED: "课堂视频音频抽取失败。",
    WorkerErrorCode.AUDIO_EXTRACTION_TIMEOUT: "课堂视频音频抽取超时。",
    WorkerErrorCode.ASR_UNAVAILABLE: "语音识别服务当前不可用。",
    WorkerErrorCode.ASR_TIMEOUT: "语音识别处理超时。",
    WorkerErrorCode.INVALID_TIMESTAMP: "语音识别结果包含无效时间范围。",
    WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID: "逐字稿结果未通过结构校验。",
    WorkerErrorCode.UPSTREAM_UNAVAILABLE: "上游处理服务当前不可用。",
    WorkerErrorCode.CLEANUP_FAILED: "临时媒体清理失败。",
    WorkerErrorCode.JOB_STORE_FAILED: "任务状态服务当前不可用。",
    WorkerErrorCode.STOPPED: "任务租约已停止，Worker 已放弃继续处理。",
}


def public_worker_error_message(code: WorkerErrorCode) -> str:
    """Return a stable public message without local diagnostics."""

    return _PUBLIC_MESSAGES[code]


class WorkerError(RuntimeError):
    def __init__(
        self,
        code: WorkerErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    @property
    def platform_code(self) -> ErrorCode:
        if self.code is WorkerErrorCode.INPUT_NOT_FOUND:
            return ErrorCode.RESOURCE_NOT_FOUND
        if self.code in {
            WorkerErrorCode.INVALID_TIMESTAMP,
            WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID,
        }:
            return ErrorCode.VALIDATION_ERROR
        if self.code in {
            WorkerErrorCode.FFMPEG_NOT_FOUND,
            WorkerErrorCode.ASR_UNAVAILABLE,
            WorkerErrorCode.ASR_TIMEOUT,
            WorkerErrorCode.UPSTREAM_UNAVAILABLE,
            WorkerErrorCode.JOB_STORE_FAILED,
        }:
            return ErrorCode.UPSTREAM_UNAVAILABLE
        return ErrorCode.INTERNAL_ERROR

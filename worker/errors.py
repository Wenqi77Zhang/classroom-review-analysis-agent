"""Stable worker failures mapped to the platform error contract."""

from __future__ import annotations

from enum import StrEnum

from backend.app.schemas.common import ErrorCode


class WorkerErrorCode(StrEnum):
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    MEDIA_INVALID = "MEDIA_INVALID"
    FFMPEG_UNAVAILABLE = "FFMPEG_UNAVAILABLE"
    FFMPEG_FAILED = "FFMPEG_FAILED"
    FFMPEG_TIMEOUT = "FFMPEG_TIMEOUT"
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"
    ASR_FAILED = "ASR_FAILED"
    TRANSCRIPT_EMPTY = "TRANSCRIPT_EMPTY"
    JOB_STORE_FAILED = "JOB_STORE_FAILED"


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
        if self.code in {WorkerErrorCode.MEDIA_INVALID, WorkerErrorCode.TRANSCRIPT_EMPTY}:
            return ErrorCode.VALIDATION_ERROR
        if self.code in {
            WorkerErrorCode.FFMPEG_UNAVAILABLE,
            WorkerErrorCode.ASR_UNAVAILABLE,
        }:
            return ErrorCode.UPSTREAM_UNAVAILABLE
        return ErrorCode.INTERNAL_ERROR

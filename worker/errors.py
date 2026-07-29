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

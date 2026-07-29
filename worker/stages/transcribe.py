"""Run ASR and convert its output into the frozen backend contract."""

from __future__ import annotations

import math
import wave
from pathlib import Path

from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.adapters.asr import AsrAdapter
from worker.errors import WorkerError, WorkerErrorCode


def _milliseconds(seconds: float) -> int:
    return round(seconds * 1000)


def _audio_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as audio:
            frame_rate = audio.getframerate()
            frame_count = audio.getnframes()
    except (OSError, EOFError, wave.Error) as exc:
        raise WorkerError(
            WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID,
            "无法从抽取音频读取真实时长。",
        ) from exc
    if frame_rate <= 0 or frame_count <= 0:
        raise WorkerError(
            WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID,
            "抽取音频的时长无效。",
        )
    return frame_count / frame_rate


def transcribe_audio(
    audio_path: Path,
    adapter: AsrAdapter,
    *,
    trace_id: str | None = None,
) -> InternalTranscriptWrite:
    duration_seconds = _audio_duration_seconds(audio_path)
    duration_ms = _milliseconds(duration_seconds)
    result = adapter.transcribe(audio_path)
    segments: list[InternalTranscriptSegmentWrite] = []
    previous_end_ms = 0
    for item in result.segments:
        if not math.isfinite(item.start_seconds) or not math.isfinite(item.end_seconds):
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 返回了非有限时间戳。",
            )
        if item.start_seconds < 0 or item.end_seconds < 0:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 时间戳不能为负数。",
            )
        if item.end_seconds <= item.start_seconds:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 片段结束时间必须大于开始时间。",
            )
        start_ms = _milliseconds(item.start_seconds)
        end_ms = _milliseconds(item.end_seconds)
        if end_ms <= start_ms:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 时间戳转换为毫秒后形成空区间。",
            )
        if start_ms < previous_end_ms:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 片段必须按时间单调且不能重叠。",
            )
        if end_ms > duration_ms:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "ASR 片段超出真实音频时长。",
            )
        segments.append(
            InternalTranscriptSegmentWrite(
                index=len(segments),
                start_ms=start_ms,
                end_ms=end_ms,
                speaker=None,
                text=item.text,
                translation=None,
            )
        )
        previous_end_ms = end_ms
    if not segments:
        raise WorkerError(
            WorkerErrorCode.TRANSCRIPT_SCHEMA_INVALID,
            "ASR 未返回任何有效逐字稿。",
        )
    return InternalTranscriptWrite(
        source_language=result.language,
        translation_language=None,
        duration_ms=duration_ms,
        segments=segments,
        trace_id=trace_id,
    )

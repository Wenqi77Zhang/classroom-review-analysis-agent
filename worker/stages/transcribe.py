"""Run ASR and convert its output into the frozen backend contract."""

from __future__ import annotations

from pathlib import Path

from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.adapters.asr import AsrAdapter
from worker.errors import WorkerError, WorkerErrorCode


def _milliseconds(seconds: float) -> int:
    return max(0, round(seconds * 1000))


def transcribe_audio(
    audio_path: Path,
    adapter: AsrAdapter,
    *,
    trace_id: str | None = None,
) -> InternalTranscriptWrite:
    result = adapter.transcribe(audio_path)
    segments: list[InternalTranscriptSegmentWrite] = []
    for item in result.segments:
        start_ms = _milliseconds(item.start_seconds)
        end_ms = max(start_ms + 1, _milliseconds(item.end_seconds))
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
    if not segments:
        raise WorkerError(WorkerErrorCode.TRANSCRIPT_EMPTY, "ASR 未返回任何有效逐字稿。")
    return InternalTranscriptWrite(
        source_language=result.language,
        translation_language=None,
        duration_ms=max(segment.end_ms for segment in segments),
        segments=segments,
        trace_id=trace_id,
    )

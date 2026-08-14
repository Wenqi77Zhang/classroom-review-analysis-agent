"""Import teacher-supplied Chinese subtitle cues as aligned translations."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.schemas.transcript import InternalTranscriptWrite
from worker.errors import WorkerError, WorkerErrorCode

_TIMING_LINE = re.compile(
    r"^(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)
_TAG = re.compile(r"<[^>]+>")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class TranslationCue:
    start_ms: int
    end_ms: int
    text: str


def _timestamp_ms(value: str) -> int:
    normalized = value.replace(",", ".")
    parts = normalized.split(":")
    if len(parts) == 2:
        hours = 0
        minutes_text, seconds_text = parts
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes_text, seconds_text = parts[1:]
    else:
        raise ValueError("invalid subtitle timestamp")
    seconds, milliseconds = seconds_text.split(".", 1)
    minutes = int(minutes_text)
    if minutes >= 60 or int(seconds) >= 60 or len(milliseconds) != 3:
        raise ValueError("invalid subtitle timestamp")
    return (((hours * 60) + minutes) * 60 + int(seconds)) * 1000 + int(milliseconds)


def parse_translation_subtitles(path: Path) -> tuple[TranslationCue, ...]:
    """Parse UTF-8 SRT/VTT whose cue bodies are Chinese translations."""

    if path.suffix.lower() not in {".srt", ".vtt"}:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
            "补充译文只支持带时间轴的 SRT 或 VTT 文件。",
        )
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
            "补充译文必须是 UTF-8 编码的 SRT 或 VTT 文件。",
        ) from exc

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[TranslationCue] = []
    index = 0
    while index < len(lines):
        timing = _TIMING_LINE.match(lines[index].strip())
        if timing is None:
            index += 1
            continue
        try:
            start_ms = _timestamp_ms(timing.group("start"))
            end_ms = _timestamp_ms(timing.group("end"))
        except (ValueError, TypeError) as exc:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "补充译文包含无效时间戳。",
            ) from exc
        if end_ms <= start_ms:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "补充译文片段结束时间必须晚于开始时间。",
            )
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip():
            cleaned = html.unescape(_TAG.sub("", lines[index])).strip()
            if cleaned:
                body.append(cleaned)
            index += 1
        text = " ".join(body).strip()
        if not text or _CJK.search(text) is None:
            raise WorkerError(
                WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
                "补充字幕的每个时间片段都必须包含中文译文。",
            )
        if cues and start_ms < cues[-1].end_ms:
            raise WorkerError(
                WorkerErrorCode.INVALID_TIMESTAMP,
                "补充译文时间片段必须按顺序排列且不能重叠。",
            )
        cues.append(TranslationCue(start_ms=start_ms, end_ms=end_ms, text=text))

    if not cues:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
            "补充译文中没有可读取的时间片段。",
        )
    return tuple(cues)


def align_supplemental_translations(
    transcript: InternalTranscriptWrite,
    subtitle_path: Path,
) -> InternalTranscriptWrite:
    """Attach translations by real timestamp overlap; reject incomplete coverage."""

    cues = parse_translation_subtitles(subtitle_path)
    translated_segments = []
    missing_indexes: list[int] = []
    for segment in transcript.segments:
        overlaps = [
            (
                min(segment.end_ms, cue.end_ms)
                - max(segment.start_ms, cue.start_ms),
                cue.text,
            )
            for cue in cues
            if min(segment.end_ms, cue.end_ms) > max(segment.start_ms, cue.start_ms)
        ]
        best_overlap, translation = max(overlaps, default=(0, ""))
        if best_overlap * 2 < segment.end_ms - segment.start_ms:
            missing_indexes.append(segment.index)
            translated_segments.append(segment)
            continue
        translated_segments.append(
            segment.model_copy(update={"translation": translation})
        )

    if missing_indexes:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
            "补充译文未覆盖全部语音片段，请校对字幕时间轴后重新上传。",
        )
    return transcript.model_copy(
        update={
            "segments": translated_segments,
            "translation_language": "zh",
        },
        deep=True,
    )

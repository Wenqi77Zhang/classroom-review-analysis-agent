import wave
from pathlib import Path

import pytest

from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.errors import WorkerError, WorkerErrorCode
from worker.job_store import LocalJobStore
from worker.pipeline import run_pipeline
from worker.stages.import_translation import (
    align_supplemental_translations,
    parse_translation_subtitles,
)
from worker.types import AsrResult, AsrSegment, PipelineTask


class _EnglishAsr:
    def transcribe(self, _audio_path: Path) -> AsrResult:
        return AsrResult(
            language="en",
            segments=(
                AsrSegment(0.0, 1.8, "First explanation."),
                AsrSegment(1.8, 4.0, "Second explanation."),
            ),
        )


def _transcript() -> InternalTranscriptWrite:
    return InternalTranscriptWrite(
        source_language="en",
        duration_ms=4000,
        segments=[
            InternalTranscriptSegmentWrite(
                index=0,
                start_ms=0,
                end_ms=1800,
                text="First explanation.",
            ),
            InternalTranscriptSegmentWrite(
                index=1,
                start_ms=1800,
                end_ms=4000,
                text="Second explanation.",
            ),
        ],
    )


def test_parse_utf8_srt_and_align_every_asr_segment(tmp_path: Path) -> None:
    subtitle = tmp_path / "translation.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,900\n第一段中文译文。\n\n"
        "2\n00:00:01,900 --> 00:00:04,000\n第二段中文译文。\n",
        encoding="utf-8",
    )

    cues = parse_translation_subtitles(subtitle)
    aligned = align_supplemental_translations(_transcript(), subtitle)

    assert len(cues) == 2
    assert aligned.translation_language == "zh"
    assert [segment.translation for segment in aligned.segments] == [
        "第一段中文译文。",
        "第二段中文译文。",
    ]
    assert [segment.text for segment in aligned.segments] == [
        "First explanation.",
        "Second explanation.",
    ]


def test_parse_webvtt_strips_markup_without_losing_translation(tmp_path: Path) -> None:
    subtitle = tmp_path / "translation.vtt"
    subtitle.write_text(
        "WEBVTT\n\n00:00.000 --> 00:02.000\n<c.zh>第一段译文</c>\n\n"
        "00:02.000 --> 00:04.000\n第二段译文\n",
        encoding="utf-8",
    )

    cues = parse_translation_subtitles(subtitle)

    assert [cue.text for cue in cues] == ["第一段译文", "第二段译文"]


def test_alignment_rejects_incomplete_timeline_coverage(tmp_path: Path) -> None:
    subtitle = tmp_path / "incomplete.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,800\n只覆盖第一段。\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkerError) as raised:
        align_supplemental_translations(_transcript(), subtitle)

    assert raised.value.code is WorkerErrorCode.TRANSLATION_SCHEMA_INVALID
    assert "覆盖全部语音片段" in str(raised.value)


def test_subtitle_rejects_non_chinese_or_non_timed_input(tmp_path: Path) -> None:
    subtitle = tmp_path / "translation.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:04,000\nEnglish only.\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkerError) as raised:
        parse_translation_subtitles(subtitle)

    assert raised.value.code is WorkerErrorCode.TRANSLATION_SCHEMA_INVALID


def test_pipeline_consumes_supplement_and_persists_aligned_translation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "class.mp4"
    source.write_bytes(b"real-input-placeholder")
    subtitle = tmp_path / "translation.vtt"
    subtitle.write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.800\n第一段中文译文。\n\n"
        "00:01.800 --> 00:04.000\n第二段中文译文。\n",
        encoding="utf-8",
    )

    def fake_extract_audio(_source: Path, target: Path) -> None:
        with wave.open(str(target), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\0\0" * 8000 * 4)

    monkeypatch.setattr("worker.pipeline.extract_audio", fake_extract_audio)
    store = LocalJobStore()
    task = PipelineTask(input_path=source)

    result = run_pipeline(
        task,
        _EnglishAsr(),
        store,
        supplemental_translation_path=subtitle,
    )

    assert result.translated_segments == 2
    assert store.transcripts[task.task_id].translation_language == "zh"
    assert store.events[task.task_id][-1].stage.value == "translate"
    assert store.events[task.task_id][-1].progress == 1.0

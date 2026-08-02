from __future__ import annotations

import threading

import pytest

from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.errors import WorkerError, WorkerErrorCode, public_worker_error_message
from worker.stages.translate import detect_language, translate_transcript
from worker.types import DetectedLanguage, TranslationBatch


class FakeTranslationAdapter:
    model_name = "fake-translation-for-tests"

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str, str]] = []

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch:
        self.calls.append((texts, source_language, target_language))
        return TranslationBatch(
            translations=tuple(f"[测试译文]{text}" for text in texts),
            model_name=self.model_name,
        )


def _transcript(
    *texts: str,
    source_language: str = "en-zh",
) -> InternalTranscriptWrite:
    return InternalTranscriptWrite(
        source_language=source_language,
        duration_ms=len(texts) * 1000,
        trace_id="trace-translation-test",
        segments=[
            InternalTranscriptSegmentWrite(
                index=index,
                start_ms=index * 1000,
                end_ms=(index + 1) * 1000,
                text=text,
            )
            for index, text in enumerate(texts)
        ],
    )


def test_translation_adapter_preserves_batch_order() -> None:
    result = FakeTranslationAdapter().translate_batch(
        ("first", "second"),
        source_language="en",
        target_language="zh",
    )

    assert result.translations == ("[测试译文]first", "[测试译文]second")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("这是中文课堂。", DetectedLanguage.ZH),
        ("This is an AI lecture.", DetectedLanguage.EN),
        ("我们使用 Transformer model。", DetectedLanguage.MIXED),
        ("1234…", DetectedLanguage.OTHER),
    ],
)
def test_detect_language(text: str, expected: DetectedLanguage) -> None:
    assert detect_language(text) is expected


def test_translate_transcript_preserves_original_fields_and_alignment() -> None:
    original = _transcript(
        "这是中文。",
        "Explain the model.",
        "这是 Transformer architecture.",
    )
    adapter = FakeTranslationAdapter()

    translated = translate_transcript(original, adapter)

    assert translated.segments[0].translation is None
    assert translated.segments[1].translation == "[测试译文]Explain the model."
    assert (
        translated.segments[2].translation
        == "[测试译文]这是 Transformer architecture."
    )
    assert [segment.text for segment in translated.segments] == [
        segment.text for segment in original.segments
    ]
    assert [
        (segment.index, segment.start_ms, segment.end_ms, segment.speaker)
        for segment in translated.segments
    ] == [
        (segment.index, segment.start_ms, segment.end_ms, segment.speaker)
        for segment in original.segments
    ]
    assert translated.translation_language == "zh"
    assert adapter.calls == [
        (
            ("Explain the model.", "这是 Transformer architecture."),
            "en",
            "zh",
        )
    ]


def test_chinese_only_transcript_skips_adapter() -> None:
    original = _transcript("第一句。", "第二句。", source_language="zh")
    adapter = FakeTranslationAdapter()

    translated = translate_transcript(original, adapter)

    assert translated == original
    assert translated is not original
    assert adapter.calls == []


def test_translation_is_required_for_english_without_adapter() -> None:
    with pytest.raises(WorkerError) as raised:
        translate_transcript(_transcript("Explain AI.", source_language="en"), None)

    assert raised.value.code is WorkerErrorCode.TRANSLATION_UNAVAILABLE
    assert raised.value.retryable is True


class FixedOutputAdapter(FakeTranslationAdapter):
    def __init__(self, output: tuple[str, ...]) -> None:
        super().__init__()
        self.output = output

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch:
        self.calls.append((texts, source_language, target_language))
        return TranslationBatch(
            translations=self.output,
            model_name=self.model_name,
        )


@pytest.mark.parametrize("output", [(), ("",), ("   ",)])
def test_translation_rejects_missing_or_blank_output(output: tuple[str, ...]) -> None:
    with pytest.raises(WorkerError) as raised:
        translate_transcript(
            _transcript("Explain AI.", source_language="en"),
            FixedOutputAdapter(output),
        )

    assert raised.value.code is WorkerErrorCode.TRANSLATION_SCHEMA_INVALID
    assert raised.value.retryable is False


def test_translation_rejects_unsupported_segment_in_bilingual_transcript() -> None:
    with pytest.raises(WorkerError) as raised:
        translate_transcript(
            _transcript("Explain AI.", "1234…", source_language="en"),
            FakeTranslationAdapter(),
        )

    assert raised.value.code is WorkerErrorCode.UNSUPPORTED_LANGUAGE


def test_translation_stop_before_adapter_makes_no_call() -> None:
    stop = threading.Event()
    stop.set()
    adapter = FakeTranslationAdapter()

    with pytest.raises(WorkerError) as raised:
        translate_transcript(
            _transcript("Explain AI.", source_language="en"),
            adapter,
            stop_event=stop,
        )

    assert raised.value.code is WorkerErrorCode.STOPPED
    assert adapter.calls == []


def test_translation_stop_after_adapter_discards_output() -> None:
    stop = threading.Event()

    class StopAfterTranslation(FakeTranslationAdapter):
        def translate_batch(
            self,
            texts: tuple[str, ...],
            *,
            source_language: str,
            target_language: str,
        ) -> TranslationBatch:
            result = super().translate_batch(
                texts,
                source_language=source_language,
                target_language=target_language,
            )
            stop.set()
            return result

    with pytest.raises(WorkerError) as raised:
        translate_transcript(
            _transcript("Explain AI.", source_language="en"),
            StopAfterTranslation(),
            stop_event=stop,
        )

    assert raised.value.code is WorkerErrorCode.STOPPED


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (TimeoutError("private input text"), WorkerErrorCode.TRANSLATION_TIMEOUT),
        (RuntimeError("private input text"), WorkerErrorCode.TRANSLATION_UNAVAILABLE),
    ],
)
def test_translation_maps_adapter_errors_without_exposing_input(
    failure: Exception,
    expected_code: WorkerErrorCode,
) -> None:
    class FailingAdapter(FakeTranslationAdapter):
        def translate_batch(
            self,
            texts: tuple[str, ...],
            *,
            source_language: str,
            target_language: str,
        ) -> TranslationBatch:
            raise failure

    with pytest.raises(WorkerError) as raised:
        translate_transcript(
            _transcript("secret lesson text", source_language="en"),
            FailingAdapter(),
        )

    assert raised.value.code is expected_code
    assert "secret lesson text" not in str(raised.value)
    assert "private input text" not in str(raised.value)


@pytest.mark.parametrize(
    "code",
    [
        WorkerErrorCode.TRANSLATION_UNAVAILABLE,
        WorkerErrorCode.TRANSLATION_TIMEOUT,
        WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
        WorkerErrorCode.UNSUPPORTED_LANGUAGE,
    ],
)
def test_translation_public_messages_are_stable_and_private(
    code: WorkerErrorCode,
) -> None:
    message = public_worker_error_message(code)

    assert message
    assert "http" not in message
    assert "/" not in message
    assert "secret lesson text" not in message

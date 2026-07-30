"""Deterministic language detection and aligned transcript translation."""

from __future__ import annotations

import re
from threading import Event

from backend.app.schemas.transcript import InternalTranscriptWrite
from worker.adapters.translation import TranslationAdapter
from worker.errors import WorkerError, WorkerErrorCode
from worker.types import DetectedLanguage

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> DetectedLanguage:
    """Classify only evidence-visible CJK and ASCII Latin characters."""

    has_cjk = _CJK_PATTERN.search(text) is not None
    has_latin = _LATIN_PATTERN.search(text) is not None
    if has_cjk and has_latin:
        return DetectedLanguage.MIXED
    if has_cjk:
        return DetectedLanguage.ZH
    if has_latin:
        return DetectedLanguage.EN
    return DetectedLanguage.OTHER


def _raise_if_stopped(stop_event: Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise WorkerError(
            WorkerErrorCode.STOPPED,
            "任务租约已停止，放弃翻译或写入译文。",
            retryable=True,
        )


def translate_transcript(
    transcript: InternalTranscriptWrite,
    adapter: TranslationAdapter | None,
    *,
    stop_event: Event | None = None,
) -> InternalTranscriptWrite:
    """Return a validated copy with Chinese translations aligned by segment."""

    _raise_if_stopped(stop_event)
    languages = tuple(detect_language(segment.text) for segment in transcript.segments)
    bilingual_required = any(
        language in {DetectedLanguage.EN, DetectedLanguage.MIXED}
        for language in languages
    ) or transcript.source_language.lower() in {"en", "en-zh", "zh-en"}

    if bilingual_required and DetectedLanguage.OTHER in languages:
        raise WorkerError(
            WorkerErrorCode.UNSUPPORTED_LANGUAGE,
            "双语逐字稿包含无法确定语言的片段。",
            retryable=False,
        )

    target_indexes = tuple(
        index
        for index, (segment, language) in enumerate(zip(transcript.segments, languages))
        if language in {DetectedLanguage.EN, DetectedLanguage.MIXED}
        and not (segment.translation or "").strip()
    )
    if not target_indexes:
        translation_language = "zh" if bilingual_required else transcript.translation_language
        return transcript.model_copy(
            update={"translation_language": translation_language},
            deep=True,
        )

    if adapter is None:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_UNAVAILABLE,
            "英文或中英混合逐字稿没有可用翻译适配器。",
            retryable=True,
        )

    texts = tuple(transcript.segments[index].text for index in target_indexes)
    try:
        batch = adapter.translate_batch(
            texts,
            source_language="en",
            target_language="zh",
        )
    except WorkerError:
        raise
    except TimeoutError:
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_TIMEOUT,
            "翻译适配器处理超时。",
            retryable=True,
        ) from None
    except Exception:  # noqa: BLE001 - provider exceptions must cross a private boundary
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_UNAVAILABLE,
            "翻译适配器当前不可用。",
            retryable=True,
        ) from None

    _raise_if_stopped(stop_event)
    if (
        len(batch.translations) != len(texts)
        or not batch.model_name.strip()
        or any(not translation.strip() for translation in batch.translations)
    ):
        raise WorkerError(
            WorkerErrorCode.TRANSLATION_SCHEMA_INVALID,
            "翻译结果数量、模型标识或正文不符合逐句对齐契约。",
            retryable=False,
        )

    translated_by_index = dict(zip(target_indexes, batch.translations))
    segments = [
        segment.model_copy(
            update={"translation": translated_by_index.get(index, segment.translation)}
        )
        for index, segment in enumerate(transcript.segments)
    ]
    return transcript.model_copy(
        update={
            "segments": segments,
            "translation_language": "zh",
        },
        deep=True,
    )

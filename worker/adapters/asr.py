"""ASR adapter boundary and a local Whisper implementation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Protocol

from worker.errors import WorkerError, WorkerErrorCode
from worker.types import AsrResult, AsrSegment


class AsrAdapter(Protocol):
    def transcribe(self, audio_path: Path) -> AsrResult: ...


def _is_repetitive_hallucination(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    text = str(item.get("text", "")).strip()
    try:
        duration = float(item["end"]) - float(item["start"])
    except (KeyError, TypeError, ValueError):
        return False
    if duration <= 0 or len(text) / duration < 25:
        return False
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    longest = max(tokens, key=len, default="")
    if len(longest) < 128 or len(set(longest)) / len(longest) > 0.1:
        return False
    trigrams = [longest[index : index + 3] for index in range(len(longest) - 2)]
    repeated_ratio = 1 - (len(set(trigrams)) / len(trigrams)) if trigrams else 0
    return repeated_ratio >= 0.9


class LocalWhisperAdapter:
    """Load the model only when the first task is transcribed."""

    def __init__(self, model_name: str = "tiny", *, language: str | None = None) -> None:
        self.model_name = model_name
        self.language = language
        self._model: object | None = None

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            import whisper
        except ImportError as exc:
            raise WorkerError(
                WorkerErrorCode.ASR_UNAVAILABLE,
                "未安装本地 Whisper 依赖。",
                retryable=True,
            ) from exc
        try:
            self._model = whisper.load_model(self.model_name)
        except Exception as exc:
            raise WorkerError(
                WorkerErrorCode.ASR_UNAVAILABLE,
                f"Whisper 模型 {self.model_name!r} 加载失败。",
                retryable=True,
            ) from exc
        return self._model

    def transcribe(self, audio_path: Path) -> AsrResult:
        model = self._load_model()
        try:
            raw = model.transcribe(
                str(audio_path),
                language=self.language,
                fp16=False,
                verbose=False,
                # A temperature tuple enables fallback sampling and can change
                # segment boundaries between identical runs. Evidence timestamps
                # must be reproducible, so use deterministic greedy decoding.
                temperature=0.0,
                # Long-form context can repeat the final prompt into padded
                # silence and emit timestamps past the real WAV duration.
                condition_on_previous_text=False,
            )
        except Exception as exc:
            raise WorkerError(
                WorkerErrorCode.UPSTREAM_UNAVAILABLE,
                "Whisper 识别失败。",
                retryable=True,
            ) from exc

        segments: list[AsrSegment] = []
        filtered_segments = 0
        for item in raw.get("segments", []):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            if _is_repetitive_hallucination(item):
                filtered_segments += 1
                continue
            segments.append(
                AsrSegment(
                    start_seconds=float(item["start"]),
                    end_seconds=float(item["end"]),
                    text=str(item["text"]).strip(),
                )
            )
        if filtered_segments:
            print(
                f"Whisper 质量门禁已排除 {filtered_segments} 个高度重复的疑似幻觉片段。",
                file=sys.stderr,
                flush=True,
            )
        return AsrResult(
            language=str(raw.get("language") or self.language or "und"),
            segments=tuple(segments),
        )

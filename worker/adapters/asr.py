"""ASR adapter boundary and a local Whisper implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from worker.errors import WorkerError, WorkerErrorCode
from worker.types import AsrResult, AsrSegment


class AsrAdapter(Protocol):
    def transcribe(self, audio_path: Path) -> AsrResult: ...


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
            )
        except Exception as exc:
            raise WorkerError(
                WorkerErrorCode.ASR_FAILED,
                "Whisper 识别失败。",
                retryable=True,
            ) from exc

        segments = tuple(
            AsrSegment(
                start_seconds=float(item["start"]),
                end_seconds=float(item["end"]),
                text=str(item["text"]).strip(),
            )
            for item in raw.get("segments", [])
            if str(item.get("text", "")).strip()
        )
        return AsrResult(language=str(raw.get("language") or self.language or "und"), segments=segments)

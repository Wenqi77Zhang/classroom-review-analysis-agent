"""Construct the configured translation adapter without importing the worker runtime."""

from __future__ import annotations

import os

from worker.adapters.local_translation import LocalModelTranslationAdapter
from worker.adapters.translation import TranslationAdapter


def build_translation_adapter_from_env() -> TranslationAdapter | None:
    """Build the host-local automatic translator; teacher VTT still takes priority."""

    provider = os.getenv("TRANSLATION_PROVIDER", "local_model").strip().lower()
    if provider in {"", "none", "disabled"}:
        return None
    if provider != "local_model":
        raise ValueError("TRANSLATION_PROVIDER 当前只支持 local_model、none 或 disabled。")
    endpoint = (
        os.getenv("TRANSLATION_MODEL_CHAT_COMPLETIONS_URL", "").strip()
        or os.getenv(
            "LOCAL_MODEL_CHAT_COMPLETIONS_URL",
            "http://127.0.0.1:11434/v1/chat/completions",
        ).strip()
    )
    model = (
        os.getenv("TRANSLATION_MODEL_NAME", "").strip()
        or os.getenv("LOCAL_MODEL_NAME", "qwen3.5:4b").strip()
    )
    return LocalModelTranslationAdapter(
        endpoint=endpoint,
        model=model,
        timeout_seconds=float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "120")),
        batch_size=int(os.getenv("TRANSLATION_BATCH_SIZE", "8")),
    )

"""Provider-neutral translation adapter contract."""

from __future__ import annotations

from typing import Protocol

from worker.types import TranslationBatch


class TranslationAdapter(Protocol):
    """Translate an aligned batch without receiving task or database objects."""

    model_name: str

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch: ...

"""Immutable values passed between courseware and evidence stages."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CoursewarePage:
    page_no: int
    text: str

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError("page_no must be one-based")


@dataclass(frozen=True, slots=True)
class CoursewareDocument:
    asset_id: UUID
    pages: tuple[CoursewarePage, ...]

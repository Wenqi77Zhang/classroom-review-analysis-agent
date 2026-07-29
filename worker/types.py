"""Small internal types used between worker stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True, slots=True)
class AsrResult:
    language: str
    segments: tuple[AsrSegment, ...]


@dataclass(frozen=True, slots=True)
class PipelineTask:
    input_path: Path
    task_id: UUID = field(default_factory=uuid4)
    trace_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True, slots=True)
class PipelineResult:
    task_id: UUID
    transcript_segments: int
    duration_ms: int

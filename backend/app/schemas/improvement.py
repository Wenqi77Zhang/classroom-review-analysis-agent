"""M2 improvement cycles and M3 portfolio schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from backend.app.schemas.analysis_report import EvidenceReference, ReviewAction, ReviewStatus
from backend.app.schemas.common import ApiModel, OrmModel, ResourceId

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ValidationMode(StrEnum):
    REAL = "real"
    SYNTHETIC = "synthetic"


class CycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIONS_READY = "actions_ready"
    FOLLOWUP_LINKED = "followup_linked"
    READY_TO_COMPARE = "ready_to_compare"
    REVIEWING = "reviewing"
    COMPLETED = "completed"


class ActionProgress(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DROPPED = "dropped"


class ComparisonOutcome(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ImprovementCycleCreate(ApiModel):
    baseline_classroom_id: ResourceId
    title: NonBlank = Field(max_length=255)
    objective: NonBlank = Field(max_length=4000)
    validation_mode: ValidationMode = ValidationMode.REAL


class ImprovementCycleUpdate(ApiModel):
    title: NonBlank | None = Field(default=None, max_length=255)
    objective: NonBlank | None = Field(default=None, max_length=4000)
    followup_classroom_id: ResourceId | None = None

    @model_validator(mode="after")
    def require_change(self) -> ImprovementCycleUpdate:
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要修改的字段。")
        return self


class ImprovementActionCreate(ApiModel):
    source_conclusion_id: ResourceId
    action_text: NonBlank = Field(max_length=4000)
    success_criterion: NonBlank = Field(max_length=2000)
    priority: int = Field(default=2, ge=1, le=3)


class ImprovementActionUpdate(ApiModel):
    action_text: NonBlank | None = Field(default=None, max_length=4000)
    success_criterion: NonBlank | None = Field(default=None, max_length=2000)
    priority: int | None = Field(default=None, ge=1, le=3)
    progress: ActionProgress | None = None

    @model_validator(mode="after")
    def require_change(self) -> ImprovementActionUpdate:
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要修改的字段。")
        return self


class ImprovementActionRead(OrmModel):
    id: ResourceId
    source_conclusion_id: ResourceId
    action_text: str
    success_criterion: str
    priority: int
    progress: ActionProgress
    created_at: datetime
    updated_at: datetime | None = None


class ImprovementComparisonRead(OrmModel):
    id: ResourceId
    action_id: ResourceId
    baseline_conclusion_id: ResourceId
    followup_conclusion_id: ResourceId | None
    proposed_outcome: ComparisonOutcome
    summary: str
    baseline_evidence: list[EvidenceReference]
    followup_evidence: list[EvidenceReference]
    review_status: ReviewStatus
    reviewed_summary: str | None = None
    trace_id: str
    skill: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime | None = None


class ComparisonReviewRequest(ApiModel):
    action: ReviewAction
    edited_summary: str | None = Field(default=None, max_length=6000)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_review(self) -> ComparisonReviewRequest:
        if self.action is ReviewAction.MODIFY and not (self.edited_summary or "").strip():
            raise ValueError("修改确认时必须提供 edited_summary。")
        return self


class ImprovementCycleRead(OrmModel):
    id: ResourceId
    course_id: ResourceId
    baseline_classroom_id: ResourceId
    followup_classroom_id: ResourceId | None
    title: str
    objective: str
    status: CycleStatus
    validation_mode: ValidationMode
    actions: list[ImprovementActionRead] = Field(default_factory=list)
    comparisons: list[ImprovementComparisonRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class PortfolioClassroomRead(ApiModel):
    id: ResourceId
    title: str
    latest_task_id: ResourceId | None = None
    task_count: int
    succeeded_task_count: int
    reviewed_conclusion_count: int
    report_ready: bool


class PortfolioCourseRead(ApiModel):
    id: ResourceId
    name: str
    classroom_count: int
    completed_cycle_count: int
    classrooms: list[PortfolioClassroomRead]


class PortfolioOverview(ApiModel):
    course_count: int
    classroom_count: int
    completed_cycle_count: int
    courses: list[PortfolioCourseRead]


class AggregateReportRead(ApiModel):
    title: str
    content: str
    included_cycle_ids: list[ResourceId]
    generated_at: datetime
    evidence_boundary: str

"""Persistence for M2 improvement cycles and evidence comparisons."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.schemas.analysis_report import ReviewStatus
from backend.app.schemas.improvement import (
    ActionProgress,
    ComparisonOutcome,
    CycleStatus,
    ValidationMode,
)


class ImprovementCycle(Base):
    __tablename__ = "improvement_cycles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    baseline_classroom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    followup_classroom_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[CycleStatus] = mapped_column(String(32), default=CycleStatus.DRAFT, index=True)
    validation_mode: Mapped[ValidationMode] = mapped_column(String(16), default=ValidationMode.REAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    actions: Mapped[list[ImprovementAction]] = relationship(back_populates="cycle", cascade="all, delete-orphan", order_by="ImprovementAction.created_at")
    comparisons: Mapped[list[ImprovementComparison]] = relationship(back_populates="cycle", cascade="all, delete-orphan", order_by="ImprovementComparison.created_at", overlaps="comparisons")
    __table_args__ = (
        ForeignKeyConstraint(["course_id", "owner_id"], ["courses.id", "courses.owner_id"], name="fk_improvement_cycles_course_owner", ondelete="CASCADE"),
        ForeignKeyConstraint(["baseline_classroom_id", "owner_id"], ["classrooms.id", "classrooms.owner_id"], name="fk_improvement_cycles_baseline_owner", ondelete="RESTRICT"),
        ForeignKeyConstraint(["followup_classroom_id", "owner_id"], ["classrooms.id", "classrooms.owner_id"], name="fk_improvement_cycles_followup_owner", ondelete="RESTRICT"),
        UniqueConstraint("id", "owner_id", name="uq_improvement_cycles_id_owner"),
    )


class ImprovementAction(Base):
    __tablename__ = "improvement_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source_conclusion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    action_text: Mapped[str] = mapped_column(Text)
    success_criterion: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    progress: Mapped[ActionProgress] = mapped_column(String(32), default=ActionProgress.PLANNED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    cycle: Mapped[ImprovementCycle] = relationship(back_populates="actions")
    comparisons: Mapped[list[ImprovementComparison]] = relationship(back_populates="action", overlaps="comparisons")
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 3", name="ck_improvement_action_priority"),
        ForeignKeyConstraint(["cycle_id", "owner_id"], ["improvement_cycles.id", "improvement_cycles.owner_id"], name="fk_improvement_actions_cycle_owner", ondelete="CASCADE"),
        ForeignKeyConstraint(["source_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_actions_conclusion_owner", ondelete="RESTRICT"),
        UniqueConstraint("id", "owner_id", name="uq_improvement_actions_id_owner"),
        UniqueConstraint("cycle_id", "source_conclusion_id", name="uq_improvement_action_source"),
    )


class ImprovementComparison(Base):
    __tablename__ = "improvement_comparisons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    baseline_conclusion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    followup_conclusion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    proposed_outcome: Mapped[ComparisonOutcome] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    baseline_evidence: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    followup_evidence: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    review_status: Mapped[ReviewStatus] = mapped_column(String(32), default=ReviewStatus.PENDING, index=True)
    reviewed_summary: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    skill: Mapped[str] = mapped_column(String(64), default="evidence-comparison")
    prompt_version: Mapped[str] = mapped_column(String(64), default="comparison-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    cycle: Mapped[ImprovementCycle] = relationship(back_populates="comparisons", overlaps="comparisons")
    action: Mapped[ImprovementAction] = relationship(back_populates="comparisons", overlaps="comparisons,cycle")
    __table_args__ = (
        ForeignKeyConstraint(["cycle_id", "owner_id"], ["improvement_cycles.id", "improvement_cycles.owner_id"], name="fk_improvement_comparisons_cycle_owner", ondelete="CASCADE"),
        ForeignKeyConstraint(["action_id", "owner_id"], ["improvement_actions.id", "improvement_actions.owner_id"], name="fk_improvement_comparisons_action_owner", ondelete="CASCADE"),
        ForeignKeyConstraint(["baseline_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_comparisons_baseline_owner", ondelete="RESTRICT"),
        ForeignKeyConstraint(["followup_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_comparisons_followup_owner", ondelete="RESTRICT"),
        UniqueConstraint("id", "owner_id", name="uq_improvement_comparisons_id_owner"),
        UniqueConstraint("cycle_id", "action_id", name="uq_improvement_comparison_action"),
    )

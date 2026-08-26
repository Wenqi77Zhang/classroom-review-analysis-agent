"""Assets, processing tasks, events, and transcript persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import AssetKind, PrivacyMode, TaskStage, TaskStatus, UploadStatus

task_assets = Table(
    "task_assets",
    Base.metadata,
    Column(
        "task_id",
        UUID(as_uuid=True),
        primary_key=True,
    ),
    Column(
        "asset_id",
        UUID(as_uuid=True),
        primary_key=True,
    ),
    Column("owner_id", UUID(as_uuid=True), nullable=False),
    ForeignKeyConstraint(
        ["task_id", "owner_id"],
        ["processing_tasks.id", "processing_tasks.owner_id"],
        name="fk_task_assets_task_owner",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["asset_id", "owner_id"],
        ["assets.id", "assets.owner_id"],
        name="fk_task_assets_asset_owner",
        ondelete="CASCADE",
    ),
)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[AssetKind] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column()
    upload_status: Mapped[UploadStatus] = mapped_column(String(32), default=UploadStatus.PENDING)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    etag: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    classroom: Mapped[Classroom] = relationship(back_populates="assets")
    tasks: Mapped[list[ProcessingTask]] = relationship(
        secondary=task_assets, back_populates="assets"
    )

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_assets_size_positive"),
        ForeignKeyConstraint(
            ["classroom_id", "owner_id"],
            ["classrooms.id", "classrooms.owner_id"],
            name="fk_assets_classroom_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_id", name="uq_assets_id_owner"),
    )


class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    classroom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[TaskStatus] = mapped_column(String(32), default=TaskStatus.PENDING, index=True)
    stage: Mapped[TaskStage] = mapped_column(String(64), default=TaskStage.UPLOADED, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    privacy_mode: Mapped[PrivacyMode] = mapped_column(String(16), default=PrivacyMode.LOCAL)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    analysis_contract: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    transcript_duration_ms: Mapped[int | None] = mapped_column(Integer)
    last_error_code: Mapped[ErrorCode | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    classroom: Mapped[Classroom] = relationship(back_populates="tasks")
    assets: Mapped[list[Asset]] = relationship(secondary=task_assets, back_populates="tasks")
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.created_at"
    )
    transcript_segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TranscriptSegment.index"
    )
    courseware_pages: Mapped[list[CoursewarePage]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CoursewarePage.asset_id, CoursewarePage.page_no",
    )

    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 1", name="ck_tasks_progress_range"),
        CheckConstraint("retry_count >= 0", name="ck_tasks_retry_nonnegative"),
        CheckConstraint(
            "transcript_duration_ms IS NULL OR transcript_duration_ms >= 0",
            name="ck_tasks_transcript_duration_nonnegative",
        ),
        ForeignKeyConstraint(
            ["classroom_id", "owner_id"],
            ["classrooms.id", "classrooms.owner_id"],
            name="fk_processing_tasks_classroom_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_id", name="uq_processing_tasks_id_owner"),
    )


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    stage: Mapped[TaskStage] = mapped_column(String(64))
    status: Mapped[TaskStatus] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[ErrorCode | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    task: Mapped[ProcessingTask] = relationship(back_populates="events")
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 1", name="ck_task_events_progress_range"),
        ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["processing_tasks.id", "processing_tasks.owner_id"],
            name="fk_task_events_task_owner",
            ondelete="CASCADE",
        ),
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    index: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(String(16))
    translation: Mapped[str | None] = mapped_column(Text)
    translation_language: Mapped[str | None] = mapped_column(String(16))
    is_edited: Mapped[bool] = mapped_column(default=False, server_default="false")
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[ProcessingTask] = relationship(back_populates="transcript_segments")
    revisions: Mapped[list[TranscriptSegmentRevision]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("task_id", "index", name="uq_transcript_task_index"),
        CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_transcript_valid_range"),
        ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["processing_tasks.id", "processing_tasks.owner_id"],
            name="fk_transcript_segments_task_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_id", name="uq_transcript_segments_id_owner"),
    )


class TranscriptSegmentRevision(Base):
    __tablename__ = "transcript_segment_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    previous_text: Mapped[str | None] = mapped_column(Text)
    previous_speaker: Mapped[str | None] = mapped_column(String(64))
    previous_translation: Mapped[str | None] = mapped_column(Text)
    edited_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    segment: Mapped[TranscriptSegment] = relationship(back_populates="revisions")
    edited_by: Mapped[User] = relationship(foreign_keys=[edited_by_id])
    __table_args__ = (
        ForeignKeyConstraint(
            ["segment_id", "owner_id"],
            ["transcript_segments.id", "transcript_segments.owner_id"],
            name="fk_transcript_revisions_segment_owner",
            ondelete="CASCADE",
        ),
    )


class CoursewarePage(Base):
    """Extracted page text scoped to both a task and its attached courseware asset."""

    __tablename__ = "courseware_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[ProcessingTask] = relationship(back_populates="courseware_pages")

    __table_args__ = (
        UniqueConstraint("task_id", "asset_id", "page_no", name="uq_courseware_task_asset_page"),
        UniqueConstraint("id", "owner_id", name="uq_courseware_pages_id_owner"),
        CheckConstraint("page_no >= 1", name="ck_courseware_page_positive"),
        CheckConstraint("length(trim(text)) > 0", name="ck_courseware_page_text_nonempty"),
        ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["processing_tasks.id", "processing_tasks.owner_id"],
            name="fk_courseware_pages_task_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["asset_id", "owner_id"],
            ["assets.id", "assets.owner_id"],
            name="fk_courseware_pages_asset_owner",
            ondelete="CASCADE",
        ),
    )


from backend.app.models.identity import Classroom, User

"""Identity, course, and classroom persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auth_version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    courses: Mapped[list[Course]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    owner: Mapped[User] = relationship(back_populates="courses")
    classrooms: Mapped[list[Classroom]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        foreign_keys="Classroom.course_id",
    )
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_courses_id_owner"),
    )


class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    analysis_contract: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    owner: Mapped[User] = relationship()
    course: Mapped[Course] = relationship(
        back_populates="classrooms", foreign_keys=[course_id]
    )
    assets: Mapped[list[Asset]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[ProcessingTask]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan"
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "owner_id"],
            ["courses.id", "courses.owner_id"],
            name="fk_classrooms_course_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_id", name="uq_classrooms_id_owner"),
    )


from backend.app.models.processing import Asset, ProcessingTask

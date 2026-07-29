"""Owner-scoped processing task and append-only event persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.errors import NotFoundError, StateConflictError, ValidationFailedError
from backend.app.models import Asset, Classroom, ProcessingTask, TaskEvent
from backend.app.models.processing import task_assets
from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import (
    PrivacyMode,
    TaskStage,
    TaskStatus,
    UploadStatus,
)
from backend.app.services.permissions import get_owned_or_404


async def append_task_event(
    session: AsyncSession,
    task: ProcessingTask,
    *,
    message: str | None = None,
    error_code: ErrorCode | None = None,
) -> TaskEvent:
    event = TaskEvent(
        owner_id=task.owner_id,
        task_id=task.id,
        stage=task.stage,
        status=task.status,
        progress=task.progress,
        message=message,
        error_code=error_code,
        trace_id=task.trace_id,
    )
    session.add(event)
    await session.flush()
    return event


async def create_processing_task(
    session: AsyncSession,
    *,
    owner_id: UUID,
    classroom_id: UUID,
    asset_ids: list[UUID],
    privacy_mode: PrivacyMode,
    analysis_contract: dict[str, object],
    trace_id: str,
) -> ProcessingTask:
    classroom = await get_owned_or_404(session, Classroom, classroom_id, owner_id)
    if len(set(asset_ids)) != len(asset_ids):
        raise ValidationFailedError("asset_ids 不允许重复。")

    rows = list(
        await session.scalars(
            select(Asset).where(Asset.owner_id == owner_id, Asset.id.in_(asset_ids))
        )
    )
    if len(rows) != len(asset_ids):
        raise NotFoundError()
    if any(row.classroom_id != classroom_id for row in rows):
        raise NotFoundError()
    if any(UploadStatus(row.upload_status) is not UploadStatus.UPLOADED for row in rows):
        raise StateConflictError("所有文件通过上传核验后才能创建任务。")

    task = ProcessingTask(
        owner_id=owner_id,
        classroom_id=classroom_id,
        status=TaskStatus.QUEUED,
        stage=TaskStage.UPLOADED,
        progress=0.0,
        privacy_mode=privacy_mode,
        retry_count=0,
        analysis_contract=analysis_contract or classroom.analysis_contract,
        trace_id=trace_id,
    )
    session.add(task)
    await session.flush()
    await session.execute(
        insert(task_assets),
        [
            {"task_id": task.id, "asset_id": asset_id, "owner_id": owner_id}
            for asset_id in asset_ids
        ],
    )
    await append_task_event(session, task, message="任务已进入处理队列。")
    return task


async def list_tasks(
    session: AsyncSession,
    owner_id: UUID,
    *,
    classroom_id: UUID | None,
    limit: int,
    offset: int,
) -> list[ProcessingTask]:
    statement = select(ProcessingTask).where(ProcessingTask.owner_id == owner_id)
    if classroom_id is not None:
        await get_owned_or_404(session, Classroom, classroom_id, owner_id)
        statement = statement.where(ProcessingTask.classroom_id == classroom_id)
    rows = await session.scalars(
        statement.order_by(ProcessingTask.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows)


async def list_task_events(
    session: AsyncSession, owner_id: UUID, task_id: UUID
) -> list[TaskEvent]:
    await get_owned_or_404(session, ProcessingTask, task_id, owner_id)
    rows = await session.scalars(
        select(TaskEvent)
        .where(TaskEvent.owner_id == owner_id, TaskEvent.task_id == task_id)
        .order_by(TaskEvent.created_at, TaskEvent.id)
    )
    return list(rows)


async def get_task_assets(
    session: AsyncSession, task_id: UUID, owner_id: UUID
) -> list[Asset]:
    rows = await session.scalars(
        select(Asset)
        .join(task_assets, task_assets.c.asset_id == Asset.id)
        .where(task_assets.c.task_id == task_id, task_assets.c.owner_id == owner_id)
        .order_by(Asset.created_at, Asset.id)
    )
    return list(rows)


async def claim_task(
    session: AsyncSession,
    *,
    worker_id: str,
    stages: list[TaskStage],
    lease_seconds: int,
) -> tuple[ProcessingTask, list[Asset]] | None:
    now = datetime.now(UTC)
    task = await session.scalar(
        select(ProcessingTask)
        .where(
            ProcessingTask.stage.in_(stages),
            or_(
                ProcessingTask.status == TaskStatus.QUEUED,
                and_(
                    ProcessingTask.status == TaskStatus.RUNNING,
                    ProcessingTask.lease_expires_at.is_not(None),
                    ProcessingTask.lease_expires_at < now,
                ),
            ),
        )
        .order_by(ProcessingTask.created_at, ProcessingTask.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if task is None:
        return None

    reclaimed = TaskStatus(task.status) is TaskStatus.RUNNING
    task.status = TaskStatus.RUNNING
    task.claimed_by = worker_id
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    task.trace_id = task.trace_id or uuid.uuid4().hex
    await append_task_event(
        session,
        task,
        message="租约到期后重新领取。" if reclaimed else "Worker 已领取任务。",
    )
    return task, await get_task_assets(session, task.id, task.owner_id)


async def get_internal_task(session: AsyncSession, task_id: UUID) -> ProcessingTask:
    task = await session.get(ProcessingTask, task_id)
    if task is None:
        raise NotFoundError()
    return task

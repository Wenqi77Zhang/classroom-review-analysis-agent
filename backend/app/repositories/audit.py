"""Owner-scoped audit reads and idempotent Agent Trace persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.errors import NotFoundError, StateConflictError
from backend.app.models import AuditEvent, ProcessingTask
from backend.app.schemas.audit import InternalTraceEventWrite
from backend.app.schemas.task import ServiceIdentity
from backend.app.services.permissions import get_owned_or_404


async def persist_task_trace_event(
    session: AsyncSession,
    *,
    task_id: UUID,
    body: InternalTraceEventWrite,
) -> AuditEvent:
    task = await session.scalar(
        select(ProcessingTask)
        .where(ProcessingTask.id == task_id)
        .with_for_update()
    )
    if task is None:
        raise NotFoundError()
    if task.trace_id != body.trace_id:
        raise StateConflictError("Trace ID 与当前任务不一致。")

    details = body.audit_details()
    existing = await session.get(AuditEvent, body.event_id)
    if existing is not None:
        same_event = (
            existing.owner_id == task.owner_id
            and existing.actor_service == ServiceIdentity.AGENT.value
            and existing.action == body.name.value
            and existing.resource_type == "processing_task"
            and existing.resource_id == task.id
            and existing.trace_id == body.trace_id
            and existing.details == details
        )
        if not same_event:
            raise StateConflictError("event_id 已用于不同的 Trace 事件。")
        return existing

    event = AuditEvent(
        id=body.event_id,
        owner_id=task.owner_id,
        actor_service=ServiceIdentity.AGENT.value,
        action=body.name.value,
        resource_type="processing_task",
        resource_id=task.id,
        trace_id=body.trace_id,
        details=details,
    )
    session.add(event)
    await session.flush()
    return event


async def list_task_audit_events(
    session: AsyncSession,
    *,
    owner_id: UUID,
    task_id: UUID,
) -> list[AuditEvent]:
    task = await get_owned_or_404(session, ProcessingTask, task_id, owner_id)
    if task.trace_id is None:
        return []
    rows = await session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.owner_id == owner_id,
            AuditEvent.trace_id == task.trace_id,
            AuditEvent.resource_type == "processing_task",
            AuditEvent.resource_id == task.id,
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    return list(rows)

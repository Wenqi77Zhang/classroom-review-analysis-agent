"""Persistent Agent Trace writes and owner-scoped audit reads."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import (
    get_current_user,
    get_db,
    require_service_identity,
)
from backend.app.models import User
from backend.app.repositories.audit import (
    list_task_audit_events,
    persist_task_trace_event,
)
from backend.app.schemas.audit import AuditEventRead, InternalTraceEventWrite
from backend.app.schemas.task import ServiceIdentity

router = APIRouter(tags=["audit"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AgentTraceWriter = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:trace")),
]


@router.get("/tasks/{task_id}/audit-events", response_model=list[AuditEventRead])
async def get_task_audit_events(
    task_id: UUID,
    session: Db,
    user: CurrentUser,
) -> list[AuditEventRead]:
    return [
        AuditEventRead.model_validate(event)
        for event in await list_task_audit_events(
            session, owner_id=user.id, task_id=task_id
        )
    ]


@router.post(
    "/internal/tasks/{task_id}/trace-events",
    response_model=AuditEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_task_trace_event(
    task_id: UUID,
    body: InternalTraceEventWrite,
    session: Db,
    _identity: AgentTraceWriter,
) -> AuditEventRead:
    return AuditEventRead.model_validate(
        await persist_task_trace_event(session, task_id=task_id, body=body)
    )

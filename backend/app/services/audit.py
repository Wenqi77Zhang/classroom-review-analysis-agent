"""Persist allowlisted audit metadata without sensitive request content."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.errors import current_trace_id
from backend.app.models import AuditEvent


async def record_audit_event(
    session: AsyncSession,
    *,
    owner_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    actor_user_id: UUID | None = None,
    actor_service: str | None = None,
    details: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    """Append one event; callers pass only non-sensitive, allowlisted details."""

    if (actor_user_id is None) == (actor_service is None):
        raise ValueError("审计事件必须且只能提供一种操作身份。")
    effective_trace_id = trace_id or current_trace_id.get()
    event = AuditEvent(
        owner_id=owner_id,
        actor_user_id=actor_user_id,
        actor_service=actor_service,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        trace_id=None if effective_trace_id == "-" else effective_trace_id,
        details=details or {},
    )
    session.add(event)
    await session.flush()
    return event

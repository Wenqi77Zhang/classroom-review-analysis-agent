"""Allowlisted Agent Trace writes and teacher-visible audit events."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from backend.app.schemas.common import ApiModel, ErrorCode, OrmModel, ResourceId


class TraceEventName(StrEnum):
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"


class InternalTraceEventWrite(ApiModel):
    event_id: ResourceId = Field(description="Agent 生成的幂等键。")
    trace_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    name: TraceEventName
    stage: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    model_name: str | None = Field(default=None, max_length=128)
    skill: str | None = Field(default=None, max_length=64)
    prompt_version: str | None = Field(default=None, max_length=64)
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def _check_error_fields(self) -> InternalTraceEventWrite:
        if self.name is TraceEventName.AGENT_ERROR and self.error_code is None:
            raise ValueError("agent.error 必须提供稳定 error_code。")
        if self.name is not TraceEventName.AGENT_ERROR and self.error_code is not None:
            raise ValueError("只有 agent.error 可以携带 error_code。")
        return self

    def audit_details(self) -> dict[str, str | int]:
        return {
            key: value.value if isinstance(value, StrEnum) else value
            for key, value in self.model_dump(
                exclude={"event_id", "trace_id", "name"}, exclude_none=True
            ).items()
        }


class AuditEventRead(OrmModel):
    id: ResourceId
    actor_service: str | None = None
    action: str
    resource_type: str
    resource_id: ResourceId | None = None
    trace_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime

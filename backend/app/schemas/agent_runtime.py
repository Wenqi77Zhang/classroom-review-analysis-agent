"""后端与 Agent 运行器之间的最小权限任务契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from backend.app.schemas.analysis_report import EvidenceReference
from backend.app.schemas.common import ApiModel, OrmModel, ResourceId
from backend.app.schemas.task import AnalysisContract, PrivacyMode


class InternalAgentHandoff(ApiModel):
    """Worker 完成证据准备后释放租约并把任务交给 Agent。"""

    worker_id: str = Field(min_length=1, max_length=128)


class InternalAgentClaimRequest(ApiModel):
    agent_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=300, ge=30, le=3600)


class InternalAgentHeartbeat(ApiModel):
    agent_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=300, ge=30, le=3600)


class InternalAgentEvidence(OrmModel):
    """Agent 可读取的任务内证据；不包含对象存储密钥或无关课堂数据。"""

    id: ResourceId
    task_id: ResourceId
    owner_id: ResourceId
    reference: EvidenceReference
    text: str = Field(min_length=1, max_length=10000)
    translation: str | None = Field(default=None, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InternalAgentTaskClaim(OrmModel):
    task_id: ResourceId
    classroom_id: ResourceId
    owner_id: ResourceId
    privacy_mode: PrivacyMode
    analysis_contract: AnalysisContract
    evidence: list[InternalAgentEvidence] = Field(min_length=1, max_length=1000)
    lease_expires_at: datetime
    trace_id: str

"""Agent 内部契约；跨模块字段直接复用成员 3 冻结的后端 Schema。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from backend.app.schemas.analysis_report import (
    ConclusionType,
    EvidenceReference,
    InternalConclusionBatchWrite,
)
from backend.app.schemas.common import ApiModel, ResourceId
from backend.app.schemas.task import (
    AnalysisContract,
    AnalysisScope,
    CourseDomain,
)

__all__ = [
    "AnalysisContract",
    "AnalysisScope",
    "CourseDomain",
]


class AgentErrorCode(StrEnum):
    CONTRACT_UNCONFIRMED = "CONTRACT_UNCONFIRMED"
    SKILL_UNAVAILABLE = "SKILL_UNAVAILABLE"
    EVIDENCE_SCOPE_EMPTY = "EVIDENCE_SCOPE_EMPTY"
    EVIDENCE_OUT_OF_SCOPE = "EVIDENCE_OUT_OF_SCOPE"
    EVIDENCE_NOT_PROVIDED = "EVIDENCE_NOT_PROVIDED"
    BILINGUAL_EVIDENCE_INCOMPLETE = "BILINGUAL_EVIDENCE_INCOMPLETE"
    SKILL_NOT_IN_PLAN = "SKILL_NOT_IN_PLAN"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    AGENT_INTERNAL_ERROR = "AGENT_INTERNAL_ERROR"


class EvidenceItem(ApiModel):
    """Worker 证据索引交给 Agent 的最小任务内表示。"""

    id: ResourceId
    task_id: ResourceId
    owner_id: ResourceId
    reference: EvidenceReference
    text: str = Field(min_length=1, max_length=10000)
    translation: str | None = Field(default=None, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisInput(ApiModel):
    task_id: ResourceId
    owner_id: ResourceId
    contract: AnalysisContract
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=1000)
    trace_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

    @model_validator(mode="after")
    def _enforce_task_boundary(self) -> AnalysisInput:
        mismatched = [item.id for item in self.evidence if item.task_id != self.task_id]
        if mismatched:
            raise ValueError("证据 task_id 与当前任务不一致。")
        foreign = [item.id for item in self.evidence if item.owner_id != self.owner_id]
        if foreign:
            raise ValueError("证据 owner_id 与当前账号不一致。")
        return self


class SkillSpec(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    instructions: str = Field(min_length=1, max_length=10000)


class AnalysisPlan(ApiModel):
    goal: str
    focus_areas: list[str]
    skills: list[SkillSpec] = Field(min_length=1)
    unavailable_skills: list[str] = Field(default_factory=list)


class ModelConclusion(ApiModel):
    """模型候选输出；证据 ID 会由协调器解析为冻结的 EvidenceReference。"""

    type: ConclusionType
    content: str = Field(min_length=1, max_length=10000)
    evidence_ids: list[ResourceId] = Field(min_length=1, max_length=20)
    skill: str = Field(min_length=1, max_length=64)


class ModelAnalysis(ApiModel):
    conclusions: list[ModelConclusion] = Field(min_length=1, max_length=100)


class AgentRunResult(ApiModel):
    trace_id: str
    model_name: str
    prompt_version: str
    skills: list[str]
    conclusions: InternalConclusionBatchWrite

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
from backend.app.schemas.task import PrivacyMode


class AnalysisScope(StrEnum):
    FULL_LESSON = "full_lesson"
    TIME_RANGE = "time_range"


class CourseDomain(StrEnum):
    GENERAL = "general"
    COMPUTER_AI = "computer_ai"
    HUMANITIES = "humanities"


class AnalysisContract(ApiModel):
    """教师确认后才可执行的分析契约。"""

    goal: str = Field(min_length=1, max_length=2000)
    scope: AnalysisScope = AnalysisScope.FULL_LESSON
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    focus_areas: list[str] = Field(min_length=1, max_length=12)
    judgment_criteria: list[str] = Field(default_factory=list, max_length=20)
    evidence_requirements: list[str] = Field(default_factory=list, max_length=20)
    bilingual_required: bool = False
    privacy_mode: PrivacyMode = PrivacyMode.LOCAL
    course_domain: CourseDomain = CourseDomain.GENERAL
    confirmed: bool = False

    @model_validator(mode="after")
    def _validate_scope(self) -> AnalysisContract:
        if self.scope is AnalysisScope.TIME_RANGE:
            if self.start_ms is None or self.end_ms is None:
                raise ValueError("scope=time_range 必须同时提供 start_ms 与 end_ms。")
            if self.end_ms <= self.start_ms:
                raise ValueError("分析范围 end_ms 必须大于 start_ms。")
        elif self.start_ms is not None or self.end_ms is not None:
            raise ValueError("只有 scope=time_range 才能提供 start_ms/end_ms。")
        return self


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

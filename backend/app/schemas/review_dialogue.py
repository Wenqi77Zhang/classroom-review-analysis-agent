"""Teacher-facing review clarification and draft-contract schemas."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.app.schemas.common import ApiModel
from backend.app.schemas.task import AnalysisContract, AnalysisScope, CourseDomain, PrivacyMode

ContractText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ReviewDialogueRequest(ApiModel):
    """Only teacher turns are accepted; assistant text is generated server-side."""

    teacher_messages: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _normalize_messages(self) -> ReviewDialogueRequest:
        normalized = [message.strip() for message in self.teacher_messages]
        if any(not message for message in normalized):
            raise ValueError("每轮教师输入不能为空。")
        if any(len(message) > 2000 for message in normalized):
            raise ValueError("单轮教师输入不能超过 2000 个字符。")
        self.teacher_messages = normalized
        return self


class ModelReviewContract(ApiModel):
    """Grammar-friendly model output; zero time values mean no explicit range."""

    goal: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]
    scope: AnalysisScope
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    focus_areas: list[ContractText] = Field(min_length=1, max_length=12)
    judgment_criteria: list[ContractText] = Field(min_length=1, max_length=20)
    evidence_requirements: list[ContractText] = Field(min_length=1, max_length=20)
    bilingual_required: bool
    course_domain: CourseDomain

    def to_analysis_contract(self) -> AnalysisContract:
        start_ms: int | None = None
        end_ms: int | None = None
        if self.scope is AnalysisScope.TIME_RANGE:
            if self.end_ms <= self.start_ms:
                raise ValueError("模型给出的时间范围无效。")
            start_ms, end_ms = self.start_ms, self.end_ms
        return AnalysisContract(
            goal=self.goal,
            scope=self.scope,
            start_ms=start_ms,
            end_ms=end_ms,
            focus_areas=self.focus_areas,
            judgment_criteria=self.judgment_criteria,
            evidence_requirements=self.evidence_requirements,
            bilingual_required=self.bilingual_required,
            privacy_mode=PrivacyMode.LOCAL,
            course_domain=self.course_domain,
            confirmed=False,
        )


class ModelReviewDialogue(ApiModel):
    clarification_needed: bool
    assistant_message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1200),
    ]
    analysis_contract: ModelReviewContract


class ReviewDialogueResponse(ApiModel):
    clarification_needed: bool
    assistant_message: str
    analysis_contract: AnalysisContract
    model_name: str = Field(min_length=1, max_length=128)
    prompt_version: Literal["clarification-v1"] = "clarification-v1"
    trace_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")

"""一次规划、受约束模型调用、证据解析与结构化结论编排。"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from agent.contracts import (
    AgentErrorCode,
    AgentRunResult,
    AnalysisContract,
    AnalysisInput,
    AnalysisPlan,
    AnalysisScope,
    CourseDomain,
    EvidenceItem,
    ModelAnalysis,
    SkillSpec,
)
from agent.observability.tracing import InMemoryTraceSink, Tracer, TraceSink
from agent.providers import ProviderNotConfiguredError, ProviderRouter
from agent.providers.base import ModelProviderError, ModelRequest
from agent.skills.common import get_common_skill
from agent.state import AgentState, AgentWorkflow
from agent.tools.retrieve_evidence import EvidenceNotFoundError, EvidenceRetriever
from backend.app.schemas.analysis_report import (
    EvidenceSourceType,
    InternalConclusionBatchWrite,
    InternalConclusionWrite,
)

PROMPT_VERSION = "analysis-v1"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "analysis.md"


class AgentRunError(RuntimeError):
    def __init__(self, code: AgentErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


ConclusionValidator = Callable[[InternalConclusionWrite], None]


class AgentOrchestrator:
    def __init__(
        self,
        *,
        providers: ProviderRouter,
        skill_registry: Mapping[str, SkillSpec] | None = None,
        conclusion_validator: ConclusionValidator | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        self._providers = providers
        self._skills = dict(skill_registry or {})
        self._skills.setdefault("common", get_common_skill())
        self._conclusion_validator = conclusion_validator
        self._trace_sink = trace_sink or InMemoryTraceSink()

    def plan(self, analysis_input: AnalysisInput) -> AnalysisPlan:
        skills = [self._skills["common"]]
        unavailable: list[str] = []
        requested = {
            CourseDomain.COMPUTER_AI: "computer_ai",
            CourseDomain.HUMANITIES: "humanities",
        }.get(analysis_input.contract.course_domain)
        if requested:
            if requested in self._skills:
                skills.append(self._skills[requested])
            else:
                # 专业规则由成员 4 提供；未提供时不伪装为已启用。
                unavailable.append(requested)
        return AnalysisPlan(
            goal=analysis_input.contract.goal,
            focus_areas=analysis_input.contract.focus_areas,
            skills=skills,
            unavailable_skills=unavailable,
        )

    async def analyze(self, analysis_input: AnalysisInput) -> AgentRunResult:
        workflow = AgentWorkflow()
        tracer = Tracer(self._trace_sink, analysis_input.trace_id)
        try:
            if not analysis_input.contract.confirmed:
                raise AgentRunError(
                    AgentErrorCode.CONTRACT_UNCONFIRMED,
                    "分析契约尚未由教师确认，拒绝启动 Agent。",
                )
            workflow.transition(AgentState.PLANNING)
            plan = self.plan(analysis_input)
            tracer.event(
                "agent.plan.created",
                task_id=str(analysis_input.task_id),
                skills=[skill.name for skill in plan.skills],
                unavailable_skills=plan.unavailable_skills,
                prompt_version=PROMPT_VERSION,
            )
            if plan.unavailable_skills:
                raise AgentRunError(
                    AgentErrorCode.SKILL_UNAVAILABLE,
                    "教师请求的专业 Skill 尚未可用，拒绝降级为通用分析。",
                )

            retriever = EvidenceRetriever(
                analysis_input.evidence,
                task_id=analysis_input.task_id,
                owner_id=analysis_input.owner_id,
            )
            evidence = self._select_evidence(analysis_input)
            provided_evidence_ids = {item.id for item in evidence}
            provider = self._providers.select(analysis_input.contract.privacy_mode)
            request = ModelRequest(
                system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
                user_prompt=self._build_user_prompt(analysis_input, plan, evidence),
                trace_id=tracer.trace_id,
                response_schema=ModelAnalysis.model_json_schema(),
            )

            workflow.transition(AgentState.ANALYZING)
            response = await provider.generate_structured(request)
            tracer.event(
                "agent.model.completed",
                model_name=response.model_name,
                latency_ms=response.latency_ms,
                usage=response.usage,
            )

            workflow.transition(AgentState.VALIDATING)
            model_analysis = ModelAnalysis.model_validate(response.data)
            allowed_skills = {skill.name for skill in plan.skills}
            conclusions: list[InternalConclusionWrite] = []
            for candidate in model_analysis.conclusions:
                if candidate.skill not in allowed_skills:
                    raise AgentRunError(
                        AgentErrorCode.SKILL_NOT_IN_PLAN,
                        "模型声明了本次计划未启用的 Skill。",
                    )
                evidence_items = retriever.get_many(candidate.evidence_ids)
                self._validate_evidence_policy(evidence_items, analysis_input.contract)
                if any(item.id not in provided_evidence_ids for item in evidence_items):
                    raise AgentRunError(
                        AgentErrorCode.EVIDENCE_NOT_PROVIDED,
                        "模型引用了未提供给本次分析的证据。",
                    )
                conclusion = InternalConclusionWrite(
                    type=candidate.type,
                    content=candidate.content,
                    evidence_refs=[item.reference for item in evidence_items],
                    trace_id=tracer.trace_id,
                    model_name=response.model_name,
                    skill=candidate.skill,
                    prompt_version=PROMPT_VERSION,
                )
                if self._conclusion_validator is not None:
                    self._conclusion_validator(conclusion)
                conclusions.append(conclusion)
            batch = InternalConclusionBatchWrite(conclusions=conclusions)
            tracer.event(
                "agent.analysis.validated",
                conclusion_count=len(conclusions),
                evidence_reference_count=sum(len(item.evidence_refs) for item in conclusions),
            )
            workflow.transition(AgentState.AWAITING_REVIEW)
            return AgentRunResult(
                trace_id=tracer.trace_id,
                model_name=response.model_name,
                prompt_version=PROMPT_VERSION,
                skills=[skill.name for skill in plan.skills],
                conclusions=batch,
            )
        except Exception as exc:
            failed_stage = workflow.state.value
            error_code = self._error_code(exc)
            tracer.error(exc, stage=failed_stage, error_code=error_code.value)
            workflow.fail()
            if isinstance(exc, AgentRunError):
                raise
            raise AgentRunError(error_code, f"Agent 在 {failed_stage} 阶段失败。") from exc

    @staticmethod
    def _is_in_scope(item: EvidenceItem, contract: AnalysisContract) -> bool:
        if contract.scope is AnalysisScope.FULL_LESSON:
            return True
        start_ms = contract.start_ms
        end_ms = contract.end_ms
        if start_ms is None or end_ms is None or item.reference.start_ms is None:
            return False
        item_end_ms = item.reference.end_ms or item.reference.start_ms
        return item.reference.start_ms >= start_ms and item_end_ms <= end_ms

    def _select_evidence(self, analysis_input: AnalysisInput) -> list[EvidenceItem]:
        evidence = [
            item
            for item in analysis_input.evidence
            if item.task_id == analysis_input.task_id
            and item.owner_id == analysis_input.owner_id
            and self._is_in_scope(item, analysis_input.contract)
        ]
        if not evidence:
            raise AgentRunError(
                AgentErrorCode.EVIDENCE_SCOPE_EMPTY,
                "教师确认的分析范围内没有可定位证据。",
            )
        self._validate_evidence_policy(evidence, analysis_input.contract)
        return evidence[:200]

    def _validate_evidence_policy(
        self,
        evidence: Sequence[EvidenceItem],
        contract: AnalysisContract,
    ) -> None:
        if any(not self._is_in_scope(item, contract) for item in evidence):
            raise AgentRunError(
                AgentErrorCode.EVIDENCE_OUT_OF_SCOPE,
                "结论引用了教师确认范围之外的证据。",
            )
        if contract.bilingual_required and any(
            item.reference.source_type is EvidenceSourceType.TRANSCRIPT
            and not (item.translation or "").strip()
            for item in evidence
        ):
            raise AgentRunError(
                AgentErrorCode.BILINGUAL_EVIDENCE_INCOMPLETE,
                "双语分析要求的逐句译文尚未完整生成。",
            )

    @staticmethod
    def _error_code(error: BaseException) -> AgentErrorCode:
        if isinstance(error, AgentRunError):
            return error.code
        if isinstance(error, ValidationError):
            return AgentErrorCode.SCHEMA_INVALID
        if isinstance(error, EvidenceNotFoundError):
            return AgentErrorCode.EVIDENCE_NOT_FOUND
        if isinstance(error, ProviderNotConfiguredError):
            return AgentErrorCode.PROVIDER_NOT_CONFIGURED
        if isinstance(error, ModelProviderError):
            return AgentErrorCode.MODEL_PROVIDER_ERROR
        return AgentErrorCode.AGENT_INTERNAL_ERROR

    @staticmethod
    def _build_user_prompt(
        analysis_input: AnalysisInput,
        plan: AnalysisPlan,
        evidence: Sequence[EvidenceItem],
    ) -> str:
        trusted_context = {
            "analysis_contract": analysis_input.contract.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "required_output_schema": ModelAnalysis.model_json_schema(mode="serialization"),
        }
        untrusted_evidence = {
            "encoding": "base64-utf8",
            "items": [
                {
                    "evidence_id": str(item.id),
                    "source": {
                        "source_type": item.reference.source_type.value,
                        "asset_id": str(item.reference.asset_id)
                        if item.reference.asset_id
                        else None,
                        "segment_id": str(item.reference.segment_id)
                        if item.reference.segment_id
                        else None,
                        "start_ms": item.reference.start_ms,
                        "end_ms": item.reference.end_ms,
                        "page_no": item.reference.page_no,
                    },
                    "text_b64": base64.b64encode(item.text.encode("utf-8")).decode("ascii"),
                    "translation_b64": base64.b64encode(item.translation.encode("utf-8")).decode(
                        "ascii"
                    )
                    if item.translation is not None
                    else None,
                }
                for item in evidence
            ],
        }
        return "\n".join(
            [
                "TRUSTED_ANALYSIS_CONTEXT_JSON",
                json.dumps(trusted_context, ensure_ascii=False, separators=(",", ":")),
                "BEGIN_UNTRUSTED_EVIDENCE_JSON_BASE64",
                json.dumps(untrusted_evidence, ensure_ascii=True, separators=(",", ":")),
                "END_UNTRUSTED_EVIDENCE_JSON_BASE64",
            ]
        )

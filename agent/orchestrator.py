"""一次规划、受约束模型调用、证据解析与结构化结论编排。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from agent.contracts import (
    AgentRunResult,
    AnalysisInput,
    AnalysisPlan,
    CourseDomain,
    EvidenceItem,
    ModelAnalysis,
    SkillSpec,
)
from agent.observability.tracing import InMemoryTraceSink, Tracer, TraceSink
from agent.providers import ProviderRouter
from agent.providers.base import ModelRequest
from agent.skills.common import get_common_skill
from agent.state import AgentState, AgentWorkflow
from agent.tools.retrieve_evidence import EvidenceRetriever
from backend.app.schemas.analysis_report import (
    InternalConclusionBatchWrite,
    InternalConclusionWrite,
)

PROMPT_VERSION = "analysis-v1"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "analysis.md"


class AgentRunError(RuntimeError):
    pass


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
                raise AgentRunError("分析契约尚未由教师确认，拒绝启动 Agent。")
            workflow.transition(AgentState.PLANNING)
            plan = self.plan(analysis_input)
            tracer.event(
                "agent.plan.created",
                task_id=str(analysis_input.task_id),
                skills=[skill.name for skill in plan.skills],
                unavailable_skills=plan.unavailable_skills,
                prompt_version=PROMPT_VERSION,
            )

            retriever = EvidenceRetriever(
                analysis_input.evidence,
                task_id=analysis_input.task_id,
                owner_id=analysis_input.owner_id,
            )
            evidence = retriever.all()
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
                        f"模型声明了本次计划未启用的 Skill：{candidate.skill}。"
                    )
                evidence_items = retriever.get_many(candidate.evidence_ids)
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
            tracer.error(exc, stage=failed_stage)
            workflow.fail()
            if isinstance(exc, AgentRunError):
                raise
            raise AgentRunError(f"Agent 在 {failed_stage} 阶段失败。") from exc

    @staticmethod
    def _build_user_prompt(
        analysis_input: AnalysisInput,
        plan: AnalysisPlan,
        evidence: Sequence[EvidenceItem],
    ) -> str:
        payload = {
            "analysis_contract": analysis_input.contract.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "evidence": [
                {
                    "evidence_id": str(item.id),
                    "source": item.reference.model_dump(mode="json"),
                    "text": item.text,
                    "translation": item.translation,
                }
                for item in evidence
            ],
            "required_output_schema": ModelAnalysis.model_json_schema(mode="serialization"),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

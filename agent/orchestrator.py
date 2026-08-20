"""一次规划、受约束模型调用、证据解析与结构化结论编排。"""

from __future__ import annotations

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
    ConclusionType,
    EvidenceSourceType,
    InternalConclusionBatchWrite,
    InternalConclusionWrite,
)

PROMPT_VERSION = "analysis-v2"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "analysis.md"
_GRAMMAR_SCHEMA_KEYS = frozenset(
    {"type", "properties", "required", "items", "enum", "additionalProperties"}
)


def _model_grammar_schema(
    *,
    allowed_skills: Sequence[str] | None = None,
    allowed_types: Sequence[str] | None = None,
    allowed_evidence_ids: Sequence[str] | None = None,
) -> dict:
    """把 Pydantic Schema 精简为本地 grammar 引擎稳定支持的结构子集。

    模型侧只负责约束 JSON 形状；完整的 UUID、长度、数量与枚举校验仍由下游
    ``ModelAnalysis.model_validate`` 执行，所以精简不会绕过服务端门禁。
    """

    root = ModelAnalysis.model_json_schema(mode="serialization")
    definitions = root.get("$defs", {})

    def compact(node: object) -> object:
        if isinstance(node, list):
            return [compact(item) for item in node]
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            target = definitions.get(name)
            if isinstance(target, dict):
                return compact(target)
        result: dict[str, object] = {}
        for key, value in node.items():
            if key not in _GRAMMAR_SCHEMA_KEYS:
                continue
            if key == "properties" and isinstance(value, dict):
                result[key] = {name: compact(schema) for name, schema in value.items()}
            else:
                result[key] = compact(value)
        return result

    compacted = compact(root)
    if not isinstance(compacted, dict):
        raise TypeError("模型输出 Schema 精简失败。")
    if allowed_skills is not None:
        skill_names = list(dict.fromkeys(allowed_skills))
        if not skill_names:
            raise ValueError("模型输出 Schema 至少需要一个允许的 Skill。")
        try:
            skill_schema = compacted["properties"]["conclusions"]["items"][
                "properties"
            ]["skill"]
        except (KeyError, TypeError) as exc:
            raise TypeError("模型输出 Schema 缺少 conclusions[].skill。") from exc
        if not isinstance(skill_schema, dict):
            raise TypeError("模型输出 Schema 的 conclusions[].skill 不是对象。")
        # 把本轮计划真正收紧进 grammar，减少小模型生成计划外 Skill 的机会。
        # 下游仍保留独立白名单校验，不能仅依赖模型侧约束。
        skill_schema["enum"] = skill_names
    if allowed_types is not None:
        conclusion_types = list(dict.fromkeys(allowed_types))
        if not conclusion_types:
            raise ValueError("模型输出 Schema 至少需要一个允许的结论类型。")
        try:
            type_schema = compacted["properties"]["conclusions"]["items"][
                "properties"
            ]["type"]
        except (KeyError, TypeError) as exc:
            raise TypeError("模型输出 Schema 缺少 conclusions[].type。") from exc
        if not isinstance(type_schema, dict):
            raise TypeError("模型输出 Schema 的 conclusions[].type 不是对象。")
        type_schema["enum"] = conclusion_types
    if allowed_evidence_ids is not None:
        evidence_ids = list(dict.fromkeys(allowed_evidence_ids))
        if not evidence_ids:
            raise ValueError("模型输出 Schema 至少需要一个允许的证据 ID。")
        try:
            evidence_id_schema = compacted["properties"]["conclusions"]["items"][
                "properties"
            ]["evidence_ids"]["items"]
        except (KeyError, TypeError) as exc:
            raise TypeError("模型输出 Schema 缺少 conclusions[].evidence_ids[]。") from exc
        if not isinstance(evidence_id_schema, dict):
            raise TypeError("模型输出 Schema 的 evidence_ids[] 不是对象。")
        # 让 grammar 只接受本次真正提供给模型的证据 ID。后端后续仍会校验
        # task/owner/scope，枚举只是第一道约束而不是权限判断的替代品。
        evidence_id_schema["enum"] = evidence_ids
    return compacted


class AgentRunError(RuntimeError):
    def __init__(self, code: AgentErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


ConclusionValidator = Callable[[InternalConclusionWrite], None]


def _validation_error_shape(error: ValidationError) -> list[dict[str, str]]:
    """Return only schema locations and error types; never persist model content."""

    return [
        {
            "location": ".".join(str(part) for part in item["loc"]),
            "type": item["type"],
        }
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    ]


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
            allowed_skills = [skill.name for skill in plan.skills]
            allowed_evidence_ids = [str(item.id) for item in evidence]
            response_schema = _model_grammar_schema(
                allowed_skills=allowed_skills,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            request = ModelRequest(
                system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
                user_prompt=self._build_user_prompt(
                    analysis_input,
                    plan,
                    evidence,
                    response_schema=response_schema,
                ),
                trace_id=tracer.trace_id,
                response_schema=response_schema,
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
            try:
                model_analysis = ModelAnalysis.model_validate(response.data)
            except ValidationError as validation_error:
                tracer.event(
                    "agent.model.schema_invalid",
                    errors=_validation_error_shape(validation_error),
                )
                # 本地小模型偶尔会生成 JSON 形状正确、但 UUID/必填字段等完整契约
                # 不合规的结果。只允许一次同约束重生，不把无效字段静默修补进系统。
                schema_repair_request = ModelRequest(
                    system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
                    user_prompt=self._build_user_prompt(
                        analysis_input,
                        plan,
                        evidence,
                        response_schema=response_schema,
                        schema_repair=True,
                    ),
                    trace_id=tracer.trace_id,
                    response_schema=response_schema,
                )
                response = await provider.generate_structured(schema_repair_request)
                tracer.event(
                    "agent.model.schema_repair_completed",
                    model_name=response.model_name,
                    latency_ms=response.latency_ms,
                    usage=response.usage,
                )
                try:
                    model_analysis = ModelAnalysis.model_validate(response.data)
                except ValidationError as repair_error:
                    tracer.event(
                        "agent.model.schema_repair_invalid",
                        errors=_validation_error_shape(repair_error),
                    )
                    raise
            candidates = list(model_analysis.conclusions)
            required_types = (
                ConclusionType.FACT,
                ConclusionType.JUDGMENT,
                ConclusionType.SUGGESTION,
            )
            present_types = {candidate.type for candidate in candidates}
            for missing_type in required_types:
                if missing_type in present_types:
                    continue
                repair_schema = _model_grammar_schema(
                    allowed_skills=allowed_skills,
                    allowed_types=[missing_type.value],
                    allowed_evidence_ids=allowed_evidence_ids,
                )
                repair_request = ModelRequest(
                    system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
                    user_prompt=self._build_user_prompt(
                        analysis_input,
                        plan,
                        evidence,
                        response_schema=repair_schema,
                        required_conclusion_types=[missing_type.value],
                    ),
                    trace_id=tracer.trace_id,
                    response_schema=repair_schema,
                )
                repair_response = await provider.generate_structured(repair_request)
                tracer.event(
                    "agent.model.repair_completed",
                    model_name=repair_response.model_name,
                    required_type=missing_type.value,
                    latency_ms=repair_response.latency_ms,
                    usage=repair_response.usage,
                )
                repaired = ModelAnalysis.model_validate(repair_response.data)
                matching = [
                    candidate
                    for candidate in repaired.conclusions
                    if candidate.type is missing_type
                ]
                if not matching:
                    raise AgentRunError(
                        AgentErrorCode.SCHEMA_INVALID,
                        f"模型修复输出仍缺少 {missing_type.value} 结论。",
                    )
                candidates.append(matching[0])
                present_types.add(missing_type)

            allowed_skill_set = set(allowed_skills)
            conclusions: list[InternalConclusionWrite] = []
            for candidate in candidates:
                if candidate.skill not in allowed_skill_set:
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
        *,
        response_schema: Mapping[str, object],
        required_conclusion_types: Sequence[str] | None = None,
        schema_repair: bool = False,
    ) -> str:
        trusted_context = {
            "analysis_contract": analysis_input.contract.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "required_output_schema": response_schema,
        }
        if required_conclusion_types is not None:
            trusted_context["required_conclusion_types"] = list(
                required_conclusion_types
            )
        if schema_repair:
            trusted_context["schema_repair"] = {
                "required": True,
                "instruction": "重新生成完整结果；不得沿用不合规字段或省略必填字段。",
            }
        untrusted_evidence = {
            "encoding": "json-utf8",
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
                    "text": item.text,
                    "translation": item.translation,
                }
                for item in evidence
            ],
        }
        return "\n".join(
            [
                "TRUSTED_ANALYSIS_CONTEXT_JSON",
                json.dumps(trusted_context, ensure_ascii=False, separators=(",", ":")),
                "BEGIN_UNTRUSTED_EVIDENCE_JSON",
                json.dumps(untrusted_evidence, ensure_ascii=False, separators=(",", ":")),
                "END_UNTRUSTED_EVIDENCE_JSON",
            ]
        )

"""成员 5：Agent 契约、状态、隐私路由、证据门禁、Trace 与编排测试。"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from agent.contracts import (
    AnalysisContract,
    AnalysisInput,
    AnalysisScope,
    CourseDomain,
    EvidenceItem,
)
from agent.observability.tracing import InMemoryTraceSink, Tracer
from agent.orchestrator import AgentOrchestrator, AgentRunError
from agent.providers import ProviderNotConfiguredError, ProviderRouter
from agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from agent.providers.cloud import CloudModelProvider
from agent.providers.local import LocalModelProvider
from agent.state import AgentState, AgentWorkflow, InvalidAgentTransition
from agent.tools.retrieve_evidence import EvidenceNotFoundError, EvidenceRetriever
from backend.app.schemas.analysis_report import EvidenceReference, EvidenceSourceType
from backend.app.schemas.task import PrivacyMode


class FakeProvider(ModelProvider):
    def __init__(self, data: dict, *, name: str = "fake-model") -> None:
        self.data = data
        self._name = name
        self.requests: list[ModelRequest] = []

    @property
    def model_name(self) -> str:
        return self._name

    async def generate_structured(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            data=self.data,
            model_name=self._name,
            latency_ms=12,
            usage={"total_tokens": 42},
        )


def _evidence(
    *, task_id: UUID, owner_id: UUID, evidence_id: UUID | None = None
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id or uuid4(),
        task_id=task_id,
        owner_id=owner_id,
        reference=EvidenceReference(
            source_type=EvidenceSourceType.TRANSCRIPT,
            start_ms=1200,
            end_ms=4200,
            quote="教师提出问题后停顿三秒。",
        ),
        text="教师提出问题后停顿三秒，然后邀请学生回答。",
    )


def _input(
    *,
    confirmed: bool = True,
    privacy_mode: PrivacyMode = PrivacyMode.LOCAL,
    domain: CourseDomain = CourseDomain.GENERAL,
) -> AnalysisInput:
    task_id = uuid4()
    owner_id = uuid4()
    return AnalysisInput(
        task_id=task_id,
        owner_id=owner_id,
        contract=AnalysisContract(
            goal="复盘课堂提问与等待时间",
            focus_areas=["提问等待时间"],
            privacy_mode=privacy_mode,
            course_domain=domain,
            confirmed=confirmed,
        ),
        evidence=[_evidence(task_id=task_id, owner_id=owner_id)],
    )


def _model_data(evidence_id: UUID) -> dict:
    return {
        "conclusions": [
            {
                "type": "fact",
                "content": "教师提问后等待约三秒再邀请学生回答。",
                "evidence_ids": [str(evidence_id)],
                "skill": "common",
            }
        ]
    }


def test_time_range_contract_requires_complete_ordered_range() -> None:
    with pytest.raises(ValidationError):
        AnalysisContract(
            goal="聚焦片段",
            scope=AnalysisScope.TIME_RANGE,
            start_ms=5000,
            focus_areas=["讲解"],
        )
    with pytest.raises(ValidationError):
        AnalysisContract(
            goal="聚焦片段",
            scope=AnalysisScope.TIME_RANGE,
            start_ms=5000,
            end_ms=4000,
            focus_areas=["讲解"],
        )


def test_analysis_input_rejects_foreign_evidence() -> None:
    task_id = uuid4()
    owner_id = uuid4()
    with pytest.raises(ValidationError, match="owner_id"):
        AnalysisInput(
            task_id=task_id,
            owner_id=owner_id,
            contract=AnalysisContract(goal="复盘", focus_areas=["结构"]),
            evidence=[_evidence(task_id=task_id, owner_id=uuid4())],
        )


def test_state_machine_rejects_skipping_validation() -> None:
    workflow = AgentWorkflow()
    workflow.transition(AgentState.PLANNING)
    workflow.transition(AgentState.ANALYZING)
    with pytest.raises(InvalidAgentTransition):
        workflow.transition(AgentState.AWAITING_REVIEW)


def test_provider_router_requires_configured_privacy_route() -> None:
    router = ProviderRouter()
    with pytest.raises(ProviderNotConfiguredError):
        router.select(PrivacyMode.LOCAL)


def test_provider_endpoint_security_rules() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        CloudModelProvider(endpoint="http://models.example/v1", model="m", api_key="secret")
    with pytest.raises(ValueError, match="loopback"):
        LocalModelProvider(endpoint="http://models.example/v1", model="m")
    provider = LocalModelProvider(endpoint="http://127.0.0.1:11434/v1/chat/completions", model="m")
    assert provider.model_name == "m"


def test_retriever_rejects_unknown_evidence_id() -> None:
    analysis_input = _input()
    retriever = EvidenceRetriever(
        analysis_input.evidence,
        task_id=analysis_input.task_id,
        owner_id=analysis_input.owner_id,
    )
    with pytest.raises(EvidenceNotFoundError):
        retriever.get_many([uuid4()])


@pytest.mark.asyncio
async def test_orchestrator_generates_frozen_backend_conclusion_contract() -> None:
    analysis_input = _input()
    evidence_id = analysis_input.evidence[0].id
    provider = FakeProvider(_model_data(evidence_id))
    sink = InMemoryTraceSink()
    orchestrator = AgentOrchestrator(
        providers=ProviderRouter(local=provider),
        trace_sink=sink,
    )

    result = await orchestrator.analyze(analysis_input)

    conclusion = result.conclusions.conclusions[0]
    assert conclusion.type.value == "fact"
    assert conclusion.evidence_refs[0] == analysis_input.evidence[0].reference
    assert conclusion.trace_id == result.trace_id
    assert conclusion.model_name == "fake-model"
    assert conclusion.skill == "common"
    assert conclusion.prompt_version == "analysis-v1"
    assert "review_status" not in conclusion.model_dump()
    assert [event.name for event in sink.events] == [
        "agent.plan.created",
        "agent.model.completed",
        "agent.analysis.validated",
    ]
    assert str(evidence_id) in provider.requests[0].user_prompt


@pytest.mark.asyncio
async def test_orchestrator_refuses_unconfirmed_contract_before_model_call() -> None:
    analysis_input = _input(confirmed=False)
    provider = FakeProvider(_model_data(analysis_input.evidence[0].id))
    orchestrator = AgentOrchestrator(providers=ProviderRouter(local=provider))
    with pytest.raises(AgentRunError, match="尚未由教师确认"):
        await orchestrator.analyze(analysis_input)
    assert provider.requests == []


@pytest.mark.asyncio
async def test_orchestrator_blocks_model_reference_outside_task() -> None:
    analysis_input = _input()
    provider = FakeProvider(_model_data(uuid4()))
    orchestrator = AgentOrchestrator(providers=ProviderRouter(local=provider))
    with pytest.raises(AgentRunError) as captured:
        await orchestrator.analyze(analysis_input)
    assert isinstance(captured.value.__cause__, EvidenceNotFoundError)


def test_missing_member4_domain_skill_is_reported_not_faked() -> None:
    analysis_input = _input(domain=CourseDomain.HUMANITIES)
    provider = FakeProvider(_model_data(analysis_input.evidence[0].id))
    plan = AgentOrchestrator(providers=ProviderRouter(local=provider)).plan(analysis_input)
    assert [skill.name for skill in plan.skills] == ["common"]
    assert plan.unavailable_skills == ["humanities"]


def test_trace_redacts_sensitive_attributes() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(sink, "trace-safe")
    tracer.event("test", api_key="do-not-record", nested={"password": "also-secret"})
    assert sink.events[0].attributes == {
        "api_key": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }

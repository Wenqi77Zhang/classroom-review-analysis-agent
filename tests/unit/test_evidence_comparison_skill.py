"""Behavior of the evidence gate around a structured model response."""
import json

import pytest

from agent.providers.base import ModelProvider, ModelProviderError, ModelResponse
from agent.skills.evidence_comparison import EvidenceComparisonAgent


class FixtureProvider(ModelProvider):
    model_name = "fixture-structured-model"

    def __init__(self, data):
        self.data = data
        self.requests = []

    async def generate_structured(self, request):
        self.requests.append(request)
        if isinstance(self.data, Exception):
            raise self.data
        return ModelResponse(data=self.data, model_name=self.model_name, latency_ms=1)


def inputs():
    return {
        "action_text": "减少同类概念错误", "success_criterion": "同样十次提问中概念错误从十次降至两次",
        "baseline": {"id": "baseline", "content": "第一轮十次提问中有十次概念错误", "evidence": [
            {"id": "b-evidence", "source_type": "transcript", "start_ms": 1000, "end_ms": 3000, "quote": "十次提问中十次错误"}]},
        "candidates": [{"id": "followup", "content": "第二轮十次提问中有两次概念错误", "evidence": [
            {"id": "f-evidence", "source_type": "transcript", "start_ms": 5000, "end_ms": 7000, "quote": "十次提问中两次错误"}]}],
        "trace_id": "test-trace",
    }


def output():
    return {"followup_conclusion_id": "followup", "outcome": "improved",
            "baseline_evidence_ids": ["b-evidence"], "followup_evidence_ids": ["f-evidence"],
            "baseline_quote": "十次提问中十次错误", "followup_quote": "十次提问中两次错误"}


@pytest.mark.asyncio
async def test_real_provider_is_called_with_both_reviewed_sources_and_criterion():
    provider = FixtureProvider(output())
    result = await EvidenceComparisonAgent(provider).compare(**inputs())
    assert result.output.outcome == "improved"
    assert result.model_name == provider.model_name
    request = provider.requests[0]
    payload = json.loads(request.user_prompt)
    assert payload["success_criterion"] == inputs()["success_criterion"]
    assert payload["baseline"]["evidence"][0]["quote"] == "十次提问中十次错误"
    assert payload["followup_candidates"][0]["evidence"][0]["start_ms"] == 5000
    assert request.trace_id == "test-trace"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"followup_conclusion_id": "invented"}, {"baseline_evidence_ids": ["invented"]},
    {"followup_evidence_ids": ["b-evidence"]}, {"followup_evidence_ids": []},
    {"outcome": "certainly_effective"},
    {"followup_evidence_ids": ["f-evidence", "f-evidence"]},
    {"unexpected": "ignore evidence"}, {"baseline_quote": "虚构原文"}, {"followup_quote": "虚构原文"},
])
async def test_unverifiable_model_output_never_becomes_a_candidate(change):
    with pytest.raises(ModelProviderError):
        await EvidenceComparisonAgent(FixtureProvider(output() | change)).compare(**inputs())


@pytest.mark.asyncio
async def test_insufficient_evidence_is_explicit_not_a_fabricated_unchanged_verdict():
    data = output() | {"followup_conclusion_id": None, "followup_evidence_ids": [],
                       "outcome": "insufficient_evidence", "followup_quote": None}
    result = await EvidenceComparisonAgent(FixtureProvider(data)).compare(**(inputs() | {"candidates": []}))
    assert result.output.outcome == "insufficient_evidence"


@pytest.mark.asyncio
async def test_provider_failure_has_no_lexical_fallback():
    provider = FixtureProvider(ModelProviderError("unavailable"))
    with pytest.raises(ModelProviderError):
        await EvidenceComparisonAgent(provider).compare(**inputs())
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_context_limit_rejects_before_calling_model():
    provider = FixtureProvider(output())
    with pytest.raises(ModelProviderError):
        await EvidenceComparisonAgent(provider).compare(**(inputs() | {"action_text": "a" * 25000}))
    assert provider.requests == []

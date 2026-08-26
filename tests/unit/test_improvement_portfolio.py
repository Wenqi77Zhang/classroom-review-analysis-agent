"""Contract tests for M2/M3 without claiming genuine teaching improvement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.skills.evidence_comparison import _terms, propose_outcome
from backend.app.schemas.analysis_report import ReviewAction
from backend.app.schemas.improvement import (
    ComparisonReviewRequest,
    ImprovementCycleCreate,
    ImprovementCycleUpdate,
    ValidationMode,
)


def test_cycle_contract_defaults_to_real_evidence() -> None:
    value = ImprovementCycleCreate(
        baseline_classroom_id=uuid.uuid4(),
        title="提问等待时间改进",
        objective="第二轮关键提问后保留可观察的等待时间",
    )
    assert value.validation_mode is ValidationMode.REAL


def test_synthetic_mode_is_explicit_and_machine_readable() -> None:
    value = ImprovementCycleCreate(
        baseline_classroom_id=uuid.uuid4(),
        title="机制验证",
        objective="仅验证页面与数据流",
        validation_mode=ValidationMode.SYNTHETIC,
    )
    assert value.validation_mode.value == "synthetic"


def test_empty_cycle_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ImprovementCycleUpdate()


def test_modify_comparison_requires_teacher_text() -> None:
    with pytest.raises(ValidationError):
        ComparisonReviewRequest(action=ReviewAction.MODIFY)


def test_comparison_proposal_is_conservative_and_review_gated() -> None:
    assert propose_outcome("学生回应次数有所提升") == "improved"
    assert propose_outcome("等待时间减少，回应不足") == "regressed"
    assert propose_outcome("观察到相似课堂过程") == "unchanged"


def test_chinese_and_english_terms_can_support_relevance_matching() -> None:
    terms = _terms("增加 wait time，并邀请学生回应")
    assert terms["wait"] == 1
    assert terms["邀请"] == 1


def test_generated_timestamp_fixture_is_timezone_aware() -> None:
    assert datetime.now(UTC).tzinfo is not None

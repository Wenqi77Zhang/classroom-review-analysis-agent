"""Contract tests for M2/M3 without claiming genuine teaching improvement."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_classroom_deletion_checks_improvement_references_before_storage() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "backend/app/api/classrooms.py"
    ).read_text(encoding="utf-8")
    assert "ImprovementCycle.baseline_classroom_id" in source
    assert "ImprovementCycle.followup_classroom_id" in source
    assert source.index("improvement_reference_count") < source.index("storage.delete_prefix")

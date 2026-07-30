from __future__ import annotations

from uuid import uuid4

import pytest

from agent.contracts import EvidenceItem
from agent.skills.common import get_common_skill
from agent.skills.computer_ai import get_computer_ai_skill
from agent.skills.humanities import get_humanities_skill
from agent.validators.evidence_gate import (
    ProfessionalEvidenceError,
    validate_computer_ai_evidence,
    validate_humanities_evidence,
)
from backend.app.schemas.analysis_report import EvidenceReference, EvidenceSourceType


def _evidence(
    source_type: EvidenceSourceType,
    *,
    text: str = "Original classroom evidence",
    translation: str | None = "课堂证据译文",
) -> EvidenceItem:
    reference_kwargs: dict[str, object] = {
        "source_type": source_type,
        "asset_id": uuid4(),
        "quote": text,
    }
    if source_type in {EvidenceSourceType.VIDEO, EvidenceSourceType.TRANSCRIPT}:
        reference_kwargs.update(start_ms=1000, end_ms=2000)
    elif source_type is EvidenceSourceType.FRAME:
        reference_kwargs.update(start_ms=1000)
    else:
        reference_kwargs.update(page_no=2)
    return EvidenceItem(
        id=uuid4(),
        task_id=uuid4(),
        owner_id=uuid4(),
        reference=EvidenceReference(**reference_kwargs),
        text=text,
        translation=translation,
    )


def test_member4_skills_have_stable_names_versions_and_boundaries() -> None:
    computer = get_computer_ai_skill()
    humanities = get_humanities_skill()

    assert (computer.name, computer.version) == ("computer_ai", "1.0.0")
    assert (humanities.name, humanities.version) == ("humanities", "1.0.0")
    assert "代码" in computer.instructions
    assert "演示" in computer.instructions
    assert "不得推断学生掌握" in computer.instructions
    assert "原文" in humanities.instructions
    assert "课件" in humanities.instructions
    assert "立场、动机、情绪或身份" in humanities.instructions


def test_member4_skill_getters_return_deep_copies() -> None:
    first = get_computer_ai_skill()
    second = get_computer_ai_skill()

    assert first == second
    assert first is not second


def test_common_skill_is_unchanged() -> None:
    assert get_common_skill().model_dump() == {
        "name": "common",
        "version": "1.0.0",
        "instructions": (
            "分析课堂结构、目标衔接、讲解清晰度、提问与等待、例证和总结。"
            "事实只描述证据可观察内容；判断必须说明事实与标准的关系；"
            "建议必须可操作且不得超出已有证据。每条结论至少引用一个给定证据 ID。"
        ),
    }


def test_computer_ai_accepts_located_concept_transcript() -> None:
    validate_computer_ai_evidence(
        [_evidence(EvidenceSourceType.TRANSCRIPT)],
        requires_visual_proof=False,
        bilingual_required=True,
    )


def test_computer_ai_visual_claim_rejects_transcript_only() -> None:
    with pytest.raises(ProfessionalEvidenceError) as raised:
        validate_computer_ai_evidence(
            [_evidence(EvidenceSourceType.TRANSCRIPT)],
            requires_visual_proof=True,
            bilingual_required=False,
        )

    assert raised.value.code == "VISUAL_EVIDENCE_REQUIRED"


@pytest.mark.parametrize(
    "source_type",
    [
        EvidenceSourceType.VIDEO,
        EvidenceSourceType.FRAME,
        EvidenceSourceType.COURSEWARE,
    ],
)
def test_computer_ai_visual_claim_accepts_visual_source(
    source_type: EvidenceSourceType,
) -> None:
    validate_computer_ai_evidence(
        [_evidence(source_type)],
        requires_visual_proof=True,
        bilingual_required=False,
    )


def test_humanities_accepts_original_transcript_or_courseware() -> None:
    validate_humanities_evidence(
        [_evidence(EvidenceSourceType.TRANSCRIPT)],
        bilingual_required=False,
    )
    validate_humanities_evidence(
        [_evidence(EvidenceSourceType.COURSEWARE)],
        bilingual_required=False,
    )


def test_humanities_rejects_video_without_original_material() -> None:
    with pytest.raises(ProfessionalEvidenceError) as raised:
        validate_humanities_evidence(
            [_evidence(EvidenceSourceType.VIDEO)],
            bilingual_required=False,
        )

    assert raised.value.code == "ORIGINAL_TEXT_REQUIRED"


@pytest.mark.parametrize(
    "validator",
    [
        lambda evidence: validate_computer_ai_evidence(
            evidence,
            requires_visual_proof=False,
            bilingual_required=True,
        ),
        lambda evidence: validate_humanities_evidence(
            evidence,
            bilingual_required=True,
        ),
    ],
)
def test_professional_rules_require_translation_when_bilingual(
    validator,
) -> None:
    with pytest.raises(ProfessionalEvidenceError) as raised:
        validator([_evidence(EvidenceSourceType.TRANSCRIPT, translation=None)])

    assert raised.value.code == "PROFESSIONAL_TRANSLATION_REQUIRED"


@pytest.mark.parametrize(
    "validator",
    [
        lambda evidence: validate_computer_ai_evidence(
            evidence,
            requires_visual_proof=True,
            bilingual_required=True,
        ),
        lambda evidence: validate_humanities_evidence(
            evidence,
            bilingual_required=True,
        ),
    ],
)
def test_professional_bilingual_gate_ignores_courseware_translation(
    validator,
) -> None:
    validator(
        [
            _evidence(
                EvidenceSourceType.COURSEWARE,
                text="中文课件内容",
                translation=None,
            )
        ]
    )


@pytest.mark.parametrize(
    "validator",
    [
        lambda: validate_computer_ai_evidence(
            [],
            requires_visual_proof=False,
            bilingual_required=False,
        ),
        lambda: validate_humanities_evidence([], bilingual_required=False),
    ],
)
def test_professional_rules_reject_empty_evidence(validator) -> None:
    with pytest.raises(ProfessionalEvidenceError) as raised:
        validator()

    assert raised.value.code == "PROFESSIONAL_EVIDENCE_MISSING"

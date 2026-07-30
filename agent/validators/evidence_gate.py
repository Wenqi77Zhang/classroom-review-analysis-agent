"""Pure specialist evidence checks supplied by member 4."""

from __future__ import annotations

from collections.abc import Sequence

from agent.contracts import EvidenceItem
from backend.app.schemas.analysis_report import EvidenceSourceType


class ProfessionalEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _require_evidence(evidence: Sequence[EvidenceItem]) -> None:
    if not evidence:
        raise ProfessionalEvidenceError(
            "PROFESSIONAL_EVIDENCE_MISSING",
            "专业分析至少需要一条可定位证据。",
        )


def _require_translation(
    evidence: Sequence[EvidenceItem],
    *,
    bilingual_required: bool,
) -> None:
    if bilingual_required and any(
        item.reference.source_type is EvidenceSourceType.TRANSCRIPT
        and not (item.translation or "").strip()
        for item in evidence
    ):
        raise ProfessionalEvidenceError(
            "PROFESSIONAL_TRANSLATION_REQUIRED",
            "双语专业分析所引用的证据必须包含逐句译文。",
        )


def validate_computer_ai_evidence(
    evidence: Sequence[EvidenceItem],
    *,
    requires_visual_proof: bool,
    bilingual_required: bool,
) -> None:
    """Require visual evidence for code, UI, demo, and runtime claims."""

    _require_evidence(evidence)
    _require_translation(evidence, bilingual_required=bilingual_required)
    if requires_visual_proof and not any(
        item.reference.source_type
        in {
            EvidenceSourceType.VIDEO,
            EvidenceSourceType.FRAME,
            EvidenceSourceType.COURSEWARE,
        }
        for item in evidence
    ):
        raise ProfessionalEvidenceError(
            "VISUAL_EVIDENCE_REQUIRED",
            "代码、界面或运行演示结论必须引用视频、画面或课件证据。",
        )


def validate_humanities_evidence(
    evidence: Sequence[EvidenceItem],
    *,
    bilingual_required: bool,
) -> None:
    """Require quotable original material for humanities interpretation."""

    _require_evidence(evidence)
    _require_translation(evidence, bilingual_required=bilingual_required)
    has_original_material = any(
        item.text.strip()
        and (
            item.reference.source_type is EvidenceSourceType.TRANSCRIPT
            or (
                item.reference.source_type is EvidenceSourceType.COURSEWARE
                and item.reference.page_no is not None
            )
        )
        for item in evidence
    )
    if not has_original_material:
        raise ProfessionalEvidenceError(
            "ORIGINAL_TEXT_REQUIRED",
            "人文社科结论必须引用逐字稿原文或带页码的课件材料。",
        )

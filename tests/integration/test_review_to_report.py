"""成员 5：验证教师复核状态到确定性报告组合的双重门禁。"""

from datetime import UTC, datetime
from uuid import uuid4

from agent.reporting.composer import compose_reviewed_report
from backend.app.schemas.analysis_report import (
    AnalysisConclusion,
    ConclusionType,
    EvidenceReference,
    EvidenceSourceType,
    ReviewStatus,
)


def _conclusion(
    status: ReviewStatus,
    *,
    content: str,
    reviewed_content: str | None = None,
) -> AnalysisConclusion:
    return AnalysisConclusion(
        id=uuid4(),
        classroom_id=uuid4(),
        task_id=uuid4(),
        type=ConclusionType.SUGGESTION,
        content=content,
        evidence_refs=[
            EvidenceReference(
                source_type=EvidenceSourceType.VIDEO,
                start_ms=1000,
                end_ms=3000,
                quote="可定位证据",
            )
        ],
        review_status=status,
        reviewed_content=reviewed_content,
        created_at=datetime.now(UTC),
        trace_id=f"trace-{status.value}",
    )


def test_report_contains_only_accepted_and_teacher_modified_content() -> None:
    accepted = _conclusion(ReviewStatus.ACCEPTED, content="教师接受的原始建议")
    modified = _conclusion(
        ReviewStatus.MODIFIED,
        content="不得进入报告的模型原文",
        reviewed_content="教师修改并确认的建议",
    )
    pending = _conclusion(ReviewStatus.PENDING, content="未复核内容")
    rejected = _conclusion(ReviewStatus.REJECTED, content="已驳回内容")

    report = compose_reviewed_report(
        title="课堂复盘报告",
        conclusions=[accepted, modified, pending, rejected],
    )

    assert report.included_conclusion_ids == [accepted.id, modified.id]
    assert "教师接受的原始建议" in report.content
    assert "教师修改并确认的建议" in report.content
    assert "不得进入报告的模型原文" not in report.content
    assert "未复核内容" not in report.content
    assert "已驳回内容" not in report.content
    assert "video 1000–3000 ms" in report.content
    assert "trace-accepted" in report.content


def test_report_with_no_reviewed_conclusion_is_explicitly_empty() -> None:
    report = compose_reviewed_report(
        title="空报告",
        conclusions=[_conclusion(ReviewStatus.PENDING, content="待复核")],
    )
    assert report.included_conclusion_ids == []
    assert "没有经教师接受或修改确认的结论" in report.content
    assert "待复核" not in report.content

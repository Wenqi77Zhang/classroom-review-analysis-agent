"""Owner-scoped review history, report persistence, and report gates."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.errors import NotFoundError
from backend.app.models import (
    AnalysisConclusion,
    Classroom,
    Report,
    ReviewDecision,
    User,
)
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    ReportUpdate,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
)
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404

_RESULTING_STATUS = {
    ReviewAction.ACCEPT: ReviewStatus.ACCEPTED,
    ReviewAction.MODIFY: ReviewStatus.MODIFIED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
}


async def apply_review(
    session: AsyncSession,
    *,
    owner_id: UUID,
    user: User,
    conclusion_id: UUID,
    body: ReviewRequest,
) -> ReviewDecision:
    conclusion = await get_owned_or_404(
        session, AnalysisConclusion, conclusion_id, owner_id
    )
    await _lock_classroom(session, owner_id, conclusion.classroom_id)
    current_status = ReviewStatus(conclusion.review_status)
    previous_content = (
        conclusion.reviewed_content
        if current_status is ReviewStatus.MODIFIED
        else conclusion.content
    )
    resulting_status = _RESULTING_STATUS[body.action]
    edited_content = (
        body.edited_content.strip()
        if body.action is ReviewAction.MODIFY and body.edited_content is not None
        else None
    )
    conclusion.review_status = resulting_status
    conclusion.reviewed_content = edited_content
    decision = ReviewDecision(
        owner_id=owner_id,
        conclusion_id=conclusion.id,
        action=body.action,
        resulting_status=resulting_status,
        previous_content=previous_content,
        edited_content=edited_content,
        note=body.note,
        decided_by_id=user.id,
        decided_by=user,
    )
    session.add(decision)

    await session.flush()
    report = await _find_report(session, owner_id, conclusion.classroom_id)
    if report is not None:
        await _sync_report_content(
            session, report, owner_id, conclusion.classroom_id
        )
    await record_audit_event(
        session,
        owner_id=owner_id,
        actor_user_id=user.id,
        action="conclusion.reviewed",
        resource_type="analysis_conclusion",
        resource_id=conclusion.id,
        details={
            "review_action": body.action.value,
            "resulting_status": resulting_status.value,
        },
    )
    return decision


async def list_review_history(
    session: AsyncSession,
    *,
    owner_id: UUID,
    conclusion_id: UUID,
) -> list[ReviewDecision]:
    await get_owned_or_404(session, AnalysisConclusion, conclusion_id, owner_id)
    rows = await session.scalars(
        select(ReviewDecision)
        .options(selectinload(ReviewDecision.decided_by))
        .where(
            ReviewDecision.owner_id == owner_id,
            ReviewDecision.conclusion_id == conclusion_id,
        )
        .order_by(ReviewDecision.created_at, ReviewDecision.id)
    )
    return list(rows)


async def get_report(
    session: AsyncSession,
    *,
    owner_id: UUID,
    classroom_id: UUID,
) -> Report:
    await get_owned_or_404(session, Classroom, classroom_id, owner_id)
    report = await session.scalar(
        select(Report)
        .options(selectinload(Report.conclusions))
        .where(
            Report.owner_id == owner_id,
            Report.classroom_id == classroom_id,
        )
    )
    if report is None:
        raise NotFoundError("报告尚未创建。")
    return report


async def _lock_classroom(
    session: AsyncSession, owner_id: UUID, classroom_id: UUID
) -> Classroom:
    classroom = await session.scalar(
        select(Classroom)
        .where(Classroom.id == classroom_id, Classroom.owner_id == owner_id)
        .with_for_update()
    )
    if classroom is None:
        raise NotFoundError()
    return classroom


async def _find_report(
    session: AsyncSession, owner_id: UUID, classroom_id: UUID
) -> Report | None:
    return await session.scalar(
        select(Report)
        .options(selectinload(Report.conclusions))
        .where(
            Report.owner_id == owner_id,
            Report.classroom_id == classroom_id,
        )
    )


async def _reportable_conclusions(
    session: AsyncSession, owner_id: UUID, classroom_id: UUID
) -> list[AnalysisConclusion]:
    return list(
        await session.scalars(
            select(AnalysisConclusion)
            .where(
                AnalysisConclusion.owner_id == owner_id,
                AnalysisConclusion.classroom_id == classroom_id,
                AnalysisConclusion.review_status.in_(REPORTABLE_REVIEW_STATUSES),
            )
            .order_by(AnalysisConclusion.created_at, AnalysisConclusion.id)
        )
    )


def _compose_report_content(conclusions: list[AnalysisConclusion]) -> str:
    parts: list[str] = []
    for conclusion in conclusions:
        status = ReviewStatus(conclusion.review_status)
        content = (
            conclusion.reviewed_content
            if status is ReviewStatus.MODIFIED
            else conclusion.content
        )
        if not (content or "").strip():
            raise ValueError("可报告结论缺少正文。")
        parts.append(f"- {(content or '').strip()}")
    return "\n".join(parts)


async def _sync_report_content(
    session: AsyncSession,
    report: Report,
    owner_id: UUID,
    classroom_id: UUID,
) -> None:
    reportable = await _reportable_conclusions(session, owner_id, classroom_id)
    report.conclusions = reportable
    report.content = _compose_report_content(reportable)
    await session.flush()


async def upsert_report(
    session: AsyncSession,
    *,
    owner_id: UUID,
    user: User,
    classroom_id: UUID,
    body: ReportUpdate,
) -> Report:
    await _lock_classroom(session, owner_id, classroom_id)
    report = await _find_report(session, owner_id, classroom_id)
    reportable = await _reportable_conclusions(session, owner_id, classroom_id)
    created = report is None
    if report is None:
        report = Report(
            owner_id=owner_id,
            classroom_id=classroom_id,
            title=body.title,
            content=_compose_report_content(reportable),
            conclusions=reportable,
        )
        session.add(report)
        await session.flush()
    else:
        report.title = body.title
        report.content = _compose_report_content(reportable)
        report.conclusions = reportable
    await session.flush()
    if not created:
        await session.refresh(report, attribute_names=["updated_at"])
    await record_audit_event(
        session,
        owner_id=owner_id,
        actor_user_id=user.id,
        action="report.created" if created else "report.updated",
        resource_type="report",
        resource_id=report.id,
        details={
            "updated_fields": ["title"],
            "included_conclusion_count": len(report.conclusions),
        },
    )
    return report

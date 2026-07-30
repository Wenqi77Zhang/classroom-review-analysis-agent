"""Owner-scoped review history and report persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent.reporting.composer import compose_reviewed_report
from backend.app.errors import NotFoundError
from backend.app.models import (
    AnalysisConclusion as AnalysisConclusionModel,
)
from backend.app.models import (
    AuditEvent,
    Classroom,
    Report,
    User,
)
from backend.app.models import (
    ReviewDecision as ReviewDecisionModel,
)
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    AnalysisConclusion,
    ReportRead,
    ReportUpdate,
    ReviewAction,
    ReviewDecision,
    ReviewRequest,
    ReviewStatus,
)


async def _conclusion(
    session: AsyncSession,
    owner_id: UUID,
    conclusion_id: UUID,
    *,
    for_update: bool = False,
) -> AnalysisConclusionModel:
    statement = (
        select(AnalysisConclusionModel)
        .where(
            AnalysisConclusionModel.id == conclusion_id,
            AnalysisConclusionModel.owner_id == owner_id,
        )
        .options(selectinload(AnalysisConclusionModel.evidence_refs))
    )
    if for_update:
        statement = statement.with_for_update()
    conclusion = await session.scalar(statement)
    if conclusion is None:
        raise NotFoundError()
    return conclusion


async def review_conclusion(
    session: AsyncSession,
    *,
    owner: User,
    conclusion_id: UUID,
    request: ReviewRequest,
    trace_id: str,
) -> AnalysisConclusion:
    conclusion = await _conclusion(session, owner.id, conclusion_id, for_update=True)
    previous_content = conclusion.reviewed_content or conclusion.content
    resulting_status = {
        ReviewAction.ACCEPT: ReviewStatus.ACCEPTED,
        ReviewAction.MODIFY: ReviewStatus.MODIFIED,
        ReviewAction.REJECT: ReviewStatus.REJECTED,
    }[request.action]
    edited_content = request.edited_content.strip() if request.edited_content else None
    decision = ReviewDecisionModel(
        owner_id=owner.id,
        conclusion_id=conclusion.id,
        action=request.action,
        resulting_status=resulting_status,
        previous_content=previous_content,
        edited_content=edited_content,
        note=request.note,
        decided_by_id=owner.id,
    )
    conclusion.review_status = resulting_status
    conclusion.reviewed_content = edited_content if resulting_status is ReviewStatus.MODIFIED else None
    session.add_all(
        [
            decision,
            AuditEvent(
                owner_id=owner.id,
                actor_user_id=owner.id,
                action="conclusion.reviewed",
                resource_type="analysis_conclusion",
                resource_id=conclusion.id,
                trace_id=trace_id,
                details={"action": request.action.value, "status": resulting_status.value},
            ),
        ]
    )
    await session.flush()
    await _refresh_existing_report(session, owner.id, conclusion.classroom_id)
    return AnalysisConclusion.model_validate(conclusion)


async def list_review_history(
    session: AsyncSession,
    *,
    owner_id: UUID,
    conclusion_id: UUID,
) -> list[ReviewDecision]:
    await _conclusion(session, owner_id, conclusion_id)
    decisions = (
        await session.scalars(
            select(ReviewDecisionModel)
            .where(
                ReviewDecisionModel.owner_id == owner_id,
                ReviewDecisionModel.conclusion_id == conclusion_id,
            )
            .options(selectinload(ReviewDecisionModel.decided_by))
            .order_by(ReviewDecisionModel.created_at, ReviewDecisionModel.id)
        )
    ).all()
    return [ReviewDecision.model_validate(item) for item in decisions]


async def _reportable_conclusions(
    session: AsyncSession,
    owner_id: UUID,
    classroom_id: UUID,
) -> list[AnalysisConclusionModel]:
    return list(
        (
            await session.scalars(
                select(AnalysisConclusionModel)
                .where(
                    AnalysisConclusionModel.owner_id == owner_id,
                    AnalysisConclusionModel.classroom_id == classroom_id,
                    AnalysisConclusionModel.review_status.in_(REPORTABLE_REVIEW_STATUSES),
                )
                .options(selectinload(AnalysisConclusionModel.evidence_refs))
                .order_by(AnalysisConclusionModel.created_at, AnalysisConclusionModel.id)
            )
        ).all()
    )


async def _get_report_model(
    session: AsyncSession,
    owner_id: UUID,
    classroom_id: UUID,
) -> Report | None:
    return await session.scalar(
        select(Report)
        .where(Report.owner_id == owner_id, Report.classroom_id == classroom_id)
        .options(selectinload(Report.conclusions))
    )


def _report_read(report: Report) -> ReportRead:
    return ReportRead(
        id=report.id,
        classroom_id=report.classroom_id,
        title=report.title,
        content=report.content,
        included_conclusion_ids=[item.id for item in report.conclusions],
        updated_at=report.updated_at,
    )


async def _compose_report(
    session: AsyncSession,
    report: Report,
) -> None:
    conclusions = await _reportable_conclusions(session, report.owner_id, report.classroom_id)
    composed = compose_reviewed_report(
        title=report.title,
        conclusions=[AnalysisConclusion.model_validate(item) for item in conclusions],
    )
    report.content = composed.content
    report.conclusions = conclusions


async def _refresh_existing_report(
    session: AsyncSession,
    owner_id: UUID,
    classroom_id: UUID,
) -> None:
    report = await _get_report_model(session, owner_id, classroom_id)
    if report is not None:
        await _compose_report(session, report)
        await session.flush()


async def get_report(
    session: AsyncSession,
    *,
    owner_id: UUID,
    classroom_id: UUID,
) -> ReportRead:
    report = await _get_report_model(session, owner_id, classroom_id)
    if report is None:
        raise NotFoundError()
    return _report_read(report)


async def put_report(
    session: AsyncSession,
    *,
    owner: User,
    classroom_id: UUID,
    update: ReportUpdate,
    trace_id: str,
) -> ReportRead:
    classroom = await session.scalar(
        select(Classroom).where(Classroom.id == classroom_id, Classroom.owner_id == owner.id)
    )
    if classroom is None:
        raise NotFoundError()
    report = await _get_report_model(session, owner.id, classroom_id)
    if report is None:
        report = Report(
            owner_id=owner.id,
            classroom_id=classroom_id,
            title=(update.title or f"{classroom.title}课堂复盘报告").strip(),
            conclusions=[],
        )
        session.add(report)
        await session.flush()
    elif update.title is not None:
        report.title = update.title.strip()

    await _compose_report(session, report)
    if update.content is not None:
        report.content = update.content
    session.add(
        AuditEvent(
            owner_id=owner.id,
            actor_user_id=owner.id,
            action="report.saved",
            resource_type="report",
            resource_id=report.id,
            trace_id=trace_id,
            details={"included_conclusion_count": len(report.conclusions)},
        )
    )
    await session.flush()
    return _report_read(report)

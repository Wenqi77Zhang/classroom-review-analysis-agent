"""Owner-scoped report persistence with a server-side review gate."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, get_db
from backend.app.models import Report, User
from backend.app.repositories.reviews import get_report, upsert_report
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    ReportRead,
    ReportUpdate,
    ReviewStatus,
)

router = APIRouter(tags=["reports"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _report_read(report: Report) -> ReportRead:
    included_ids = [
        item.id
        for item in report.conclusions
        if ReviewStatus(item.review_status) in REPORTABLE_REVIEW_STATUSES
    ]
    return ReportRead(
        id=report.id,
        classroom_id=report.classroom_id,
        title=report.title,
        content=report.content,
        included_conclusion_ids=included_ids,
        updated_at=report.updated_at,
    )


@router.get("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def get_classroom_report(
    classroom_id: UUID,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return _report_read(
        await get_report(session, owner_id=user.id, classroom_id=classroom_id)
    )


@router.put("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def put_classroom_report(
    classroom_id: UUID,
    body: ReportUpdate,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return _report_read(
        await upsert_report(
            session,
            owner_id=user.id,
            user=user,
            classroom_id=classroom_id,
            body=body,
        )
    )

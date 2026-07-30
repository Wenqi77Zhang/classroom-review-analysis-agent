"""Teacher-owned persisted report drafts built only from reviewed conclusions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, get_db
from backend.app.errors import current_trace_id
from backend.app.models import User
from backend.app.repositories.reviews import get_report, put_report
from backend.app.schemas.analysis_report import ReportRead, ReportUpdate

router = APIRouter(tags=["reports"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def get_classroom_report(
    classroom_id: UUID,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return await get_report(session, owner_id=user.id, classroom_id=classroom_id)


@router.put("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def put_classroom_report(
    classroom_id: UUID,
    body: ReportUpdate,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return await put_report(
        session,
        owner=user,
        classroom_id=classroom_id,
        update=body,
        trace_id=current_trace_id.get(),
    )

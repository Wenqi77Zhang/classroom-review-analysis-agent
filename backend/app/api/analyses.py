"""Evidence-grounded conclusion reads and the Agent write boundary."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import (
    get_current_user,
    get_db,
    require_service_identity,
)
from backend.app.errors import StateConflictError, current_trace_id
from backend.app.models import Classroom, User
from backend.app.repositories.results import (
    list_conclusions,
    replace_pending_conclusions,
)
from backend.app.repositories.reviews import list_review_history, review_conclusion
from backend.app.repositories.tasks import get_internal_task
from backend.app.schemas.analysis_report import (
    AnalysisConclusion,
    InternalConclusionBatchWrite,
    ReviewDecision,
    ReviewRequest,
)
from backend.app.schemas.task import ServiceIdentity, TaskStage, TaskStatus
from backend.app.services.permissions import get_owned_or_404

router = APIRouter(tags=["analyses"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AgentWriter = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:conclusions")),
]


@router.get(
    "/classrooms/{classroom_id}/conclusions",
    response_model=list[AnalysisConclusion],
)
async def get_conclusions(
    classroom_id: UUID,
    session: Db,
    user: CurrentUser,
) -> list[AnalysisConclusion]:
    await get_owned_or_404(session, Classroom, classroom_id, user.id)
    return [
        AnalysisConclusion.model_validate(item)
        for item in await list_conclusions(session, user.id, classroom_id)
    ]


@router.post(
    "/conclusions/{conclusion_id}/review",
    response_model=AnalysisConclusion,
)
async def post_conclusion_review(
    conclusion_id: UUID,
    body: ReviewRequest,
    session: Db,
    user: CurrentUser,
) -> AnalysisConclusion:
    return await review_conclusion(
        session,
        owner=user,
        conclusion_id=conclusion_id,
        request=body,
        trace_id=current_trace_id.get(),
    )


@router.get(
    "/conclusions/{conclusion_id}/history",
    response_model=list[ReviewDecision],
)
async def get_conclusion_history(
    conclusion_id: UUID,
    session: Db,
    user: CurrentUser,
) -> list[ReviewDecision]:
    return await list_review_history(
        session,
        owner_id=user.id,
        conclusion_id=conclusion_id,
    )


@router.post(
    "/internal/tasks/{task_id}/conclusions",
    response_model=list[AnalysisConclusion],
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_conclusions(
    task_id: UUID,
    body: InternalConclusionBatchWrite,
    session: Db,
    _identity: AgentWriter,
) -> list[AnalysisConclusion]:
    task = await get_internal_task(session, task_id)
    if TaskStatus(task.status) is not TaskStatus.RUNNING:
        raise StateConflictError("只有运行中的任务可以写入分析结论。")
    if TaskStage(task.stage) is not TaskStage.ANALYZE:
        raise StateConflictError("只有 analyze 阶段可以写入分析结论。")
    await replace_pending_conclusions(session, task, body)
    return [
        AnalysisConclusion.model_validate(item)
        for item in await list_conclusions(session, task.owner_id, task.classroom_id)
        if item.task_id == task.id
    ]

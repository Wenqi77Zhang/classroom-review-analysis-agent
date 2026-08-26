"""Teacher reads and Worker writes for page-aligned courseware evidence."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, get_db, require_service_identity
from backend.app.errors import StateConflictError
from backend.app.models import User
from backend.app.repositories.results import get_courseware_pages, replace_courseware_pages
from backend.app.repositories.tasks import get_internal_task
from backend.app.schemas.courseware import CoursewarePageRead, InternalCoursewareWrite
from backend.app.schemas.task import ServiceIdentity, TaskStage, TaskStatus

router = APIRouter(tags=["courseware"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
WorkerWriter = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:courseware")),
]


@router.get("/tasks/{task_id}/courseware", response_model=list[CoursewarePageRead])
async def get_task_courseware(
    task_id: UUID,
    session: Db,
    user: CurrentUser,
) -> list[CoursewarePageRead]:
    return [
        CoursewarePageRead.model_validate(page)
        for page in await get_courseware_pages(session, user.id, task_id)
    ]


@router.post(
    "/internal/tasks/{task_id}/courseware",
    response_model=list[CoursewarePageRead],
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_courseware(
    task_id: UUID,
    body: InternalCoursewareWrite,
    session: Db,
    _identity: WorkerWriter,
) -> list[CoursewarePageRead]:
    task = await get_internal_task(session, task_id)
    if TaskStatus(task.status) is not TaskStatus.RUNNING:
        raise StateConflictError("只有运行中的任务可以写入课件证据。")
    if TaskStage(task.stage) is not TaskStage.PARSE_COURSEWARE:
        raise StateConflictError("只有 parse_courseware 阶段可以写入课件证据。")
    if body.trace_id is not None and body.trace_id != task.trace_id:
        raise StateConflictError("课件证据 trace_id 必须与当前任务一致。")
    return [
        CoursewarePageRead.model_validate(page)
        for page in await replace_courseware_pages(session, task, body)
    ]

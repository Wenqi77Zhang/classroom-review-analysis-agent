"""Owner-scoped course and limited classroom management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, get_db
from backend.app.errors import StateConflictError
from backend.app.models import Classroom, ImprovementCycle, ProcessingTask, User
from backend.app.repositories.identity import (
    create_classroom,
    create_course,
    list_classrooms,
    list_courses,
)
from backend.app.schemas.identity import (
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
    CourseCreate,
    CourseRead,
)
from backend.app.schemas.task import TaskStatus
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404
from backend.app.services.storage import ObjectStorage, get_object_storage

router = APIRouter(tags=["classrooms"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def post_course(body: CourseCreate, session: Db, user: CurrentUser) -> CourseRead:
    course = await create_course(session, user.id, name=body.name, description=body.description)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="course.created",
        resource_type="course",
        resource_id=course.id,
    )
    return CourseRead.model_validate(course)


@router.get("/courses", response_model=list[CourseRead])
async def get_courses(session: Db, user: CurrentUser) -> list[CourseRead]:
    return [CourseRead.model_validate(row) for row in await list_courses(session, user.id)]


@router.post(
    "/courses/{course_id}/classrooms",
    response_model=ClassroomRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_classroom(
    course_id: UUID, body: ClassroomCreate, session: Db, user: CurrentUser
) -> ClassroomRead:
    classroom = await create_classroom(
        session,
        user.id,
        course_id,
        title=body.title,
        description=body.description,
        analysis_contract=body.analysis_contract,
    )
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="classroom.created",
        resource_type="classroom",
        resource_id=classroom.id,
        details={"course_id": str(course_id)},
    )
    return ClassroomRead.model_validate(classroom)


@router.get("/courses/{course_id}/classrooms", response_model=list[ClassroomRead])
async def get_classrooms(course_id: UUID, session: Db, user: CurrentUser) -> list[ClassroomRead]:
    return [
        ClassroomRead.model_validate(row)
        for row in await list_classrooms(session, user.id, course_id)
    ]


@router.get("/classrooms/{classroom_id}", response_model=ClassroomRead)
async def get_classroom(classroom_id: UUID, session: Db, user: CurrentUser) -> ClassroomRead:
    classroom = await get_owned_or_404(session, Classroom, classroom_id, user.id)
    return ClassroomRead.model_validate(classroom)


@router.patch("/classrooms/{classroom_id}", response_model=ClassroomRead)
async def patch_classroom(
    classroom_id: UUID, body: ClassroomUpdate, session: Db, user: CurrentUser
) -> ClassroomRead:
    classroom = await get_owned_or_404(session, Classroom, classroom_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(classroom, field, value)
    await session.flush()
    # updated_at is database-generated on UPDATE. Load it before synchronous response serialization.
    await session.refresh(classroom)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="classroom.updated",
        resource_type="classroom",
        resource_id=classroom.id,
        details={"updated_fields": sorted(changes)},
    )
    return ClassroomRead.model_validate(classroom)


@router.delete("/classrooms/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classroom(
    classroom_id: UUID,
    session: Db,
    user: CurrentUser,
    storage: Storage,
) -> None:
    classroom = await get_owned_or_404(session, Classroom, classroom_id, user.id)
    active_count = await session.scalar(
        select(func.count(ProcessingTask.id)).where(
            ProcessingTask.owner_id == user.id,
            ProcessingTask.classroom_id == classroom_id,
            ProcessingTask.status.in_(
                [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]
            ),
        )
    )
    if active_count:
        raise StateConflictError("课堂仍有处理中的任务，请先等待完成或取消任务后再删除。")

    improvement_reference_count = await session.scalar(
        select(func.count(ImprovementCycle.id)).where(
            ImprovementCycle.owner_id == user.id,
            or_(
                ImprovementCycle.baseline_classroom_id == classroom_id,
                ImprovementCycle.followup_classroom_id == classroom_id,
            ),
        )
    )
    if improvement_reference_count:
        raise StateConflictError("课堂已被改进循环引用，请先处理对应改进循环后再删除。")

    prefix = f"owners/{user.id}/classrooms/{classroom_id}/"
    deleted_object_count = await storage.delete_prefix(prefix)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="classroom.deleted",
        resource_type="classroom",
        resource_id=classroom.id,
        details={"deleted_object_count": deleted_object_count},
    )
    await session.delete(classroom)

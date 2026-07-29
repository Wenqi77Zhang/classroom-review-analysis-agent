"""Owner-scoped course and limited classroom management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, get_db
from backend.app.errors import StateConflictError
from backend.app.models import Classroom, User
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
from backend.app.services.permissions import get_owned_or_404

router = APIRouter(tags=["classrooms"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def post_course(body: CourseCreate, session: Db, user: CurrentUser) -> CourseRead:
    course = await create_course(session, user.id, name=body.name, description=body.description)
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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(classroom, field, value)
    await session.flush()
    # updated_at is database-generated on UPDATE. Load it before synchronous response serialization.
    await session.refresh(classroom)
    return ClassroomRead.model_validate(classroom)


@router.delete("/classrooms/{classroom_id}", status_code=status.HTTP_409_CONFLICT)
async def delete_classroom(classroom_id: UUID, session: Db, user: CurrentUser) -> None:
    await get_owned_or_404(session, Classroom, classroom_id, user.id)
    raise StateConflictError(
        "课堂删除尚未启用：对象存储清理与删除审计实现后方可执行。"
    )

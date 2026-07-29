"""Owner-scoped user, course, and classroom persistence operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Classroom, Course, User
from backend.app.services.permissions import get_owned_or_404


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email.strip().lower()))


async def create_course(
    session: AsyncSession, owner_id: UUID, *, name: str, description: str | None
) -> Course:
    course = Course(owner_id=owner_id, name=name.strip(), description=description)
    session.add(course)
    await session.flush()
    return course


async def list_courses(session: AsyncSession, owner_id: UUID) -> list[Course]:
    rows = await session.scalars(
        select(Course).where(Course.owner_id == owner_id).order_by(Course.created_at.desc())
    )
    return list(rows)


async def create_classroom(
    session: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    *,
    title: str,
    description: str | None,
    analysis_contract: dict[str, object],
) -> Classroom:
    await get_owned_or_404(session, Course, course_id, owner_id)
    classroom = Classroom(
        owner_id=owner_id,
        course_id=course_id,
        title=title.strip(),
        description=description,
        analysis_contract=analysis_contract,
    )
    session.add(classroom)
    await session.flush()
    return classroom


async def list_classrooms(
    session: AsyncSession, owner_id: UUID, course_id: UUID
) -> list[Classroom]:
    await get_owned_or_404(session, Course, course_id, owner_id)
    rows = await session.scalars(
        select(Classroom)
        .where(Classroom.owner_id == owner_id, Classroom.course_id == course_id)
        .order_by(Classroom.created_at.desc())
    )
    return list(rows)

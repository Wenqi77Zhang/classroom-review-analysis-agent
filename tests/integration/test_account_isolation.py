"""Real PostgreSQL account-isolation checks for owner-scoped resources."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.config import get_settings
from backend.app.errors import NotFoundError
from backend.app.models import Classroom, Course, User
from backend.app.services.permissions import assert_same_owner, get_owned_or_404


@pytest.mark.asyncio
async def test_two_accounts_cannot_read_each_others_classroom() -> None:
    engine = create_async_engine(get_settings().database_url.get_secret_value())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_id, second_id = uuid.uuid4(), uuid.uuid4()

    try:
        async with factory.begin() as session:
            first = User(
                id=first_id,
                email=f"isolation-{first_id}@example.invalid",
                display_name="First",
                password_hash="test-only",
            )
            second = User(
                id=second_id,
                email=f"isolation-{second_id}@example.invalid",
                display_name="Second",
                password_hash="test-only",
            )
            first_classroom = Classroom(
                owner_id=first_id,
                course=Course(owner_id=first_id, name="First course"),
                title="First classroom",
            )
            second_classroom = Classroom(
                owner_id=second_id,
                course=Course(owner_id=second_id, name="Second course"),
                title="Second classroom",
            )
            session.add_all([first, second, first_classroom, second_classroom])

        async with factory() as session:
            own = await get_owned_or_404(session, Classroom, first_classroom.id, first_id)
            assert own.id == first_classroom.id
            with pytest.raises(NotFoundError):
                await get_owned_or_404(session, Classroom, first_classroom.id, second_id)
            with pytest.raises(NotFoundError):
                await get_owned_or_404(session, Classroom, uuid.uuid4(), second_id)

            assert_same_owner(first_id, first_classroom)
            with pytest.raises(NotFoundError):
                assert_same_owner(first_id, second_classroom)
    finally:
        async with factory.begin() as session:
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

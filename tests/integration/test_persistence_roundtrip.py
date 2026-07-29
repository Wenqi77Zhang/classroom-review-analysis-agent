"""Real PostgreSQL persistence smoke test.

Requires the local-infra PostgreSQL service and an upgraded Alembic schema.
"""

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models import Asset, Classroom, Course, ProcessingTask, User
from backend.app.schemas.task import AssetKind, PrivacyMode, TaskStage, TaskStatus, UploadStatus


@pytest.mark.asyncio
async def test_core_ownership_chain_survives_a_new_session() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id = uuid.uuid4()
    classroom_id = uuid.uuid4()
    task_id = uuid.uuid4()

    try:
        async with factory.begin() as session:
            session: AsyncSession
            user = User(
                id=owner_id,
                email=f"persistence-{owner_id}@example.invalid",
                display_name="Persistence Test",
                password_hash="not-a-real-password-hash",
            )
            course = Course(owner_id=owner_id, name="Persistence Course")
            classroom = Classroom(
                id=classroom_id,
                owner_id=owner_id,
                course=course,
                title="Persistence Classroom",
            )
            asset = Asset(
                owner_id=owner_id,
                classroom=classroom,
                kind=AssetKind.VIDEO,
                filename="fixture.mp4",
                content_type="video/mp4",
                size_bytes=1024,
                upload_status=UploadStatus.UPLOADED,
                object_key=f"tests/{owner_id}/fixture.mp4",
            )
            task = ProcessingTask(
                id=task_id,
                owner_id=owner_id,
                classroom=classroom,
                status=TaskStatus.QUEUED,
                stage=TaskStage.UPLOADED,
                progress=0,
                privacy_mode=PrivacyMode.LOCAL,
                assets=[asset],
            )
            session.add(user)
            session.add(task)

        async with factory() as session:
            persisted = await session.scalar(
                select(ProcessingTask).where(
                    ProcessingTask.id == task_id,
                    ProcessingTask.owner_id == owner_id,
                )
            )
            assert persisted is not None
            assert persisted.classroom_id == classroom_id
            assert persisted.status == TaskStatus.QUEUED
    finally:
        async with factory.begin() as session:
            persisted_user = await session.get(User, owner_id)
            if persisted_user is not None:
                await session.delete(persisted_user)
        await engine.dispose()

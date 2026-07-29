"""Real PostgreSQL account-isolation checks for owner-scoped resources."""

import os
import uuid

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.errors import NotFoundError
from backend.app.models import (
    AnalysisConclusion,
    Asset,
    AuditEvent,
    Classroom,
    Course,
    EvidenceReference,
    ProcessingTask,
    Report,
    User,
    report_conclusions,
    task_assets,
)
from backend.app.schemas.analysis_report import ConclusionType, EvidenceSourceType
from backend.app.schemas.task import AssetKind
from backend.app.services.permissions import assert_same_owner, get_owned_or_404


def _database_factory():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(database_url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_two_owner_graph(factory):
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    first_course_id, second_course_id = uuid.uuid4(), uuid.uuid4()
    first_classroom_id, second_classroom_id = uuid.uuid4(), uuid.uuid4()
    first_task_id, second_task_id = uuid.uuid4(), uuid.uuid4()
    first_asset_id, second_asset_id = uuid.uuid4(), uuid.uuid4()
    first_conclusion_id, second_conclusion_id = uuid.uuid4(), uuid.uuid4()
    first_report_id, second_report_id = uuid.uuid4(), uuid.uuid4()

    async with factory.begin() as session:
        session.add_all(
            [
                User(
                    id=first_id,
                    email=f"isolation-{first_id}@example.invalid",
                    display_name="First",
                    password_hash="test-only",
                ),
                User(
                    id=second_id,
                    email=f"isolation-{second_id}@example.invalid",
                    display_name="Second",
                    password_hash="test-only",
                ),
                Course(id=first_course_id, owner_id=first_id, name="First course"),
                Course(id=second_course_id, owner_id=second_id, name="Second course"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                Classroom(
                    id=first_classroom_id,
                    owner_id=first_id,
                    course_id=first_course_id,
                    title="First classroom",
                ),
                Classroom(
                    id=second_classroom_id,
                    owner_id=second_id,
                    course_id=second_course_id,
                    title="Second classroom",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProcessingTask(
                    id=first_task_id,
                    owner_id=first_id,
                    classroom_id=first_classroom_id,
                ),
                ProcessingTask(
                    id=second_task_id,
                    owner_id=second_id,
                    classroom_id=second_classroom_id,
                ),
                Asset(
                    id=first_asset_id,
                    owner_id=first_id,
                    classroom_id=first_classroom_id,
                    kind=AssetKind.VIDEO,
                    filename="first.mp4",
                    content_type="video/mp4",
                    size_bytes=1024,
                    object_key=f"tests/{first_id}/first.mp4",
                ),
                Asset(
                    id=second_asset_id,
                    owner_id=second_id,
                    classroom_id=second_classroom_id,
                    kind=AssetKind.VIDEO,
                    filename="second.mp4",
                    content_type="video/mp4",
                    size_bytes=1024,
                    object_key=f"tests/{second_id}/second.mp4",
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                AnalysisConclusion(
                    id=first_conclusion_id,
                    owner_id=first_id,
                    classroom_id=first_classroom_id,
                    task_id=first_task_id,
                    type=ConclusionType.FACT,
                    content="First conclusion",
                    trace_id=str(uuid.uuid4()),
                ),
                AnalysisConclusion(
                    id=second_conclusion_id,
                    owner_id=second_id,
                    classroom_id=second_classroom_id,
                    task_id=second_task_id,
                    type=ConclusionType.FACT,
                    content="Second conclusion",
                    trace_id=str(uuid.uuid4()),
                ),
                Report(
                    id=first_report_id,
                    owner_id=first_id,
                    classroom_id=first_classroom_id,
                    title="First report",
                ),
                Report(
                    id=second_report_id,
                    owner_id=second_id,
                    classroom_id=second_classroom_id,
                    title="Second report",
                ),
            ]
        )

    return {
        "first_id": first_id,
        "second_id": second_id,
        "first_course_id": first_course_id,
        "second_course_id": second_course_id,
        "first_classroom_id": first_classroom_id,
        "second_classroom_id": second_classroom_id,
        "first_task_id": first_task_id,
        "second_task_id": second_task_id,
        "first_asset_id": first_asset_id,
        "second_asset_id": second_asset_id,
        "first_conclusion_id": first_conclusion_id,
        "second_conclusion_id": second_conclusion_id,
        "first_report_id": first_report_id,
        "second_report_id": second_report_id,
    }


async def _cleanup_users(factory, *user_ids: uuid.UUID) -> None:
    async with factory.begin() as session:
        await session.execute(delete(User).where(User.id.in_(user_ids)))


@pytest.mark.asyncio
async def test_two_accounts_cannot_read_each_others_classroom() -> None:
    engine, factory = _database_factory()
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


@pytest.mark.asyncio
async def test_cross_owner_course_classroom_write_is_rejected() -> None:
    engine, factory = _database_factory()
    graph = await _seed_two_owner_graph(factory)
    try:
        with pytest.raises(IntegrityError):
            async with factory.begin() as session:
                session.add(
                    Classroom(
                        owner_id=graph["first_id"],
                        course_id=graph["second_course_id"],
                        title="Cross-owner classroom",
                    )
                )
    finally:
        await _cleanup_users(factory, graph["first_id"], graph["second_id"])
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_owner_task_asset_write_is_rejected() -> None:
    engine, factory = _database_factory()
    graph = await _seed_two_owner_graph(factory)
    try:
        with pytest.raises(IntegrityError):
            async with factory.begin() as session:
                await session.execute(
                    insert(task_assets).values(
                        task_id=graph["first_task_id"],
                        asset_id=graph["second_asset_id"],
                        owner_id=graph["first_id"],
                    )
                )
    finally:
        await _cleanup_users(factory, graph["first_id"], graph["second_id"])
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_owner_conclusion_evidence_write_is_rejected() -> None:
    engine, factory = _database_factory()
    graph = await _seed_two_owner_graph(factory)
    try:
        with pytest.raises(IntegrityError):
            async with factory.begin() as session:
                session.add(
                    EvidenceReference(
                        owner_id=graph["first_id"],
                        conclusion_id=graph["first_conclusion_id"],
                        source_type=EvidenceSourceType.VIDEO,
                        asset_id=graph["second_asset_id"],
                    )
                )
    finally:
        await _cleanup_users(factory, graph["first_id"], graph["second_id"])
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_owner_report_conclusion_write_is_rejected() -> None:
    engine, factory = _database_factory()
    graph = await _seed_two_owner_graph(factory)
    try:
        with pytest.raises(IntegrityError):
            async with factory.begin() as session:
                await session.execute(
                    insert(report_conclusions).values(
                        report_id=graph["first_report_id"],
                        conclusion_id=graph["second_conclusion_id"],
                        owner_id=graph["first_id"],
                    )
                )
    finally:
        await _cleanup_users(factory, graph["first_id"], graph["second_id"])
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_event_blocks_user_deletion_and_survives_rollback() -> None:
    engine, factory = _database_factory()
    owner_id, event_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with factory.begin() as session:
            session.add(
                User(
                    id=owner_id,
                    email=f"audit-retention-{owner_id}@example.invalid",
                    display_name="Audit Retention",
                    password_hash="test-only",
                )
            )
            session.add(
                AuditEvent(
                    id=event_id,
                    owner_id=owner_id,
                    actor_user_id=owner_id,
                    action="test.retention",
                    resource_type="user",
                    resource_id=owner_id,
                )
            )

        with pytest.raises(IntegrityError):
            async with factory.begin() as session:
                await session.execute(delete(User).where(User.id == owner_id))

        async with factory.begin() as session:
            assert await session.scalar(
                select(AuditEvent.id).where(AuditEvent.id == event_id)
            ) == event_id
            await session.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
            await session.execute(delete(User).where(User.id == owner_id))
    finally:
        await engine.dispose()

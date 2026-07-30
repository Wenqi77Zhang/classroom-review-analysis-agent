"""Real PostgreSQL coverage for review history, report gates, and audit metadata."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.dependencies import get_db
from backend.app.main import create_app
from backend.app.models import (
    AnalysisConclusion,
    AuditEvent,
    Classroom,
    Course,
    ProcessingTask,
    Report,
    ReviewDecision,
    User,
)
from backend.app.models.review_report import report_conclusions
from backend.app.schemas.analysis_report import ConclusionType, ReviewStatus
from backend.app.schemas.task import TaskStage, TaskStatus
from backend.app.services.authentication import hash_password


def api_settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        jwt_secret="review-test-jwt-secret-at-least-thirty-two-characters",
        demo_account_password=None,
        worker_service_token="review-test-worker-token",
        agent_service_token="review-test-agent-token",
        object_storage_endpoint="http://localhost:9000",
        object_storage_bucket="review-test",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
    )


@pytest.mark.asyncio
async def test_review_history_report_gate_audit_and_owner_isolation() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    settings = api_settings(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    first_email = f"first-review-{first_id}@example.invalid"
    second_email = f"second-review-{second_id}@example.invalid"
    course_id, classroom_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conclusion_ids = [uuid.uuid4() for _ in range(4)]

    async def test_db() -> AsyncIterator:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    app = create_app(settings)
    app.dependency_overrides[get_db] = test_db

    try:
        async with factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=first_id,
                        email=first_email,
                        display_name="First Reviewer",
                        password_hash=hash_password("first-password"),
                    ),
                    User(
                        id=second_id,
                        email=second_email,
                        display_name="Second Reviewer",
                        password_hash=hash_password("second-password"),
                    ),
                ]
            )
            await session.flush()
            session.add(Course(id=course_id, owner_id=first_id, name="Review Course"))
            await session.flush()
            session.add(
                Classroom(
                    id=classroom_id,
                    owner_id=first_id,
                    course_id=course_id,
                    title="Evidence Lecture",
                )
            )
            await session.flush()
            session.add(
                ProcessingTask(
                    id=task_id,
                    owner_id=first_id,
                    classroom_id=classroom_id,
                    status=TaskStatus.SUCCEEDED,
                    stage=TaskStage.ANALYZE,
                    progress=1.0,
                )
            )
            await session.flush()
            session.add_all(
                [
                    AnalysisConclusion(
                        id=conclusion_id,
                        owner_id=first_id,
                        classroom_id=classroom_id,
                        task_id=task_id,
                        type=ConclusionType.SUGGESTION,
                        content=f"model-content-{index}",
                        review_status=ReviewStatus.PENDING,
                        trace_id=f"review-trace-{index}",
                    )
                    for index, conclusion_id in enumerate(conclusion_ids)
                ]
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def token(email: str, password: str) -> str:
                response = await client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                )
                assert response.status_code == 200
                return response.json()["access_token"]

            first_headers = {
                "Authorization": f"Bearer {await token(first_email, 'first-password')}"
            }
            second_headers = {
                "Authorization": f"Bearer {await token(second_email, 'second-password')}"
            }

            missing_report = await client.get(
                f"/api/classrooms/{classroom_id}/report", headers=first_headers
            )
            assert missing_report.status_code == 404

            accepted = await client.post(
                f"/api/conclusions/{conclusion_ids[0]}/review",
                json={"action": "accept", "note": "private teacher note"},
                headers=first_headers,
            )
            assert accepted.status_code == 201
            assert accepted.json()["resulting_status"] == "accepted"

            modified = await client.post(
                f"/api/conclusions/{conclusion_ids[1]}/review",
                json={"action": "modify", "edited_content": "  teacher revision  "},
                headers=first_headers,
            )
            assert modified.status_code == 201
            assert modified.json()["edited_content"] == "teacher revision"

            rejected = await client.post(
                f"/api/conclusions/{conclusion_ids[2]}/review",
                json={"action": "reject"},
                headers=first_headers,
            )
            assert rejected.status_code == 201
            assert rejected.json()["resulting_status"] == "rejected"

            history = await client.get(
                f"/api/conclusions/{conclusion_ids[1]}/history", headers=first_headers
            )
            assert history.status_code == 200
            assert len(history.json()) == 1
            assert history.json()[0]["decided_by"] == {
                "id": str(first_id),
                "display_name": "First Reviewer",
            }

            cross_account_review = await client.post(
                f"/api/conclusions/{conclusion_ids[3]}/review",
                json={"action": "accept"},
                headers=second_headers,
            )
            assert cross_account_review.status_code == 404
            cross_account_history = await client.get(
                f"/api/conclusions/{conclusion_ids[0]}/history",
                headers=second_headers,
            )
            assert cross_account_history.status_code == 404

            invalid_title = await client.put(
                f"/api/classrooms/{classroom_id}/report",
                json={"title": "   "},
                headers=first_headers,
            )
            assert invalid_title.status_code == 422

            report = await client.put(
                f"/api/classrooms/{classroom_id}/report",
                json={"title": "  Reviewed Report  ", "content": "teacher-authored report"},
                headers=first_headers,
            )
            assert report.status_code == 200
            assert report.json()["title"] == "Reviewed Report"
            assert report.json()["included_conclusion_ids"] == sorted(
                [str(conclusion_ids[0]), str(conclusion_ids[1])]
            )

            cross_account_report = await client.get(
                f"/api/classrooms/{classroom_id}/report", headers=second_headers
            )
            assert cross_account_report.status_code == 404

            rejected_after_report = await client.post(
                f"/api/conclusions/{conclusion_ids[0]}/review",
                json={"action": "reject"},
                headers=first_headers,
            )
            assert rejected_after_report.status_code == 201

            gated_report = await client.get(
                f"/api/classrooms/{classroom_id}/report", headers=first_headers
            )
            assert gated_report.status_code == 200
            assert gated_report.json()["included_conclusion_ids"] == [
                str(conclusion_ids[1])
            ]

        async with factory() as session:
            stored_report = await session.scalar(
                select(Report).where(Report.classroom_id == classroom_id)
            )
            assert stored_report is not None
            events = list(
                await session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.owner_id == first_id)
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            )
            assert [event.action for event in events] == [
                "conclusion.reviewed",
                "conclusion.reviewed",
                "conclusion.reviewed",
                "report.created",
                "conclusion.reviewed",
            ]
            serialized_details = repr([event.details for event in events])
            assert "private teacher note" not in serialized_details
            assert "teacher revision" not in serialized_details
            assert "teacher-authored report" not in serialized_details
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(report_conclusions).where(report_conclusions.c.owner_id.in_([first_id, second_id]))
            )
            await session.execute(delete(Report).where(Report.owner_id.in_([first_id, second_id])))
            await session.execute(
                delete(AuditEvent).where(AuditEvent.owner_id.in_([first_id, second_id]))
            )
            await session.execute(
                delete(ReviewDecision).where(
                    ReviewDecision.owner_id.in_([first_id, second_id])
                )
            )
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

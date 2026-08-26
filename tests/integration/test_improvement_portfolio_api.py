"""Real PostgreSQL coverage for M2/M3 ownership, gates, and aggregation."""

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
    EvidenceReference,
    ProcessingTask,
    User,
)
from backend.app.schemas.analysis_report import ConclusionType, EvidenceSourceType, ReviewStatus
from backend.app.schemas.task import TaskStage, TaskStatus
from backend.app.services.authentication import hash_password


def settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        jwt_secret="improvement-test-jwt-secret-at-least-thirty-two-characters",
        demo_account_password=None,
        worker_service_token="improvement-worker-token",
        agent_service_token="improvement-agent-token",
        object_storage_endpoint="http://localhost:9000",
        object_storage_bucket="improvement-test",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
    )


@pytest.mark.asyncio
async def test_real_improvement_cycle_and_portfolio_gates() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id, outsider_id = uuid.uuid4(), uuid.uuid4()
    owner_email = f"m2-owner-{owner_id}@example.invalid"
    outsider_email = f"m2-outsider-{outsider_id}@example.invalid"
    course_id, other_course_id = uuid.uuid4(), uuid.uuid4()
    baseline_id, followup_id, wrong_followup_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    baseline_task_id, followup_task_id = uuid.uuid4(), uuid.uuid4()
    baseline_conclusion_id, followup_conclusion_id = uuid.uuid4(), uuid.uuid4()

    async def database() -> AsyncIterator:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    app = create_app(settings(database_url))
    app.dependency_overrides[get_db] = database
    try:
        async with factory.begin() as session:
            session.add_all([
                User(id=owner_id, email=owner_email, display_name="M2 Owner", password_hash=hash_password("owner-password")),
                User(id=outsider_id, email=outsider_email, display_name="Outsider", password_hash=hash_password("outsider-password")),
            ])
            await session.flush()
            session.add_all([
                Course(id=course_id, owner_id=owner_id, name="AI Course"),
                Course(id=other_course_id, owner_id=owner_id, name="Other Course"),
            ])
            await session.flush()
            session.add_all([
                Classroom(id=baseline_id, owner_id=owner_id, course_id=course_id, title="Round One"),
                Classroom(id=followup_id, owner_id=owner_id, course_id=course_id, title="Round Two"),
                Classroom(id=wrong_followup_id, owner_id=owner_id, course_id=other_course_id, title="Wrong Course"),
            ])
            await session.flush()
            session.add_all([
                ProcessingTask(id=baseline_task_id, owner_id=owner_id, classroom_id=baseline_id, status=TaskStatus.SUCCEEDED, stage=TaskStage.ANALYZE, progress=1.0),
                ProcessingTask(id=followup_task_id, owner_id=owner_id, classroom_id=followup_id, status=TaskStatus.SUCCEEDED, stage=TaskStage.ANALYZE, progress=1.0),
            ])
            await session.flush()
            session.add_all([
                AnalysisConclusion(id=baseline_conclusion_id, owner_id=owner_id, classroom_id=baseline_id, task_id=baseline_task_id, type=ConclusionType.SUGGESTION, content="关键提问后增加等待时间并邀请学生回应", reviewed_content="关键提问后等待五秒再邀请学生回应", review_status=ReviewStatus.MODIFIED, trace_id="baseline-trace"),
                AnalysisConclusion(id=followup_conclusion_id, owner_id=owner_id, classroom_id=followup_id, task_id=followup_task_id, type=ConclusionType.JUDGMENT, content="等待时间增加，学生回应更充分", review_status=ReviewStatus.ACCEPTED, trace_id="followup-trace"),
            ])
            await session.flush()
            session.add_all([
                EvidenceReference(owner_id=owner_id, conclusion_id=baseline_conclusion_id, source_type=EvidenceSourceType.COURSEWARE, page_no=1, quote="第一轮提问与回应证据"),
                EvidenceReference(owner_id=owner_id, conclusion_id=followup_conclusion_id, source_type=EvidenceSourceType.COURSEWARE, page_no=1, quote="第二轮提问与回应证据"),
            ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def login(email: str, password: str) -> dict[str, str]:
                response = await client.post("/api/auth/login", json={"email": email, "password": password})
                assert response.status_code == 200
                return {"Authorization": f"Bearer {response.json()['access_token']}"}

            owner_headers = await login(owner_email, "owner-password")
            outsider_headers = await login(outsider_email, "outsider-password")
            created = await client.post("/api/improvement-cycles", headers=owner_headers, json={"baseline_classroom_id": str(baseline_id), "title": "Question Wait Cycle", "objective": "Observe longer wait and more student responses", "validation_mode": "real"})
            assert created.status_code == 201, created.text
            cycle_id = created.json()["id"]

            hidden = await client.get(f"/api/improvement-cycles/{cycle_id}", headers=outsider_headers)
            assert hidden.status_code == 404

            action = await client.post(f"/api/improvement-cycles/{cycle_id}/actions", headers=owner_headers, json={"source_conclusion_id": str(baseline_conclusion_id), "action_text": "关键提问后等待五秒", "success_criterion": "第二轮证据出现更充分的学生回应", "priority": 1})
            assert action.status_code == 201, action.text

            wrong_course = await client.patch(f"/api/improvement-cycles/{cycle_id}", headers=owner_headers, json={"followup_classroom_id": str(wrong_followup_id)})
            assert wrong_course.status_code == 400

            linked = await client.patch(f"/api/improvement-cycles/{cycle_id}", headers=owner_headers, json={"followup_classroom_id": str(followup_id)})
            assert linked.status_code == 200

            compared = await client.post(f"/api/improvement-cycles/{cycle_id}/comparisons", headers=owner_headers, json={})
            assert compared.status_code == 201, compared.text
            comparison = compared.json()[0]
            assert comparison["proposed_outcome"] == "improved"
            assert comparison["review_status"] == "pending"

            reviewed = await client.post(f"/api/improvement-comparisons/{comparison['id']}/review", headers=owner_headers, json={"action": "modify", "edited_summary": "教师核对两轮证据后，确认本轮出现了更充分的学生回应。"})
            assert reviewed.status_code == 200, reviewed.text
            assert reviewed.json()["review_status"] == "modified"

            overview = await client.get("/api/portfolio/overview", headers=owner_headers)
            assert overview.status_code == 200
            assert overview.json()["course_count"] == 2
            assert overview.json()["completed_cycle_count"] == 1

            report = await client.get("/api/portfolio/aggregate-report", headers=owner_headers)
            assert report.status_code == 200
            assert report.json()["included_cycle_ids"] == [cycle_id]
            assert "教师核对两轮证据后" in report.json()["content"]
    finally:
        async with factory.begin() as session:
            test_user_ids = list(
                (
                    await session.scalars(
                        select(User.id).where(User.email.like("m2-%@example.invalid"))
                    )
                ).all()
            )
            if test_user_ids:
                await session.execute(
                    delete(AuditEvent).where(AuditEvent.owner_id.in_(test_user_ids))
                )
                await session.execute(delete(User).where(User.id.in_(test_user_ids)))
        await engine.dispose()

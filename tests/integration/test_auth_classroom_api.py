"""Real HTTP and PostgreSQL tests for authentication and classroom ownership."""

from __future__ import annotations

import os
import uuid
from collections import Counter
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.dependencies import get_db
from backend.app.main import create_app
from backend.app.models import AuditEvent, User
from backend.app.schemas.review_dialogue import ReviewDialogueResponse
from backend.app.schemas.task import AnalysisContract
from backend.app.services.authentication import hash_password


class DeletionRecordingStorage:
    def __init__(self) -> None:
        self.deleted_prefixes: list[str] = []

    async def delete_prefix(self, prefix: str) -> int:
        self.deleted_prefixes.append(prefix)
        return 3


class RecordingReviewClarifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def clarify(self, **kwargs: object) -> ReviewDialogueResponse:
        self.calls.append(kwargs)
        teacher_messages = kwargs["teacher_messages"]
        assert isinstance(teacher_messages, list)
        return ReviewDialogueResponse(
            clarification_needed=False,
            assistant_message="已根据你的概念顺序目标形成契约草案，请核对。",
            analysis_contract=AnalysisContract(
                goal="复盘概念讲解顺序",
                focus_areas=["概念铺垫与讲解顺序"],
            ),
            model_name="integration-test-model",
            trace_id=str(kwargs["trace_id"]),
        )


def api_settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        jwt_secret="api-test-jwt-secret-at-least-thirty-two-characters",
        demo_account_password=None,
        worker_service_token="api-test-worker-token",
        agent_service_token="api-test-agent-token",
        object_storage_endpoint="http://localhost:9000",
        object_storage_bucket="api-test",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
    )


@pytest.mark.asyncio
async def test_login_and_owner_scoped_classroom_flow() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    settings = api_settings(database_url)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_id, second_id = uuid.uuid4(), uuid.uuid4()

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
    storage = DeletionRecordingStorage()
    app.state.object_storage = storage
    clarifier = RecordingReviewClarifier()
    app.state.review_clarifier = clarifier

    try:
        async with factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=first_id,
                        email="first-api@example.invalid",
                        display_name="First API User",
                        password_hash=hash_password("first-password"),
                    ),
                    User(
                        id=second_id,
                        email="second-api@example.invalid",
                        display_name="Second API User",
                        password_hash=hash_password("second-password"),
                    ),
                ]
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            bad_login = await client.post(
                "/api/auth/login",
                json={"email": "first-api@example.invalid", "password": "wrong"},
            )
            assert bad_login.status_code == 401
            assert bad_login.json()["error"]["code"] == "UNAUTHENTICATED"

            disabled_demo = await client.post("/api/auth/demo")
            assert disabled_demo.status_code == 403
            assert disabled_demo.json()["error"]["code"] == "PERMISSION_DENIED"

            async def token(email: str, password: str) -> str:
                response = await client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                )
                assert response.status_code == 200
                return response.json()["access_token"]

            first_token = await token("first-api@example.invalid", "first-password")
            second_token = await token("second-api@example.invalid", "second-password")
            first_headers = {"Authorization": f"Bearer {first_token}"}
            second_headers = {"Authorization": f"Bearer {second_token}"}

            me = await client.get("/api/auth/me", headers=first_headers)
            assert me.status_code == 200
            assert me.json() == {"id": str(first_id), "display_name": "First API User"}

            course = await client.post(
                "/api/courses", json={"name": "AI Course"}, headers=first_headers
            )
            assert course.status_code == 201
            course_id = course.json()["id"]

            classroom = await client.post(
                f"/api/courses/{course_id}/classrooms",
                json={"title": "  Search Lecture  ", "description": "Initial description"},
                headers=first_headers,
            )
            assert classroom.status_code == 201
            assert classroom.json()["title"] == "Search Lecture"
            classroom_id = classroom.json()["id"]

            blank_create = await client.post(
                f"/api/courses/{course_id}/classrooms",
                json={"title": "   "},
                headers=first_headers,
            )
            assert blank_create.status_code == 422
            assert blank_create.json()["error"]["code"] == "SCHEMA_INVALID"

            own = await client.get(f"/api/classrooms/{classroom_id}", headers=first_headers)
            assert own.status_code == 200

            dialogue = await client.post(
                f"/api/classrooms/{classroom_id}/review-dialogue",
                json={"teacher_messages": ["请分析概念讲解顺序是否清楚"]},
                headers=first_headers,
            )
            assert dialogue.status_code == 200
            assert dialogue.json()["analysis_contract"]["focus_areas"] == [
                "概念铺垫与讲解顺序"
            ]
            assert dialogue.json()["analysis_contract"]["confirmed"] is False
            assert dialogue.json()["model_name"] == "integration-test-model"
            assert clarifier.calls[0]["course_name"] == "AI Course"

            foreign_dialogue = await client.post(
                f"/api/classrooms/{classroom_id}/review-dialogue",
                json={"teacher_messages": ["试图读取其他账户的课堂"]},
                headers=second_headers,
            )
            assert foreign_dialogue.status_code == 404
            assert len(clarifier.calls) == 1

            cross_account = await client.get(
                f"/api/classrooms/{classroom_id}", headers=second_headers
            )
            missing = await client.get(f"/api/classrooms/{uuid.uuid4()}", headers=second_headers)
            assert cross_account.status_code == missing.status_code == 404
            assert cross_account.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

            updated = await client.patch(
                f"/api/classrooms/{classroom_id}",
                json={"title": "Updated Search Lecture"},
                headers=first_headers,
            )
            assert updated.status_code == 200
            assert updated.json()["title"] == "Updated Search Lecture"

            blank_title = await client.patch(
                f"/api/classrooms/{classroom_id}",
                json={"title": "   "},
                headers=first_headers,
            )
            assert blank_title.status_code == 422
            assert blank_title.json()["error"]["code"] == "SCHEMA_INVALID"

            null_title = await client.patch(
                f"/api/classrooms/{classroom_id}",
                json={"title": None, "description": "must not be written"},
                headers=first_headers,
            )
            assert null_title.status_code == 422
            assert null_title.json()["error"]["code"] == "SCHEMA_INVALID"

            after_invalid_patch = await client.get(
                f"/api/classrooms/{classroom_id}", headers=first_headers
            )
            assert after_invalid_patch.status_code == 200
            assert after_invalid_patch.json()["title"] == "Updated Search Lecture"
            assert after_invalid_patch.json()["description"] == "Initial description"

            cleared_description = await client.patch(
                f"/api/classrooms/{classroom_id}",
                json={"description": None},
                headers=first_headers,
            )
            assert cleared_description.status_code == 200
            assert cleared_description.json()["description"] is None

            unchanged = await client.get(
                f"/api/classrooms/{classroom_id}", headers=first_headers
            )
            assert unchanged.status_code == 200
            assert unchanged.json()["title"] == "Updated Search Lecture"
            assert unchanged.json()["description"] is None

            cross_account_delete = await client.delete(
                f"/api/classrooms/{classroom_id}", headers=second_headers
            )
            assert cross_account_delete.status_code == 404
            assert cross_account_delete.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

            deleted = await client.delete(
                f"/api/classrooms/{classroom_id}", headers=first_headers
            )
            assert deleted.status_code == 204
            assert storage.deleted_prefixes == [
                f"owners/{first_id}/classrooms/{classroom_id}/"
            ]

            no_longer_exists = await client.get(
                f"/api/classrooms/{classroom_id}", headers=first_headers
            )
            assert no_longer_exists.status_code == 404

        async with factory() as session:
            events = list(
                await session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.owner_id == first_id)
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            )
            assert Counter(event.action for event in events) == Counter(
                {
                    "course.created": 1,
                    "classroom.created": 1,
                    "review_dialogue.generated": 1,
                    "classroom.updated": 2,
                    "classroom.deleted": 1,
                }
            )
            assert [event.details for event in events if event.action == "classroom.updated"] == [
                {"updated_fields": ["title"]},
                {"updated_fields": ["description"]},
            ]
            serialized = repr([event.details for event in events])
            assert "请分析概念讲解顺序是否清楚" not in serialized
            assert "Updated Search Lecture" not in serialized
            assert "Initial description" not in serialized
            deleted_events = [event for event in events if event.action == "classroom.deleted"]
            assert [event.details for event in deleted_events] == [{"deleted_object_count": 3}]
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(AuditEvent).where(AuditEvent.owner_id.in_([first_id, second_id]))
            )
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

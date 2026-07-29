"""Real HTTP and PostgreSQL tests for authentication and classroom ownership."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.dependencies import get_db
from backend.app.main import create_app
from backend.app.models import User
from backend.app.services.authentication import hash_password


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
async def test_login_and_owner_scoped_classroom_crud() -> None:
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
                json={"title": "Search Lecture"},
                headers=first_headers,
            )
            assert classroom.status_code == 201
            classroom_id = classroom.json()["id"]

            own = await client.get(f"/api/classrooms/{classroom_id}", headers=first_headers)
            assert own.status_code == 200

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

            deleted = await client.delete(f"/api/classrooms/{classroom_id}", headers=first_headers)
            assert deleted.status_code == 204
            after_delete = await client.get(
                f"/api/classrooms/{classroom_id}", headers=first_headers
            )
            assert after_delete.status_code == 404
    finally:
        async with factory.begin() as session:
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

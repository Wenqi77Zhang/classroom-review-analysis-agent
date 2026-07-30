"""Real PostgreSQL coverage for the shortest classroom-upload-task-result chain."""

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
from backend.app.services.storage import ObjectMetadata


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, ObjectMetadata] = {}
        self.deleted: list[str] = []

    async def presign_upload(self, object_key: str, content_type: str) -> str:
        return f"https://storage.invalid/upload/{object_key}"

    async def presign_download(self, object_key: str) -> str:
        return f"https://storage.invalid/download/{object_key}"

    async def head(self, object_key: str) -> ObjectMetadata | None:
        return self.objects.get(object_key)

    async def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


def api_settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=database_url,
        jwt_secret="processing-test-jwt-secret-at-least-thirty-two-characters",
        demo_account_password=None,
        worker_service_token="processing-test-worker-token",
        agent_service_token="processing-test-agent-token",
        object_storage_endpoint="http://localhost:9000",
        object_storage_bucket="processing-test",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
    )


@pytest.mark.asyncio
async def test_shortest_processing_chain_and_retry() -> None:
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
    storage = FakeObjectStorage()
    app.state.object_storage = storage

    try:
        async with factory.begin() as session:
            session.add_all(
                [
                    User(
                        id=first_id,
                        email="first-processing@example.invalid",
                        display_name="First Processing User",
                        password_hash=hash_password("first-password"),
                    ),
                    User(
                        id=second_id,
                        email="second-processing@example.invalid",
                        display_name="Second Processing User",
                        password_hash=hash_password("second-password"),
                    ),
                ]
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async def token(email: str, password: str) -> str:
                response = await client.post(
                    "/api/auth/login",
                    json={"email": email, "password": password},
                )
                assert response.status_code == 200
                return response.json()["access_token"]

            first_headers = {
                "Authorization": f"Bearer {await token('first-processing@example.invalid', 'first-password')}"
            }
            second_headers = {
                "Authorization": f"Bearer {await token('second-processing@example.invalid', 'second-password')}"
            }
            worker_headers = {"Authorization": "Bearer processing-test-worker-token"}
            agent_headers = {"Authorization": "Bearer processing-test-agent-token"}

            course = await client.post(
                "/api/courses",
                json={"name": "Processing Course"},
                headers=first_headers,
            )
            analysis_contract = {
                "goal": "Review the lesson",
                "scope": "full_lesson",
                "focus_areas": ["content structure"],
                "judgment_criteria": [],
                "evidence_requirements": ["timestamped transcript"],
                "bilingual_required": False,
                "privacy_mode": "local",
                "course_domain": "general",
                "confirmed": True,
            }
            classroom = await client.post(
                f"/api/courses/{course.json()['id']}/classrooms",
                json={
                    "title": "Processing Classroom",
                    "analysis_contract": analysis_contract,
                },
                headers=first_headers,
            )
            classroom_id = classroom.json()["id"]

            bad_presign = await client.post(
                f"/api/classrooms/{classroom_id}/uploads/presign",
                json={
                    "kind": "transcript",
                    "filename": "too-large.txt",
                    "content_type": "text/plain",
                    "size_bytes": 33 * 1024 * 1024,
                },
                headers=first_headers,
            )
            assert bad_presign.status_code == 413

            missing_upload = await client.post(
                f"/api/classrooms/{classroom_id}/uploads/presign",
                json={
                    "kind": "video",
                    "filename": "../lesson.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 12,
                },
                headers=first_headers,
            )
            missing_asset_id = missing_upload.json()["asset_id"]
            failed_complete = await client.post(
                f"/api/assets/{missing_asset_id}/complete",
                json={},
                headers=first_headers,
            )
            assert failed_complete.status_code == 400
            assert failed_complete.json()["error"]["code"] == "VALIDATION_ERROR"

            upload = await client.post(
                f"/api/classrooms/{classroom_id}/uploads/presign",
                json={
                    "kind": "video",
                    "filename": "lesson.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 12,
                },
                headers=first_headers,
            )
            assert upload.status_code == 201
            asset_id = upload.json()["asset_id"]
            object_key = upload.json()["object_key"]
            assert upload.json()["headers"] == {"Content-Type": "video/mp4"}
            storage.objects[object_key] = ObjectMetadata(
                size_bytes=12,
                content_type="video/mp4",
                etag="verified-etag",
            )

            complete = await client.post(
                f"/api/assets/{asset_id}/complete",
                json={"etag": '"verified-etag"'},
                headers=first_headers,
            )
            assert complete.status_code == 200
            assert complete.json()["upload_status"] == "uploaded"

            cross_account = await client.get(
                f"/api/assets/{asset_id}/download-url",
                headers=second_headers,
            )
            assert cross_account.status_code == 404
            download = await client.get(
                f"/api/assets/{asset_id}/download-url",
                headers=first_headers,
            )
            assert download.status_code == 200
            assert download.json()["url"].startswith("https://storage.invalid/download/")

            task_response = await client.post(
                f"/api/classrooms/{classroom_id}/tasks",
                json={
                    "asset_ids": [asset_id],
                    "analysis_contract": analysis_contract,
                },
                headers=first_headers,
            )
            assert task_response.status_code == 201
            assert task_response.json()["status"] == "queued"
            task_id = task_response.json()["id"]

            forbidden_claim = await client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-1", "stages": ["uploaded", "analyze"]},
                headers=worker_headers,
            )
            assert forbidden_claim.status_code == 403

            claimed = await client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-1", "stages": ["uploaded"]},
                headers=worker_headers,
            )
            assert claimed.status_code == 200
            assert claimed.json()["task_id"] == task_id
            assert claimed.json()["assets"][0]["id"] == asset_id
            assert claimed.json()["assets"][0]["download_url"].startswith(
                "https://storage.invalid/download/"
            )
            assert claimed.json()["assets"][0]["verified_etag"] == "verified-etag"

            wrong_heartbeat = await client.post(
                f"/api/internal/tasks/{task_id}/heartbeat",
                json={"worker_id": "worker-2"},
                headers=worker_headers,
            )
            assert wrong_heartbeat.status_code == 409
            heartbeat = await client.post(
                f"/api/internal/tasks/{task_id}/heartbeat",
                json={"worker_id": "worker-1"},
                headers=worker_headers,
            )
            assert heartbeat.status_code == 200

            transcribing = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "transcribe", "status": "running", "progress": 0.5},
                headers=worker_headers,
            )
            assert transcribing.status_code == 200

            invalid_transcript = await client.post(
                f"/api/internal/tasks/{task_id}/transcript",
                json={
                    "source_language": "zh",
                    "duration_ms": 1000,
                    "segments": [
                        {
                            "index": 0,
                            "start_ms": 100,
                            "end_ms": 1900,
                            "text": "超出媒体时长。",
                        }
                    ],
                },
                headers=worker_headers,
            )
            assert invalid_transcript.status_code == 400

            transcript = await client.post(
                f"/api/internal/tasks/{task_id}/transcript",
                json={
                    "source_language": "zh",
                    "duration_ms": 2000,
                    "segments": [
                        {
                            "index": 0,
                            "start_ms": 100,
                            "end_ms": 1900,
                            "speaker": "教师",
                            "text": "请说明检索的第一步。",
                        }
                    ],
                },
                headers=worker_headers,
            )
            assert transcript.status_code == 201
            segment_id = transcript.json()["segments"][0]["id"]

            transcribed = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "transcribe", "status": "running", "progress": 1.0},
                headers=worker_headers,
            )
            assert transcribed.status_code == 200

            forbidden_agent_stage = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "transcribe", "status": "running", "progress": 0.6},
                headers=agent_headers,
            )
            assert forbidden_agent_stage.status_code == 403

            forbidden_handoff = await client.post(
                f"/api/internal/tasks/{task_id}/handoff-agent",
                json={"worker_id": "worker-2"},
                headers=worker_headers,
            )
            assert forbidden_handoff.status_code == 409

            handed_off = await client.post(
                f"/api/internal/tasks/{task_id}/handoff-agent",
                json={"worker_id": "worker-1"},
                headers=worker_headers,
            )
            assert handed_off.status_code == 200
            assert handed_off.json()["stage"] == "analyze"
            assert handed_off.json()["status"] == "queued"
            assert handed_off.json()["progress"] == 0

            forbidden_agent_claim = await client.post(
                "/api/internal/agent/tasks/claim",
                json={"agent_id": "agent-1"},
                headers=worker_headers,
            )
            assert forbidden_agent_claim.status_code == 403

            agent_claim = await client.post(
                "/api/internal/agent/tasks/claim",
                json={"agent_id": "agent-1"},
                headers=agent_headers,
            )
            assert agent_claim.status_code == 200
            assert agent_claim.json()["task_id"] == task_id
            assert agent_claim.json()["analysis_contract"]["confirmed"] is True
            assert agent_claim.json()["evidence"][0]["id"] == segment_id
            assert agent_claim.json()["evidence"][0]["reference"]["segment_id"] == segment_id
            assert agent_claim.json()["evidence"][0]["text"] == "请说明检索的第一步。"

            wrong_agent_heartbeat = await client.post(
                f"/api/internal/agent/tasks/{task_id}/heartbeat",
                json={"agent_id": "agent-2"},
                headers=agent_headers,
            )
            assert wrong_agent_heartbeat.status_code == 409
            agent_heartbeat = await client.post(
                f"/api/internal/agent/tasks/{task_id}/heartbeat",
                json={"agent_id": "agent-1"},
                headers=agent_headers,
            )
            assert agent_heartbeat.status_code == 200

            analyzing = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "analyze", "status": "running", "progress": 0.2},
                headers=agent_headers,
            )
            assert analyzing.status_code == 200

            heartbeat_during_analysis = await client.post(
                f"/api/internal/agent/tasks/{task_id}/heartbeat",
                json={"agent_id": "agent-1"},
                headers=agent_headers,
            )
            assert heartbeat_during_analysis.status_code == 200

            ungrounded = await client.post(
                f"/api/internal/tasks/{task_id}/conclusions",
                json={
                    "conclusions": [
                        {
                            "type": "fact",
                            "content": "未绑定任务内逐字稿的结论。",
                            "trace_id": "processing-test-trace",
                            "evidence_refs": [
                                {
                                    "source_type": "transcript",
                                    "start_ms": 100,
                                    "end_ms": 1900,
                                    "quote": "缺少 segment_id",
                                }
                            ],
                        }
                    ]
                },
                headers=agent_headers,
            )
            assert ungrounded.status_code == 400

            conclusions = await client.post(
                f"/api/internal/tasks/{task_id}/conclusions",
                json={
                    "conclusions": [
                        {
                            "type": "fact",
                            "content": "教师提出了检索步骤问题。",
                            "trace_id": "processing-test-trace",
                            "model_name": "test-model",
                            "skill": "interaction-analysis",
                            "prompt_version": "v1",
                            "evidence_refs": [
                                {
                                    "source_type": "transcript",
                                    "segment_id": segment_id,
                                    "start_ms": 100,
                                    "end_ms": 1900,
                                    "quote": "请说明检索的第一步。",
                                }
                            ],
                        }
                    ]
                },
                headers=agent_headers,
            )
            assert conclusions.status_code == 201
            assert conclusions.json()[0]["review_status"] == "pending"
            conclusion_id = conclusions.json()[0]["id"]

            foreign_review = await client.post(
                f"/api/conclusions/{conclusion_id}/review",
                json={"action": "accept"},
                headers=second_headers,
            )
            assert foreign_review.status_code == 404
            accepted = await client.post(
                f"/api/conclusions/{conclusion_id}/review",
                json={"action": "accept", "note": "确认事实"},
                headers=first_headers,
            )
            assert accepted.status_code == 200
            assert accepted.json()["review_status"] == "accepted"
            history = await client.get(
                f"/api/conclusions/{conclusion_id}/history",
                headers=first_headers,
            )
            assert [item["action"] for item in history.json()] == ["accept"]

            report = await client.put(
                f"/api/classrooms/{classroom_id}/report",
                json={"title": "Processing Report"},
                headers=first_headers,
            )
            assert report.status_code == 200
            assert report.json()["included_conclusion_ids"] == [conclusion_id]
            assert "教师提出了检索步骤问题" in report.json()["content"]

            modified = await client.post(
                f"/api/conclusions/{conclusion_id}/review",
                json={"action": "modify", "edited_content": "教师确认后的改写事实。"},
                headers=first_headers,
            )
            assert modified.status_code == 200
            assert modified.json()["review_status"] == "modified"
            refreshed_report = await client.get(
                f"/api/classrooms/{classroom_id}/report",
                headers=first_headers,
            )
            assert "教师确认后的改写事实" in refreshed_report.json()["content"]
            assert "教师提出了检索步骤问题" not in refreshed_report.json()["content"]

            rejected = await client.post(
                f"/api/conclusions/{conclusion_id}/review",
                json={"action": "reject"},
                headers=first_headers,
            )
            assert rejected.status_code == 200
            rejected_report = await client.get(
                f"/api/classrooms/{classroom_id}/report",
                headers=first_headers,
            )
            assert rejected_report.json()["included_conclusion_ids"] == []
            assert "教师确认后的改写事实" not in rejected_report.json()["content"]
            final_history = await client.get(
                f"/api/conclusions/{conclusion_id}/history",
                headers=first_headers,
            )
            assert [item["action"] for item in final_history.json()] == [
                "accept",
                "modify",
                "reject",
            ]

            succeeded = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "analyze", "status": "succeeded", "progress": 1.0},
                headers=agent_headers,
            )
            assert succeeded.status_code == 200
            assert succeeded.json()["status"] == "succeeded"

            teacher_transcript = await client.get(
                f"/api/tasks/{task_id}/transcript",
                headers=first_headers,
            )
            teacher_conclusions = await client.get(
                f"/api/classrooms/{classroom_id}/conclusions",
                headers=first_headers,
            )
            events = await client.get(
                f"/api/tasks/{task_id}/events",
                headers=first_headers,
            )
            assert teacher_transcript.json()["segment_count"] == 1
            assert teacher_conclusions.json()[0]["evidence_refs"][0]["segment_id"] == segment_id
            assert events.json()[-1]["status"] == "succeeded"

            retry_task = await client.post(
                f"/api/classrooms/{classroom_id}/tasks",
                json={
                    "asset_ids": [asset_id],
                    "analysis_contract": analysis_contract,
                },
                headers=first_headers,
            )
            retry_task_id = retry_task.json()["id"]
            await client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-1", "stages": ["uploaded"]},
                headers=worker_headers,
            )
            failed = await client.patch(
                f"/api/internal/tasks/{retry_task_id}/state",
                json={
                    "stage": "uploaded",
                    "status": "failed",
                    "progress": 0,
                    "error_code": "UPSTREAM_UNAVAILABLE",
                    "message": "temporary failure",
                },
                headers=worker_headers,
            )
            assert failed.status_code == 200
            retried = await client.post(
                f"/api/tasks/{retry_task_id}/retry",
                headers=first_headers,
            )
            assert retried.status_code == 200
            assert retried.json()["status"] == "queued"
            assert retried.json()["retry_count"] == 1
    finally:
        async with factory.begin() as session:
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

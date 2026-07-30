"""Real PostgreSQL coverage for the shortest classroom-upload-task-result chain."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.config import Settings
from backend.app.dependencies import get_db
from backend.app.main import create_app
from backend.app.models import AuditEvent, ProcessingTask, User
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
            classroom = await client.post(
                f"/api/courses/{course.json()['id']}/classrooms",
                json={
                    "title": "Processing Classroom",
                    "analysis_contract": {"goal": "Review the lesson"},
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
                json={"asset_ids": [asset_id]},
                headers=first_headers,
            )
            assert task_response.status_code == 201
            assert task_response.json()["status"] == "queued"
            task_id = task_response.json()["id"]
            task_trace_id = task_response.json()["trace_id"]

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
            repeated_transcript = await client.post(
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
            assert repeated_transcript.status_code == 201
            segment_id = repeated_transcript.json()["segments"][0]["id"]

            forbidden_agent_stage = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "transcribe", "status": "running", "progress": 0.6},
                headers=agent_headers,
            )
            assert forbidden_agent_stage.status_code == 403

            analyzing = await client.patch(
                f"/api/internal/tasks/{task_id}/state",
                json={"stage": "analyze", "status": "running", "progress": 0.2},
                headers=agent_headers,
            )
            assert analyzing.status_code == 200

            trace_event_id = str(uuid.uuid4())
            trace_payload = {
                "event_id": trace_event_id,
                "trace_id": task_trace_id,
                "name": "agent.started",
                "stage": "analyze",
                "model_name": "test-model",
                "skill": "interaction-analysis",
                "prompt_version": "v1",
            }
            forbidden_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json=trace_payload,
                headers=worker_headers,
            )
            assert forbidden_trace.status_code == 403
            teacher_cannot_write_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json=trace_payload,
                headers=first_headers,
            )
            assert teacher_cannot_write_trace.status_code == 401
            wrong_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json={**trace_payload, "trace_id": "wrong-trace"},
                headers=agent_headers,
            )
            assert wrong_trace.status_code == 409
            trace_event = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json=trace_payload,
                headers=agent_headers,
            )
            assert trace_event.status_code == 201
            duplicate_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json=trace_payload,
                headers=agent_headers,
            )
            assert duplicate_trace.status_code == 201
            assert duplicate_trace.json()["id"] == trace_event_id
            conflicting_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json={**trace_payload, "name": "agent.completed"},
                headers=agent_headers,
            )
            assert conflicting_trace.status_code == 409
            unsafe_trace = await client.post(
                f"/api/internal/tasks/{task_id}/trace-events",
                json={**trace_payload, "event_id": str(uuid.uuid4()), "prompt": "private"},
                headers=agent_headers,
            )
            assert unsafe_trace.status_code == 422

            audit_events = await client.get(
                f"/api/tasks/{task_id}/audit-events",
                headers=first_headers,
            )
            assert audit_events.status_code == 200
            assert [event["id"] for event in audit_events.json()] == [trace_event_id]
            assert audit_events.json()[0]["details"] == {
                "stage": "analyze",
                "model_name": "test-model",
                "skill": "interaction-analysis",
                "prompt_version": "v1",
            }
            cross_account_audit = await client.get(
                f"/api/tasks/{task_id}/audit-events",
                headers=second_headers,
            )
            assert cross_account_audit.status_code == 404
            service_cannot_read_audit = await client.get(
                f"/api/tasks/{task_id}/audit-events",
                headers=agent_headers,
            )
            assert service_cannot_read_audit.status_code == 401

            wrong_conclusion_trace = await client.post(
                f"/api/internal/tasks/{task_id}/conclusions",
                json={
                    "conclusions": [
                        {
                            "type": "fact",
                            "content": "Trace 不一致。",
                            "trace_id": "wrong-trace",
                            "evidence_refs": [
                                {
                                    "source_type": "transcript",
                                    "segment_id": segment_id,
                                    "start_ms": 100,
                                    "end_ms": 1900,
                                }
                            ],
                        }
                    ]
                },
                headers=agent_headers,
            )
            assert wrong_conclusion_trace.status_code == 400

            ungrounded = await client.post(
                f"/api/internal/tasks/{task_id}/conclusions",
                json={
                    "conclusions": [
                        {
                            "type": "fact",
                            "content": "未绑定任务内逐字稿的结论。",
                            "trace_id": task_trace_id,
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
                            "trace_id": task_trace_id,
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
            repeated_conclusions = await client.post(
                f"/api/internal/tasks/{task_id}/conclusions",
                json={
                    "conclusions": [
                        {
                            "type": "fact",
                            "content": "教师提出了检索步骤问题。",
                            "trace_id": task_trace_id,
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
            assert repeated_conclusions.status_code == 201
            assert len(repeated_conclusions.json()) == 1

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
                json={"asset_ids": [asset_id]},
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

            pre_restart_claim = await client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-before-restart", "stages": ["uploaded"]},
                headers=worker_headers,
            )
            assert pre_restart_claim.json()["task_id"] == retry_task_id

        async with factory.begin() as session:
            persisted_task = await session.get(ProcessingTask, uuid.UUID(retry_task_id))
            assert persisted_task is not None
            persisted_task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        restarted_app = create_app(settings)
        restarted_app.dependency_overrides[get_db] = test_db
        restarted_app.state.object_storage = storage
        restarted_transport = httpx.ASGITransport(app=restarted_app)
        async with httpx.AsyncClient(
            transport=restarted_transport, base_url="http://restarted"
        ) as restarted_client:
            reclaimed = await restarted_client.post(
                "/api/internal/tasks/claim",
                json={"worker_id": "worker-after-restart", "stages": ["uploaded"]},
                headers=worker_headers,
            )
            assert reclaimed.status_code == 200
            assert reclaimed.json()["task_id"] == retry_task_id
            recovered_events = await restarted_client.get(
                f"/api/tasks/{retry_task_id}/events",
                headers=first_headers,
            )
            assert recovered_events.status_code == 200
            assert recovered_events.json()[-1]["message"] == "租约到期后重新领取。"
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(AuditEvent).where(
                    AuditEvent.owner_id.in_([first_id, second_id])
                )
            )
            for user_id in (first_id, second_id):
                user = await session.get(User, user_id)
                if user is not None:
                    await session.delete(user)
        await engine.dispose()

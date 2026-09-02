from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from backend.app.config import AppEnv
from backend.app.errors import UpstreamUnavailableError
from backend.app.services.storage import S3ObjectStorage
from scripts.production_preflight import _optional, _require


def make_settings(**overrides: object):
    from backend.app.config import Settings

    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://classroom_review:pw@localhost:5432/classroom_review",
        "jwt_secret": "t" * 32,
        "worker_service_token": "worker-service-token",
        "agent_service_token": "agent-service-token",
        "object_storage_endpoint": "http://localhost:9000",
        "object_storage_bucket": "classroom-review",
        "object_storage_access_key_id": "testkey",
        "object_storage_secret_access_key": "testsecret",
        "frontend_origin": "http://localhost:3000",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_production_rejects_non_https_frontend() -> None:
    with pytest.raises(ValidationError, match="FRONTEND_ORIGIN"):
        make_settings(
            app_env=AppEnv.PRODUCTION,
            frontend_origin="http://classroom.example",
            object_storage_endpoint="https://s3.example",
        )


def test_production_rejects_non_https_storage() -> None:
    with pytest.raises(ValidationError, match="对象存储端点"):
        make_settings(
            app_env=AppEnv.PRODUCTION,
            frontend_origin="https://classroom.example",
            object_storage_endpoint="http://s3.example",
        )


def test_production_rejects_weak_demo_password() -> None:
    with pytest.raises(ValidationError, match="至少 16"):
        make_settings(
            app_env=AppEnv.PRODUCTION,
            frontend_origin="https://classroom.example",
            object_storage_endpoint="https://s3.example",
            demo_account_password="too-short",
        )


def test_production_accepts_https_and_strong_secrets() -> None:
    settings = make_settings(
        app_env=AppEnv.PRODUCTION,
        frontend_origin="https://classroom.example",
        object_storage_endpoint="https://s3.example",
        demo_account_password="strong-demo-password",
    )
    assert settings.is_production


def test_production_preflight_rejects_example_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "replace-with-at-least-32-random-characters")
    with pytest.raises(ValueError, match="示例占位值：JWT_SECRET"):
        _require("JWT_SECRET", minimum=32)


def test_production_preflight_accepts_real_non_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    assert _require("JWT_SECRET", minimum=32) == "x" * 40


def test_demo_and_extra_entrance_gate_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_ACCOUNT_PASSWORD", raising=False)
    monkeypatch.delenv("TEAM_TUNNEL_ACCESS_CODE", raising=False)
    assert _optional("DEMO_ACCOUNT_PASSWORD", minimum=16) is None
    assert _optional("TEAM_TUNNEL_ACCESS_CODE", minimum=16) is None


@pytest.mark.asyncio
async def test_storage_readiness_accepts_existing_sentinel() -> None:
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    storage._bucket = "restricted-bucket"
    storage._client = type("Client", (), {})()

    storage._client.head_object = lambda **_: {"ContentLength": 2}
    await storage.ready()


@pytest.mark.asyncio
async def test_storage_readiness_rejects_forbidden_probe() -> None:
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    storage._bucket = "restricted-bucket"
    storage._client = type("Client", (), {})()

    def forbidden(**_: object) -> None:
        raise ClientError(
            {
                "Error": {"Code": "403", "Message": "Forbidden"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            "HeadObject",
        )

    storage._client.head_object = forbidden
    with pytest.raises(UpstreamUnavailableError):
        await storage.ready()


@pytest.mark.asyncio
async def test_storage_deletes_every_page_below_exact_classroom_prefix() -> None:
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    storage._bucket = "restricted-bucket"
    calls: list[dict[str, object]] = []

    class Client:
        def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            if "ContinuationToken" not in kwargs:
                return {
                    "Contents": [{"Key": "owners/11111111-1111-1111-1111-111111111111/classrooms/22222222-2222-2222-2222-222222222222/video.mp4"}],
                    "IsTruncated": True,
                    "NextContinuationToken": "next-page",
                }
            return {
                "Contents": [{"Key": "owners/11111111-1111-1111-1111-111111111111/classrooms/22222222-2222-2222-2222-222222222222/report.pdf"}],
                "IsTruncated": False,
            }

        def delete_objects(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {}

    storage._client = Client()
    prefix = "owners/11111111-1111-1111-1111-111111111111/classrooms/22222222-2222-2222-2222-222222222222/"
    deleted = await storage.delete_prefix(prefix)

    assert deleted == 2
    assert calls[0] == {"Bucket": "restricted-bucket", "Prefix": prefix}
    assert calls[2]["ContinuationToken"] == "next-page"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prefix",
    [
        "owners/u/",
        "owners/u/classrooms/c/",
        "owners/11111111-1111-1111-1111-111111111111/classrooms/",
        "owners/11111111-1111-1111-1111-111111111111/classrooms/22222222-2222-2222-2222-222222222222/extra/",
    ],
)
async def test_storage_rejects_broad_or_malformed_delete_prefix(prefix: str) -> None:
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    with pytest.raises(ValueError, match="单个课堂"):
        await storage.delete_prefix(prefix)

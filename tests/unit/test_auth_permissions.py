"""Authentication and internal service permission tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.dependencies import identify_service
from backend.app.errors import UnauthenticatedError
from backend.app.schemas.identity import ClassroomCreate, ClassroomUpdate, CourseCreate
from backend.app.schemas.task import ServiceIdentity
from backend.app.services.authentication import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def make_settings(*, jwt_secret: str | None = None) -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        jwt_secret=jwt_secret or "jwt-secret-that-is-at-least-thirty-two-characters",
        worker_service_token="worker-token-that-is-long-and-distinct",
        agent_service_token="agent-token-that-is-long-and-distinct",
        object_storage_endpoint="http://localhost:9000",
        object_storage_bucket="test",
        object_storage_access_key_id="access",
        object_storage_secret_access_key="secret",
    )


def test_password_hash_does_not_contain_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip() -> None:
    settings = make_settings()
    user_id = uuid.uuid4()
    token = create_access_token(user_id, settings)
    assert decode_access_token(token, settings) == user_id


def test_expired_access_token_is_rejected() -> None:
    settings = make_settings()
    old = datetime.now(UTC) - timedelta(days=2)
    token = create_access_token(uuid.uuid4(), settings, now=old)
    with pytest.raises(UnauthenticatedError):
        decode_access_token(token, settings)


def test_token_signed_with_other_secret_is_rejected() -> None:
    settings = make_settings()
    other = make_settings(jwt_secret="different-secret-that-is-at-least-thirty-two-characters")
    token = create_access_token(uuid.uuid4(), other)
    with pytest.raises(UnauthenticatedError):
        decode_access_token(token, settings)


def test_service_tokens_identify_distinct_identities() -> None:
    settings = make_settings()
    assert (
        identify_service(settings.worker_service_token.get_secret_value(), settings)
        is ServiceIdentity.WORKER
    )
    assert (
        identify_service(settings.agent_service_token.get_secret_value(), settings)
        is ServiceIdentity.AGENT
    )


def test_unknown_service_token_is_rejected() -> None:
    with pytest.raises(UnauthenticatedError):
        identify_service("unknown", make_settings())


def test_empty_classroom_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassroomUpdate()


@pytest.mark.parametrize("schema, field", [(CourseCreate, "name"), (ClassroomCreate, "title")])
def test_required_names_are_trimmed_and_reject_whitespace(schema: type, field: str) -> None:
    assert getattr(schema(**{field: "  valid  "}), field) == "valid"
    with pytest.raises(ValidationError):
        schema(**{field: "   "})


def test_classroom_patch_distinguishes_clearable_and_required_fields() -> None:
    assert ClassroomUpdate(description=None).model_dump(exclude_unset=True) == {"description": None}
    with pytest.raises(ValidationError):
        ClassroomUpdate(title=None, description="must not be written")
    with pytest.raises(ValidationError):
        ClassroomUpdate(analysis_contract=None)

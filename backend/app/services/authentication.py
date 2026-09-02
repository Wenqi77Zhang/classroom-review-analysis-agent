"""Password hashing and JWT validation without HTTP-layer dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from backend.app.config import Settings
from backend.app.errors import UnauthenticatedError

JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "classroom-review-web"
JWT_ISSUER = "classroom-review-backend"

_password_hasher = PasswordHasher()


@dataclass(frozen=True)
class TokenIdentity:
    user_id: UUID
    auth_version: int


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空。")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    user_id: UUID,
    settings: Settings,
    *,
    auth_version: int = 1,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "av": auth_version,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> UUID:
    return decode_access_token_identity(token, settings).user_id


def decode_access_token_identity(token: str, settings: Settings) -> TokenIdentity:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss", "aud", "av"]},
        )
        auth_version = int(payload["av"])
        if auth_version < 1:
            raise ValueError("invalid auth version")
        return TokenIdentity(user_id=UUID(payload["sub"]), auth_version=auth_version)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise UnauthenticatedError("登录已失效，请重新登录。") from exc

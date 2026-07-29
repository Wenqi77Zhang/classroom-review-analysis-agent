"""Password hashing and JWT validation without HTTP-layer dependencies."""

from __future__ import annotations

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


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("密码不能为空。")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: UUID, settings: Settings, *, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss", "aud"]},
        )
        return UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise UnauthenticatedError("登录已失效，请重新登录。") from exc

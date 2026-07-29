"""Request-scoped database, user, and internal service authentication dependencies."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.auth import decode_access_token
from backend.app.config import Settings, get_settings
from backend.app.database import session_scope
from backend.app.errors import PermissionDeniedError, UnauthenticatedError
from backend.app.models import User
from backend.app.schemas.task import INTERNAL_ENDPOINT_SCOPES, ServiceIdentity

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in session_scope():
        yield session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthenticatedError()
    user_id = decode_access_token(credentials.credentials, settings)
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError("账号不存在或已停用。")
    return user


def identify_service(token: str, settings: Settings) -> ServiceIdentity:
    candidates = (
        (ServiceIdentity.WORKER, settings.worker_service_token.get_secret_value()),
        (ServiceIdentity.AGENT, settings.agent_service_token.get_secret_value()),
    )
    for identity, expected in candidates:
        if hmac.compare_digest(token.encode(), expected.encode()):
            return identity
    raise UnauthenticatedError("服务身份令牌无效。")


def require_service_identity(scope: str) -> Callable[..., ServiceIdentity]:
    if scope not in INTERNAL_ENDPOINT_SCOPES:
        raise ValueError(f"未知内部接口权限范围: {scope}")

    def dependency(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> ServiceIdentity:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise UnauthenticatedError("缺少服务身份令牌。")
        identity = identify_service(credentials.credentials, settings)
        if identity not in INTERNAL_ENDPOINT_SCOPES[scope]:
            raise PermissionDeniedError("该服务身份无权调用此内部接口。")
        request.state.service_identity = identity
        return identity

    return dependency

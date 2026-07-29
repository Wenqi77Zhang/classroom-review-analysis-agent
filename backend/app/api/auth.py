"""Password and JWT primitives used by the authentication routes.

The request/response route schemas remain intentionally deferred until the team confirms the
login form contract. Security primitives do not depend on that UI decision.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.dependencies import get_app_settings, get_current_user, get_db
from backend.app.errors import PermissionDeniedError, UnauthenticatedError
from backend.app.models import User
from backend.app.repositories.identity import find_user_by_email
from backend.app.schemas.common import UserRef
from backend.app.schemas.identity import AccessTokenResponse, LoginRequest
from backend.app.services.authentication import (
    create_access_token,
    hash_password,
    verify_password,
)

_DUMMY_PASSWORD_HASH = hash_password("timing-only-password-that-is-never-valid")
DEMO_ACCOUNT_EMAIL = "demo@classroom-review.local"

router = APIRouter(tags=["auth"])


def _token_response(user: User, settings: Settings) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in_seconds=settings.access_token_expire_minutes * 60,
        user=UserRef.model_validate(user),
    )


@router.post("/auth/login", response_model=AccessTokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AccessTokenResponse:
    user = await find_user_by_email(session, body.email)
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    valid = verify_password(body.password, password_hash)
    if user is None or not user.is_active or not valid:
        raise UnauthenticatedError("邮箱或密码错误。")
    return _token_response(user, settings)


@router.post("/auth/demo", response_model=AccessTokenResponse)
async def demo_login(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AccessTokenResponse:
    if settings.demo_account_password is None:
        raise PermissionDeniedError("当前环境未启用演示账号。")
    user = await find_user_by_email(session, DEMO_ACCOUNT_EMAIL)
    if user is None:
        user = User(
            email=DEMO_ACCOUNT_EMAIL,
            display_name="演示教师",
            password_hash=hash_password(settings.demo_account_password.get_secret_value()),
        )
        session.add(user)
        await session.flush()
    request.state.demo_account = True
    return _token_response(user, settings)


@router.get("/auth/me", response_model=UserRef)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserRef:
    return UserRef.model_validate(user)

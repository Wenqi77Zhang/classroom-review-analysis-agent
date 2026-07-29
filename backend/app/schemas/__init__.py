"""API schema package."""

from backend.app.schemas.identity import (
    AccessTokenResponse,
    ClassroomCreate,
    ClassroomRead,
    ClassroomUpdate,
    CourseCreate,
    CourseRead,
    LoginRequest,
)

__all__ = [
    "AccessTokenResponse",
    "ClassroomCreate",
    "ClassroomRead",
    "ClassroomUpdate",
    "CourseCreate",
    "CourseRead",
    "LoginRequest",
]

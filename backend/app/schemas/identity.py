"""Authentication, course, and classroom API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, StringConstraints, field_validator, model_validator

from backend.app.schemas.common import ApiModel, OrmModel, ResourceId, UserRef

RequiredName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AccessTokenResponse(OrmModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = Field(gt=0)
    user: UserRef


class CourseCreate(ApiModel):
    name: RequiredName
    description: str | None = Field(default=None, max_length=4000)


class CourseRead(OrmModel):
    id: ResourceId
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ClassroomCreate(ApiModel):
    title: RequiredName
    description: str | None = Field(default=None, max_length=4000)
    analysis_contract: dict[str, Any] = Field(default_factory=dict)


class ClassroomUpdate(ApiModel):
    title: RequiredName | None = None
    description: str | None = Field(default=None, max_length=4000)
    analysis_contract: dict[str, Any] | None = None

    @field_validator("title", "analysis_contract", mode="before")
    @classmethod
    def _required_fields_cannot_be_cleared(cls, value: object) -> object:
        if value is None:
            raise ValueError("必填字段不能设为 null。")
        return value

    @model_validator(mode="after")
    def _require_any_field(self) -> ClassroomUpdate:
        if not self.model_fields_set:
            raise ValueError("title、description、analysis_contract 至少提供一个。")
        return self


class ClassroomRead(OrmModel):
    id: ResourceId
    course_id: ResourceId
    title: str
    description: str | None = None
    analysis_contract: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None = None

"""Page-aligned courseware evidence shared by Worker, Agent, and frontend."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from backend.app.schemas.common import ApiModel, OrmModel, ResourceId

NonBlankPageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100_000),
]


class CoursewarePageRead(OrmModel):
    id: ResourceId
    task_id: ResourceId
    asset_id: ResourceId
    page_no: int = Field(ge=1)
    text: str


class InternalCoursewarePageWrite(ApiModel):
    asset_id: ResourceId
    page_no: int = Field(ge=1)
    text: NonBlankPageText


class InternalCoursewareWrite(ApiModel):
    """Replace all extracted courseware pages for one processing task."""

    pages: list[InternalCoursewarePageWrite] = Field(default_factory=list, max_length=1000)
    trace_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")

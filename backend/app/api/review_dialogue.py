"""Authenticated teacher dialogue for drafting an evidence-bound review contract."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agent.clarifier import ReviewClarificationAgent
from agent.providers.base import ModelProviderError
from backend.app.dependencies import get_current_user, get_db
from backend.app.errors import UpstreamUnavailableError, current_trace_id
from backend.app.models import Classroom, Course, User
from backend.app.schemas.review_dialogue import ReviewDialogueRequest, ReviewDialogueResponse
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404

router = APIRouter(tags=["review-dialogue"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_review_clarifier(request: Request) -> ReviewClarificationAgent:
    return request.app.state.review_clarifier


Clarifier = Annotated[ReviewClarificationAgent, Depends(get_review_clarifier)]


@router.post(
    "/classrooms/{classroom_id}/review-dialogue",
    response_model=ReviewDialogueResponse,
)
async def post_review_dialogue(
    classroom_id: UUID,
    body: ReviewDialogueRequest,
    session: Db,
    user: CurrentUser,
    clarifier: Clarifier,
) -> ReviewDialogueResponse:
    classroom = await get_owned_or_404(session, Classroom, classroom_id, user.id)
    course = await get_owned_or_404(session, Course, classroom.course_id, user.id)
    trace_id = current_trace_id.get()
    try:
        response = await clarifier.clarify(
            teacher_messages=body.teacher_messages,
            course_name=course.name,
            classroom_title=classroom.title,
            classroom_description=classroom.description,
            trace_id=trace_id,
        )
    except ModelProviderError as exc:
        raise UpstreamUnavailableError(
            "复盘 Agent 暂时不可用，请确认本地模型已经启动后重试。"
        ) from exc

    # Only operational metadata is auditable here. Teacher messages and generated
    # contract text can contain private teaching information and are never copied to logs.
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="review_dialogue.generated",
        resource_type="classroom",
        resource_id=classroom.id,
        details={
            "turn_count": len(body.teacher_messages),
            "clarification_needed": response.clarification_needed,
            "model_name": response.model_name,
            "prompt_version": response.prompt_version,
        },
    )
    return response

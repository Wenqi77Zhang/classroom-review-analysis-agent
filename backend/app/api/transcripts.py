"""Teacher transcript reads/edits and the Worker transcript write boundary."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import (
    get_current_user,
    get_db,
    require_service_identity,
)
from backend.app.errors import StateConflictError, ValidationFailedError
from backend.app.models import User
from backend.app.repositories.results import (
    edit_transcript_segment,
    get_transcript_segments,
    replace_transcript,
)
from backend.app.repositories.tasks import get_internal_task
from backend.app.schemas.task import ServiceIdentity, TaskStage, TaskStatus
from backend.app.schemas.transcript import (
    InternalTranscriptWrite,
    TranscriptRead,
    TranscriptSegment,
    TranscriptSegmentUpdate,
)

router = APIRouter(tags=["transcripts"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
WorkerWriter = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:transcript")),
]


def _transcript_read(task_id: UUID, segments: list) -> TranscriptRead:
    source_language = segments[0].source_language if segments else "und"
    return TranscriptRead(
        task_id=task_id,
        source_language=source_language,
        has_translation=any(item.translation is not None for item in segments),
        segment_count=len(segments),
        duration_ms=max((item.end_ms for item in segments), default=0),
        segments=[TranscriptSegment.model_validate(item) for item in segments],
    )


@router.get("/tasks/{task_id}/transcript", response_model=TranscriptRead)
async def get_transcript(task_id: UUID, session: Db, user: CurrentUser) -> TranscriptRead:
    return _transcript_read(
        task_id,
        await get_transcript_segments(session, user.id, task_id),
    )


@router.patch("/transcript-segments/{segment_id}", response_model=TranscriptSegment)
async def patch_segment(
    segment_id: UUID,
    body: TranscriptSegmentUpdate,
    session: Db,
    user: CurrentUser,
) -> TranscriptSegment:
    segment = await edit_transcript_segment(
        session,
        owner_id=user.id,
        user_id=user.id,
        segment_id=segment_id,
        body=body,
    )
    return TranscriptSegment.model_validate(segment)


@router.post(
    "/internal/tasks/{task_id}/transcript",
    response_model=TranscriptRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_transcript(
    task_id: UUID,
    body: InternalTranscriptWrite,
    session: Db,
    _identity: WorkerWriter,
) -> TranscriptRead:
    task = await get_internal_task(session, task_id)
    if TaskStatus(task.status) is not TaskStatus.RUNNING:
        raise StateConflictError("只有运行中的任务可以写入逐字稿。")
    if TaskStage(task.stage) not in {TaskStage.TRANSCRIBE, TaskStage.TRANSLATE}:
        raise StateConflictError("当前任务阶段不允许写入逐字稿。")
    if any(segment.end_ms > body.duration_ms for segment in body.segments):
        raise ValidationFailedError(
            "逐字稿时间范围不能超过声明的媒体时长。"
        )
    segments = await replace_transcript(session, task, body)
    return _transcript_read(task.id, segments)

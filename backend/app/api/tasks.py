"""External task APIs and least-privilege Worker/Agent state APIs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import (
    get_current_user,
    get_db,
    require_service_identity,
)
from backend.app.errors import PermissionDeniedError, StateConflictError, current_trace_id
from backend.app.models import ProcessingTask, User
from backend.app.repositories.results import get_courseware_pages, get_transcript_segments
from backend.app.repositories.tasks import (
    append_task_event,
    claim_task,
    create_processing_task,
    get_internal_task,
    get_task_assets,
    handoff_task_to_agent,
    list_task_events,
    list_tasks,
)
from backend.app.schemas.agent_runtime import (
    InternalAgentClaimRequest,
    InternalAgentEvidence,
    InternalAgentHandoff,
    InternalAgentHeartbeat,
    InternalAgentTaskClaim,
)
from backend.app.schemas.analysis_report import EvidenceReference, EvidenceSourceType
from backend.app.schemas.task import (
    AGENT_WRITABLE_STAGES,
    ALLOWED_STATUS_TRANSITIONS,
    WORKER_WRITABLE_STAGES,
    AnalysisContract,
    AssetRead,
    InternalAssetRead,
    InternalTaskClaim,
    InternalTaskClaimRequest,
    InternalTaskHeartbeat,
    InternalTaskStateUpdate,
    ServiceIdentity,
    TaskCreate,
    TaskEventRead,
    TaskRead,
    TaskStage,
    TaskStatus,
)
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404
from backend.app.services.storage import ObjectStorage, get_object_storage

router = APIRouter(tags=["tasks"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Worker = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:claim")),
]
WorkerHeartbeat = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:heartbeat")),
]
WorkerHandoff = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:handoff-agent")),
]
AgentClaim = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("agent:claim")),
]
AgentHeartbeat = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("agent:heartbeat")),
]
StateWriter = Annotated[
    ServiceIdentity,
    Depends(require_service_identity("tasks:state")),
]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]

_STAGE_ORDER = {stage: index for index, stage in enumerate(TaskStage)}


def _task_read(task: ProcessingTask) -> TaskRead:
    return TaskRead.model_validate(task)


async def _claim_contract_or_quarantine(
    session: AsyncSession, task: ProcessingTask
) -> AnalysisContract | None:
    try:
        return AnalysisContract.model_validate(task.analysis_contract)
    except ValidationError:
        # Old JSON must not repeatedly poison the worker queue. Keep only a
        # stable, content-free diagnostic in the task event stream.
        task.status = TaskStatus.FAILED
        task.claimed_by = None
        task.lease_expires_at = None
        task.finished_at = datetime.now(UTC)
        task.last_error_code = "VALIDATION_ERROR"
        task.last_error_message = "任务分析契约已过期，需重新创建任务。"
        await append_task_event(
            session,
            task,
            message="任务因不兼容的历史分析契约被隔离。",
            error_code="VALIDATION_ERROR",
        )
        return None


@router.post("/classrooms/{classroom_id}/tasks", response_model=TaskRead, status_code=201)
async def post_task(
    classroom_id: UUID,
    body: TaskCreate,
    session: Db,
    user: CurrentUser,
) -> TaskRead:
    task = await create_processing_task(
        session,
        owner_id=user.id,
        classroom_id=classroom_id,
        asset_ids=body.asset_ids,
        privacy_mode=body.privacy_mode,
        analysis_contract=body.analysis_contract,
        trace_id=current_trace_id.get(),
    )
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="task.created",
        resource_type="processing_task",
        resource_id=task.id,
        details={"asset_count": len(body.asset_ids), "privacy_mode": body.privacy_mode.value},
        trace_id=task.trace_id,
    )
    return _task_read(task)


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, session: Db, user: CurrentUser) -> TaskRead:
    return _task_read(await get_owned_or_404(session, ProcessingTask, task_id, user.id))


@router.get("/tasks/{task_id}/assets", response_model=list[AssetRead])
async def get_assets(task_id: UUID, session: Db, user: CurrentUser) -> list[AssetRead]:
    """Return the authenticated teacher's task inputs for refresh recovery.

    Only stable asset metadata is returned. Object keys are never converted to
    public URLs here; the browser requests a short-lived download URL for the
    selected video through the dedicated asset endpoint.
    """

    await get_owned_or_404(session, ProcessingTask, task_id, user.id)
    return [
        AssetRead.model_validate(asset)
        for asset in await get_task_assets(session, task_id, user.id)
    ]


@router.get("/tasks", response_model=list[TaskRead])
async def get_tasks(
    session: Db,
    user: CurrentUser,
    classroom_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskRead]:
    return [
        _task_read(row)
        for row in await list_tasks(
            session,
            user.id,
            classroom_id=classroom_id,
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/tasks/{task_id}/events", response_model=list[TaskEventRead])
async def get_events(task_id: UUID, session: Db, user: CurrentUser) -> list[TaskEventRead]:
    return [
        TaskEventRead.model_validate(row)
        for row in await list_task_events(session, user.id, task_id)
    ]


@router.post("/tasks/{task_id}/retry", response_model=TaskRead)
async def post_retry(task_id: UUID, session: Db, user: CurrentUser) -> TaskRead:
    task = await get_owned_or_404(session, ProcessingTask, task_id, user.id)
    if TaskStatus(task.status) is not TaskStatus.FAILED:
        raise StateConflictError("只有失败任务可以重试。")
    task.status = TaskStatus.QUEUED
    task.progress = 0.0
    task.retry_count += 1
    task.last_error_code = None
    task.last_error_message = None
    task.claimed_by = None
    task.lease_expires_at = None
    task.finished_at = None
    task.trace_id = current_trace_id.get()
    await append_task_event(session, task, message="教师已请求重试。")
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="task.retried",
        resource_type="processing_task",
        resource_id=task.id,
        details={"retry_count": task.retry_count},
        trace_id=task.trace_id,
    )
    await session.refresh(task)
    return _task_read(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
async def post_cancel(task_id: UUID, session: Db, user: CurrentUser) -> TaskRead:
    task = await get_owned_or_404(session, ProcessingTask, task_id, user.id)
    current = TaskStatus(task.status)
    if TaskStatus.CANCELLED not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise StateConflictError("当前任务状态不允许取消。")
    task.status = TaskStatus.CANCELLED
    task.finished_at = datetime.now(UTC)
    task.claimed_by = None
    task.lease_expires_at = None
    task.trace_id = current_trace_id.get()
    await append_task_event(session, task, message="教师已取消任务。")
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="task.cancelled",
        resource_type="processing_task",
        resource_id=task.id,
        trace_id=task.trace_id,
    )
    await session.refresh(task)
    return _task_read(task)


@router.post("/internal/tasks/claim", response_model=InternalTaskClaim | None)
async def post_claim(
    body: InternalTaskClaimRequest,
    session: Db,
    _identity: Worker,
    storage: Storage,
) -> InternalTaskClaim | None:
    if any(stage not in WORKER_WRITABLE_STAGES for stage in body.stages):
        raise PermissionDeniedError(
            "Worker 不能领取 Agent 专属的 analyze 阶段。"
        )
    claimed = await claim_task(
        session,
        worker_id=body.worker_id,
        stages=body.stages,
        lease_seconds=body.lease_seconds,
    )
    if claimed is None:
        return None
    task, assets = claimed
    analysis_contract = await _claim_contract_or_quarantine(session, task)
    if analysis_contract is None:
        return None
    assert task.lease_expires_at is not None
    assert task.trace_id is not None
    return InternalTaskClaim(
        task_id=task.id,
        classroom_id=task.classroom_id,
        owner_id=task.owner_id,
        stage=task.stage,
        privacy_mode=task.privacy_mode,
        assets=[
            InternalAssetRead(
                **AssetRead.model_validate(asset).model_dump(),
                download_url=await storage.presign_download(asset.object_key),
                verified_etag=asset.etag,
            )
            for asset in assets
        ],
        analysis_contract=analysis_contract,
        lease_expires_at=task.lease_expires_at,
        trace_id=task.trace_id,
    )


@router.post("/internal/tasks/{task_id}/heartbeat", response_model=TaskRead)
async def post_heartbeat(
    task_id: UUID,
    body: InternalTaskHeartbeat,
    session: Db,
    _identity: WorkerHeartbeat,
) -> TaskRead:
    task = await get_internal_task(session, task_id)
    now = datetime.now(UTC)
    if (
        TaskStatus(task.status) is not TaskStatus.RUNNING
        or task.claimed_by != body.worker_id
        or task.lease_expires_at is None
        or task.lease_expires_at < now
    ):
        raise StateConflictError("任务租约不存在、已过期或不属于该 Worker。")
    task.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    await session.flush()
    await session.refresh(task)
    return _task_read(task)


@router.post("/internal/tasks/{task_id}/handoff-agent", response_model=TaskRead)
async def post_handoff_agent(
    task_id: UUID,
    body: InternalAgentHandoff,
    session: Db,
    _identity: WorkerHandoff,
) -> TaskRead:
    return _task_read(
        await handoff_task_to_agent(
            session,
            task_id=task_id,
            worker_id=body.worker_id,
        )
    )


@router.post(
    "/internal/agent/tasks/claim",
    response_model=InternalAgentTaskClaim | None,
)
async def post_agent_claim(
    body: InternalAgentClaimRequest,
    session: Db,
    _identity: AgentClaim,
) -> InternalAgentTaskClaim | None:
    claimed = await claim_task(
        session,
        worker_id=body.agent_id,
        stages=[TaskStage.ANALYZE],
        lease_seconds=body.lease_seconds,
        claimant_label="Agent",
    )
    if claimed is None:
        return None
    task, _assets = claimed
    analysis_contract = await _claim_contract_or_quarantine(session, task)
    if analysis_contract is None:
        return None
    assert task.lease_expires_at is not None
    assert task.trace_id is not None
    segments = await get_transcript_segments(session, task.owner_id, task.id)
    if not segments:
        raise StateConflictError("Agent 领取的任务没有可分析逐字稿。")
    evidence = [
        InternalAgentEvidence(
            id=segment.id,
            task_id=task.id,
            owner_id=task.owner_id,
            reference=EvidenceReference(
                source_type=EvidenceSourceType.TRANSCRIPT,
                segment_id=segment.id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                quote=segment.text[:2000],
            ),
            text=segment.text,
            translation=segment.translation,
            metadata={
                "index": segment.index,
                "speaker": segment.speaker,
                "source_language": segment.source_language,
            },
        )
        for segment in segments
    ]
    pages = await get_courseware_pages(session, task.owner_id, task.id)
    evidence.extend(
        InternalAgentEvidence(
            id=page.id,
            task_id=task.id,
            owner_id=task.owner_id,
            reference=EvidenceReference(
                source_type=EvidenceSourceType.COURSEWARE,
                asset_id=page.asset_id,
                page_no=page.page_no,
                quote=page.text[:2000],
            ),
            text=page.text[:10000],
            metadata={"page_no": page.page_no},
        )
        for page in pages
    )
    return InternalAgentTaskClaim(
        task_id=task.id,
        classroom_id=task.classroom_id,
        owner_id=task.owner_id,
        privacy_mode=task.privacy_mode,
        analysis_contract=analysis_contract,
        evidence=evidence,
        lease_expires_at=task.lease_expires_at,
        trace_id=task.trace_id,
    )


@router.post("/internal/agent/tasks/{task_id}/heartbeat", response_model=TaskRead)
async def post_agent_heartbeat(
    task_id: UUID,
    body: InternalAgentHeartbeat,
    session: Db,
    _identity: AgentHeartbeat,
) -> TaskRead:
    task = await get_internal_task(session, task_id)
    now = datetime.now(UTC)
    if (
        TaskStatus(task.status) is not TaskStatus.RUNNING
        or TaskStage(task.stage) is not TaskStage.ANALYZE
        or task.claimed_by != body.agent_id
        or task.lease_expires_at is None
        or task.lease_expires_at < now
    ):
        raise StateConflictError("Agent 租约不存在、已过期或不属于该运行器。")
    task.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
    await session.flush()
    await session.refresh(task)
    return _task_read(task)


@router.patch("/internal/tasks/{task_id}/state", response_model=TaskRead)
async def patch_state(
    task_id: UUID,
    body: InternalTaskStateUpdate,
    session: Db,
    identity: StateWriter,
) -> TaskRead:
    task = await get_internal_task(session, task_id)
    writable = (
        AGENT_WRITABLE_STAGES
        if identity is ServiceIdentity.AGENT
        else WORKER_WRITABLE_STAGES
    )
    if body.stage not in writable:
        raise PermissionDeniedError("该服务身份无权回写这个处理阶段。")

    current_status = TaskStatus(task.status)
    if body.status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
        raise StateConflictError(
            f"不允许从 {current_status.value} 迁移到 {body.status.value}。"
        )
    current_stage = TaskStage(task.stage)
    if _STAGE_ORDER[body.stage] < _STAGE_ORDER[current_stage]:
        raise StateConflictError("任务阶段不能倒退。")
    if body.status is TaskStatus.SUCCEEDED and body.stage is not TaskStage.ANALYZE:
        raise StateConflictError("只有 analyze 阶段可以将整个任务标记为成功。")

    task.stage = body.stage
    task.status = body.status
    task.progress = 1.0 if body.status is TaskStatus.SUCCEEDED else body.progress
    task.trace_id = body.trace_id or task.trace_id or current_trace_id.get()
    task.last_error_code = body.error_code if body.status is TaskStatus.FAILED else None
    task.last_error_message = body.message if body.status is TaskStatus.FAILED else None
    if body.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
        task.finished_at = datetime.now(UTC)
        task.claimed_by = None
        task.lease_expires_at = None
    await append_task_event(
        session,
        task,
        message=body.message,
        error_code=body.error_code,
    )
    await session.refresh(task)
    return _task_read(task)

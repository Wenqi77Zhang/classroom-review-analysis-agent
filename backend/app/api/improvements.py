"""M2 improvement-loop and M3 multi-course portfolio endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent.skills.evidence_comparison import (
    PROMPT_VERSION,
    SKILL_NAME,
    ComparisonCandidate,
    propose_outcome,
    select_related_candidate,
)
from backend.app.dependencies import get_current_user, get_db
from backend.app.errors import StateConflictError, ValidationFailedError, current_trace_id
from backend.app.models import (
    AnalysisConclusion,
    Classroom,
    Course,
    ImprovementAction,
    ImprovementComparison,
    ImprovementCycle,
    ProcessingTask,
    Report,
    User,
)
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    ConclusionType,
    EvidenceReference,
    ReviewAction,
    ReviewStatus,
)
from backend.app.schemas.improvement import (
    AggregateReportRead,
    ComparisonOutcome,
    ComparisonReviewRequest,
    CycleStatus,
    ImprovementActionCreate,
    ImprovementActionRead,
    ImprovementActionUpdate,
    ImprovementComparisonRead,
    ImprovementCycleCreate,
    ImprovementCycleRead,
    ImprovementCycleUpdate,
    PortfolioClassroomRead,
    PortfolioCourseRead,
    PortfolioOverview,
    ValidationMode,
)
from backend.app.schemas.task import TaskStatus
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404

router = APIRouter(tags=["improvements"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _evidence_payload(conclusion: AnalysisConclusion) -> list[dict]:
    return [
        {
            "id": str(item.id),
            "source_type": str(item.source_type),
            "asset_id": str(item.asset_id) if item.asset_id else None,
            "segment_id": str(item.segment_id) if item.segment_id else None,
            "start_ms": item.start_ms,
            "end_ms": item.end_ms,
            "page_no": item.page_no,
            "image_ref": item.image_ref,
            "quote": item.quote,
        }
        for item in conclusion.evidence_refs
    ]


def _comparison_read(item: ImprovementComparison) -> ImprovementComparisonRead:
    return ImprovementComparisonRead(
        id=item.id,
        action_id=item.action_id,
        baseline_conclusion_id=item.baseline_conclusion_id,
        followup_conclusion_id=item.followup_conclusion_id,
        proposed_outcome=item.proposed_outcome,
        summary=item.summary,
        baseline_evidence=[EvidenceReference.model_validate(row) for row in item.baseline_evidence],
        followup_evidence=[EvidenceReference.model_validate(row) for row in item.followup_evidence],
        review_status=item.review_status,
        reviewed_summary=item.reviewed_summary,
        trace_id=item.trace_id,
        skill=item.skill,
        prompt_version=item.prompt_version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _cycle_read(cycle: ImprovementCycle) -> ImprovementCycleRead:
    return ImprovementCycleRead(
        id=cycle.id,
        course_id=cycle.course_id,
        baseline_classroom_id=cycle.baseline_classroom_id,
        followup_classroom_id=cycle.followup_classroom_id,
        title=cycle.title,
        objective=cycle.objective,
        status=cycle.status,
        validation_mode=cycle.validation_mode,
        actions=[ImprovementActionRead.model_validate(item) for item in cycle.actions],
        comparisons=[_comparison_read(item) for item in cycle.comparisons],
        created_at=cycle.created_at,
        updated_at=cycle.updated_at,
    )


async def _load_cycle(session: AsyncSession, cycle_id: UUID, owner_id: UUID) -> ImprovementCycle:
    cycle = await session.scalar(
        select(ImprovementCycle)
        .where(ImprovementCycle.id == cycle_id, ImprovementCycle.owner_id == owner_id)
        .options(
            selectinload(ImprovementCycle.actions),
            selectinload(ImprovementCycle.comparisons),
        )
    )
    if cycle is None:
        from backend.app.errors import NotFoundError

        raise NotFoundError()
    return cycle


def _match_followup(
    action: ImprovementAction, candidates: list[AnalysisConclusion]
) -> AnalysisConclusion | None:
    key = select_related_candidate(
        action.action_text,
        action.success_criterion,
        [
            ComparisonCandidate(
                key=str(item.id),
                content=item.reviewed_content or item.content,
                created_at=item.created_at,
            )
            for item in candidates
        ],
    )
    return next((item for item in candidates if str(item.id) == key), None)


@router.post(
    "/improvement-cycles", response_model=ImprovementCycleRead, status_code=status.HTTP_201_CREATED
)
async def create_cycle(
    body: ImprovementCycleCreate, session: Db, user: CurrentUser
) -> ImprovementCycleRead:
    baseline = await get_owned_or_404(session, Classroom, body.baseline_classroom_id, user.id)
    cycle = ImprovementCycle(
        owner_id=user.id,
        course_id=baseline.course_id,
        baseline_classroom_id=baseline.id,
        title=body.title,
        objective=body.objective,
        validation_mode=body.validation_mode,
    )
    session.add(cycle)
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_cycle.created",
        resource_type="improvement_cycle",
        resource_id=cycle.id,
        details={"validation_mode": body.validation_mode.value},
    )
    return _cycle_read(await _load_cycle(session, cycle.id, user.id))


@router.get("/improvement-cycles", response_model=list[ImprovementCycleRead])
async def list_cycles(session: Db, user: CurrentUser) -> list[ImprovementCycleRead]:
    rows = await session.scalars(
        select(ImprovementCycle)
        .where(ImprovementCycle.owner_id == user.id)
        .options(selectinload(ImprovementCycle.actions), selectinload(ImprovementCycle.comparisons))
        .order_by(ImprovementCycle.created_at.desc())
    )
    return [_cycle_read(item) for item in rows.unique().all()]


@router.get("/improvement-cycles/{cycle_id}", response_model=ImprovementCycleRead)
async def get_cycle(cycle_id: UUID, session: Db, user: CurrentUser) -> ImprovementCycleRead:
    return _cycle_read(await _load_cycle(session, cycle_id, user.id))


@router.patch("/improvement-cycles/{cycle_id}", response_model=ImprovementCycleRead)
async def update_cycle(
    cycle_id: UUID, body: ImprovementCycleUpdate, session: Db, user: CurrentUser
) -> ImprovementCycleRead:
    cycle = await _load_cycle(session, cycle_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    followup_id = changes.get("followup_classroom_id")
    if followup_id is not None:
        followup = await get_owned_or_404(session, Classroom, followup_id, user.id)
        if followup.course_id != cycle.course_id:
            raise ValidationFailedError("第二轮课堂必须属于同一门课程。")
        if followup.id == cycle.baseline_classroom_id:
            raise ValidationFailedError("第二轮课堂不能与基线课堂相同。")
        cycle.status = CycleStatus.FOLLOWUP_LINKED
    for field, value in changes.items():
        setattr(cycle, field, value)
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_cycle.updated",
        resource_type="improvement_cycle",
        resource_id=cycle.id,
        details={"updated_fields": sorted(changes)},
    )
    return _cycle_read(await _load_cycle(session, cycle.id, user.id))


@router.post(
    "/improvement-cycles/{cycle_id}/actions",
    response_model=ImprovementActionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_action(
    cycle_id: UUID, body: ImprovementActionCreate, session: Db, user: CurrentUser
) -> ImprovementActionRead:
    cycle = await _load_cycle(session, cycle_id, user.id)
    conclusion = await get_owned_or_404(
        session, AnalysisConclusion, body.source_conclusion_id, user.id
    )
    if conclusion.classroom_id != cycle.baseline_classroom_id:
        raise ValidationFailedError("行动必须追溯到基线课堂的结论。")
    if (
        ConclusionType(conclusion.type) is not ConclusionType.SUGGESTION
        or ReviewStatus(conclusion.review_status) not in REPORTABLE_REVIEW_STATUSES
    ):
        raise StateConflictError("只有教师已接受或修改确认的建议才能转为改进行动。")
    action = ImprovementAction(owner_id=user.id, cycle_id=cycle.id, **body.model_dump())
    session.add(action)
    cycle.status = CycleStatus.ACTIONS_READY
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_action.created",
        resource_type="improvement_action",
        resource_id=action.id,
        details={"cycle_id": str(cycle.id)},
    )
    return ImprovementActionRead.model_validate(action)


@router.patch("/improvement-actions/{action_id}", response_model=ImprovementActionRead)
async def update_action(
    action_id: UUID, body: ImprovementActionUpdate, session: Db, user: CurrentUser
) -> ImprovementActionRead:
    action = await get_owned_or_404(session, ImprovementAction, action_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(action, field, value)
    await session.flush()
    await session.refresh(action)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_action.updated",
        resource_type="improvement_action",
        resource_id=action.id,
        details={"updated_fields": sorted(body.model_fields_set)},
    )
    return ImprovementActionRead.model_validate(action)


@router.post(
    "/improvement-cycles/{cycle_id}/comparisons",
    response_model=list[ImprovementComparisonRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_comparisons(
    cycle_id: UUID, session: Db, user: CurrentUser
) -> list[ImprovementComparisonRead]:
    cycle = await _load_cycle(session, cycle_id, user.id)
    if cycle.followup_classroom_id is None or not cycle.actions:
        raise StateConflictError("请先建立改进行动并关联同一课程的第二轮课堂。")
    succeeded = await session.scalar(
        select(ProcessingTask.id)
        .where(
            ProcessingTask.owner_id == user.id,
            ProcessingTask.classroom_id == cycle.followup_classroom_id,
            ProcessingTask.status == TaskStatus.SUCCEEDED,
        )
        .limit(1)
    )
    if succeeded is None:
        raise StateConflictError("第二轮课堂尚未完成真实处理，不能生成对比。")
    rows = await session.scalars(
        select(AnalysisConclusion)
        .where(
            AnalysisConclusion.owner_id == user.id,
            AnalysisConclusion.classroom_id == cycle.followup_classroom_id,
            AnalysisConclusion.review_status.in_(
                tuple(item.value for item in REPORTABLE_REVIEW_STATUSES)
            ),
        )
        .options(selectinload(AnalysisConclusion.evidence_refs))
    )
    candidates = [item for item in rows.unique().all() if item.evidence_refs]
    baseline_ids = [item.source_conclusion_id for item in cycle.actions]
    base_rows = await session.scalars(
        select(AnalysisConclusion)
        .where(AnalysisConclusion.id.in_(baseline_ids), AnalysisConclusion.owner_id == user.id)
        .options(selectinload(AnalysisConclusion.evidence_refs))
    )
    baselines = {item.id: item for item in base_rows.unique().all()}
    for old in list(cycle.comparisons):
        await session.delete(old)
    await session.flush()
    trace_id = current_trace_id.get()
    created: list[ImprovementComparison] = []
    for action in cycle.actions:
        baseline = baselines[action.source_conclusion_id]
        if not baseline.evidence_refs:
            raise StateConflictError("基线建议缺少可定位证据，不能进入两轮对比。")
        followup = _match_followup(action, candidates)
        if followup is None:
            outcome = ComparisonOutcome.INSUFFICIENT_EVIDENCE
            summary = "第二轮已处理，但尚无与本行动充分对应且经教师确认的结论；不能判断是否改进。"
            followup_evidence: list[dict] = []
        else:
            followup_text = followup.reviewed_content or followup.content
            outcome = ComparisonOutcome(propose_outcome(followup_text))
            summary = f"系统找到与行动“{action.action_text}”相关的第二轮证据，提出“{outcome.value}”候选判断。该判断不是因果结论，须由教师核对两轮证据后确认。"
            followup_evidence = _evidence_payload(followup)
        comparison = ImprovementComparison(
            owner_id=user.id,
            cycle_id=cycle.id,
            action_id=action.id,
            baseline_conclusion_id=baseline.id,
            followup_conclusion_id=followup.id if followup else None,
            proposed_outcome=outcome,
            summary=summary,
            baseline_evidence=_evidence_payload(baseline),
            followup_evidence=followup_evidence,
            trace_id=trace_id if trace_id != "-" else uuid.uuid4().hex,
            skill=SKILL_NAME,
            prompt_version=PROMPT_VERSION,
        )
        session.add(comparison)
        created.append(comparison)
    cycle.status = CycleStatus.REVIEWING
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_comparisons.generated",
        resource_type="improvement_cycle",
        resource_id=cycle.id,
        details={"comparison_count": len(created), "validation_mode": str(cycle.validation_mode)},
    )
    return [_comparison_read(item) for item in created]


@router.post(
    "/improvement-comparisons/{comparison_id}/review", response_model=ImprovementComparisonRead
)
async def review_comparison(
    comparison_id: UUID, body: ComparisonReviewRequest, session: Db, user: CurrentUser
) -> ImprovementComparisonRead:
    comparison = await get_owned_or_404(session, ImprovementComparison, comparison_id, user.id)
    mapping = {
        ReviewAction.ACCEPT: ReviewStatus.ACCEPTED,
        ReviewAction.MODIFY: ReviewStatus.MODIFIED,
        ReviewAction.REJECT: ReviewStatus.REJECTED,
    }
    comparison.review_status = mapping[body.action]
    comparison.reviewed_summary = body.edited_summary.strip() if body.edited_summary else None
    comparison.review_note = body.note.strip() if body.note else None
    await session.flush()
    cycle = await _load_cycle(session, comparison.cycle_id, user.id)
    if cycle.comparisons and all(
        ReviewStatus(item.review_status) is not ReviewStatus.PENDING for item in cycle.comparisons
    ):
        cycle.status = CycleStatus.COMPLETED
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="improvement_comparison.reviewed",
        resource_type="improvement_comparison",
        resource_id=comparison.id,
        details={"action": body.action.value},
    )
    return _comparison_read(comparison)


@router.get("/portfolio/overview", response_model=PortfolioOverview)
async def portfolio_overview(session: Db, user: CurrentUser) -> PortfolioOverview:
    courses = list(
        (
            await session.scalars(
                select(Course).where(Course.owner_id == user.id).order_by(Course.created_at.desc())
            )
        ).all()
    )
    classrooms = list(
        (await session.scalars(select(Classroom).where(Classroom.owner_id == user.id))).all()
    )
    tasks = list(
        (
            await session.scalars(select(ProcessingTask).where(ProcessingTask.owner_id == user.id))
        ).all()
    )
    conclusions = list(
        (
            await session.scalars(
                select(AnalysisConclusion).where(AnalysisConclusion.owner_id == user.id)
            )
        ).all()
    )
    reports = list((await session.scalars(select(Report).where(Report.owner_id == user.id))).all())
    cycles = list(
        (
            await session.scalars(
                select(ImprovementCycle).where(ImprovementCycle.owner_id == user.id)
            )
        ).all()
    )
    course_rows: list[PortfolioCourseRead] = []
    for course in courses:
        owned_classrooms = [item for item in classrooms if item.course_id == course.id]
        classroom_rows = []
        for classroom in owned_classrooms:
            owned_tasks = [item for item in tasks if item.classroom_id == classroom.id]
            latest_task = max(owned_tasks, key=lambda item: item.created_at, default=None)
            classroom_rows.append(
                PortfolioClassroomRead(
                    id=classroom.id,
                    title=classroom.title,
                    latest_task_id=latest_task.id if latest_task else None,
                    task_count=len(owned_tasks),
                    succeeded_task_count=sum(
                        TaskStatus(item.status) is TaskStatus.SUCCEEDED for item in owned_tasks
                    ),
                    reviewed_conclusion_count=sum(
                        item.classroom_id == classroom.id
                        and ReviewStatus(item.review_status) in REPORTABLE_REVIEW_STATUSES
                        for item in conclusions
                    ),
                    report_ready=any(item.classroom_id == classroom.id for item in reports),
                )
            )
        course_rows.append(
            PortfolioCourseRead(
                id=course.id,
                name=course.name,
                classroom_count=len(owned_classrooms),
                completed_cycle_count=sum(
                    item.course_id == course.id
                    and CycleStatus(item.status) is CycleStatus.COMPLETED
                    for item in cycles
                ),
                classrooms=classroom_rows,
            )
        )
    return PortfolioOverview(
        course_count=len(courses),
        classroom_count=len(classrooms),
        completed_cycle_count=sum(
            CycleStatus(item.status) is CycleStatus.COMPLETED for item in cycles
        ),
        courses=course_rows,
    )


@router.get("/portfolio/aggregate-report", response_model=AggregateReportRead)
async def aggregate_report(session: Db, user: CurrentUser) -> AggregateReportRead:
    rows = await session.scalars(
        select(ImprovementCycle)
        .where(
            ImprovementCycle.owner_id == user.id,
            ImprovementCycle.status == CycleStatus.COMPLETED,
            ImprovementCycle.validation_mode == ValidationMode.REAL,
        )
        .options(selectinload(ImprovementCycle.actions), selectinload(ImprovementCycle.comparisons))
        .order_by(ImprovementCycle.created_at)
    )
    cycles = list(rows.unique().all())
    sections = [
        "# 多课程教学改进汇总",
        "",
        "仅汇总真实轮次中经教师接受或修改确认的对比结论；模型候选与驳回内容不进入正文。",
    ]
    included: list[UUID] = []
    for cycle in cycles:
        accepted = [
            item
            for item in cycle.comparisons
            if ReviewStatus(item.review_status) in REPORTABLE_REVIEW_STATUSES
        ]
        if not accepted:
            continue
        included.append(cycle.id)
        sections.extend(["", f"## {cycle.title}", "", f"改进目标：{cycle.objective}"])
        for item in accepted:
            text = item.reviewed_summary or item.summary
            sections.append(f"- {text}（教师确认：{item.review_status}；Trace：{item.trace_id}）")
    if not included:
        sections.extend(["", "暂无符合汇总门禁的真实改进轮次。"])
    return AggregateReportRead(
        title="多课程教学改进汇总",
        content="\n".join(sections),
        included_cycle_ids=included,
        generated_at=datetime.now(UTC),
        evidence_boundary="不汇总合成验证轮次、待复核或已驳回的模型判断；内容不构成自动教学评分。",
    )

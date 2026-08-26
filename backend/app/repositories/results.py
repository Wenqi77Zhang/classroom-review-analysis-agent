"""Transcript and evidence-grounded conclusion persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.errors import NotFoundError, ValidationFailedError
from backend.app.models import (
    AnalysisConclusion,
    Asset,
    CoursewarePage,
    EvidenceReference,
    ProcessingTask,
    TranscriptSegment,
    TranscriptSegmentRevision,
)
from backend.app.models.processing import task_assets
from backend.app.schemas.analysis_report import (
    EvidenceSourceType,
    InternalConclusionBatchWrite,
    ReviewStatus,
)
from backend.app.schemas.courseware import InternalCoursewareWrite
from backend.app.schemas.task import AssetKind
from backend.app.schemas.transcript import InternalTranscriptWrite, TranscriptSegmentUpdate
from backend.app.services.permissions import get_owned_or_404


async def replace_transcript(
    session: AsyncSession,
    task: ProcessingTask,
    body: InternalTranscriptWrite,
) -> list[TranscriptSegment]:
    task.transcript_duration_ms = body.duration_ms
    await session.execute(
        delete(TranscriptSegment).where(
            TranscriptSegment.task_id == task.id,
            TranscriptSegment.owner_id == task.owner_id,
        )
    )
    segments = [
        TranscriptSegment(
            owner_id=task.owner_id,
            task_id=task.id,
            index=item.index,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            speaker=item.speaker,
            text=item.text,
            source_language=body.source_language,
            translation=item.translation,
            translation_language=body.translation_language,
        )
        for item in body.segments
    ]
    session.add_all(segments)
    await session.flush()
    return segments


async def get_transcript_segments(
    session: AsyncSession,
    owner_id: UUID,
    task_id: UUID,
) -> list[TranscriptSegment]:
    await get_owned_or_404(session, ProcessingTask, task_id, owner_id)
    rows = await session.scalars(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.owner_id == owner_id,
            TranscriptSegment.task_id == task_id,
        )
        .order_by(TranscriptSegment.index)
    )
    return list(rows)


async def replace_courseware_pages(
    session: AsyncSession,
    task: ProcessingTask,
    body: InternalCoursewareWrite,
) -> list[CoursewarePage]:
    """Replace task-scoped page evidence after verifying every asset boundary."""

    attached_assets = {
        asset.id: asset
        for asset in await session.scalars(
            select(Asset)
            .join(task_assets, task_assets.c.asset_id == Asset.id)
            .where(
                task_assets.c.task_id == task.id,
                task_assets.c.owner_id == task.owner_id,
                Asset.owner_id == task.owner_id,
            )
        )
    }
    seen: set[tuple[UUID, int]] = set()
    for item in body.pages:
        asset = attached_assets.get(item.asset_id)
        if asset is None:
            raise NotFoundError("课件页引用的文件不属于当前任务。")
        if AssetKind(asset.kind) is not AssetKind.COURSEWARE:
            raise ValidationFailedError("课件页只能绑定当前任务的课件文件。")
        key = (item.asset_id, item.page_no)
        if key in seen:
            raise ValidationFailedError("同一课件文件的页码不能重复。")
        seen.add(key)

    await session.execute(
        delete(CoursewarePage).where(
            CoursewarePage.task_id == task.id,
            CoursewarePage.owner_id == task.owner_id,
        )
    )
    pages = [
        CoursewarePage(
            owner_id=task.owner_id,
            task_id=task.id,
            asset_id=item.asset_id,
            page_no=item.page_no,
            text=item.text,
        )
        for item in body.pages
    ]
    session.add_all(pages)
    await session.flush()
    return pages


async def get_courseware_pages(
    session: AsyncSession,
    owner_id: UUID,
    task_id: UUID,
) -> list[CoursewarePage]:
    await get_owned_or_404(session, ProcessingTask, task_id, owner_id)
    rows = await session.scalars(
        select(CoursewarePage)
        .where(
            CoursewarePage.owner_id == owner_id,
            CoursewarePage.task_id == task_id,
        )
        .order_by(CoursewarePage.asset_id, CoursewarePage.page_no)
    )
    return list(rows)


async def edit_transcript_segment(
    session: AsyncSession,
    *,
    owner_id: UUID,
    user_id: UUID,
    segment_id: UUID,
    body: TranscriptSegmentUpdate,
) -> TranscriptSegment:
    segment = await get_owned_or_404(
        session, TranscriptSegment, segment_id, owner_id
    )
    revision = TranscriptSegmentRevision(
        owner_id=owner_id,
        segment_id=segment.id,
        previous_text=segment.text,
        previous_speaker=segment.speaker,
        previous_translation=segment.translation,
        edited_by_id=user_id,
    )
    session.add(revision)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(segment, field, value)
    segment.is_edited = True
    segment.edited_at = datetime.now(UTC)
    await session.flush()
    return segment


async def _validate_evidence_scope(
    session: AsyncSession,
    task: ProcessingTask,
    *,
    source_type: EvidenceSourceType,
    asset_id: UUID | None,
    segment_id: UUID | None,
    page_no: int | None,
    image_ref: str | None,
) -> None:
    if source_type is EvidenceSourceType.TRANSCRIPT and segment_id is None:
        raise ValidationFailedError("逐字稿证据必须绑定当前任务的 segment_id。")
    if source_type in {EvidenceSourceType.VIDEO, EvidenceSourceType.COURSEWARE} and asset_id is None:
        raise ValidationFailedError("视频或课件证据必须绑定当前任务的 asset_id。")
    if (
        source_type is EvidenceSourceType.FRAME
        and asset_id is None
        and image_ref is None
    ):
        raise ValidationFailedError("画面证据必须绑定文件或任务内画面引用。")

    if asset_id is not None:
        owned_asset = await session.scalar(
            select(Asset)
            .join(task_assets, task_assets.c.asset_id == Asset.id)
            .where(
                Asset.id == asset_id,
                Asset.owner_id == task.owner_id,
                task_assets.c.task_id == task.id,
                task_assets.c.owner_id == task.owner_id,
            )
        )
        if owned_asset is None:
            raise NotFoundError("证据文件不属于当前任务。")
        expected_kind = {
            EvidenceSourceType.VIDEO: AssetKind.VIDEO,
            EvidenceSourceType.COURSEWARE: AssetKind.COURSEWARE,
            EvidenceSourceType.FRAME: AssetKind.VIDEO,
        }.get(source_type)
        if expected_kind is not None and AssetKind(owned_asset.kind) is not expected_kind:
            raise ValidationFailedError(
                "证据来源类型与绑定文件类型不一致。"
            )
        if source_type is EvidenceSourceType.COURSEWARE and page_no is not None:
            courseware_page = await session.scalar(
                select(CoursewarePage.id).where(
                    CoursewarePage.owner_id == task.owner_id,
                    CoursewarePage.task_id == task.id,
                    CoursewarePage.asset_id == asset_id,
                    CoursewarePage.page_no == page_no,
                )
            )
            if courseware_page is None:
                raise NotFoundError("课件证据页不属于当前任务或尚未完成解析。")
    if segment_id is not None:
        segment = await session.scalar(
            select(TranscriptSegment).where(
                TranscriptSegment.id == segment_id,
                TranscriptSegment.owner_id == task.owner_id,
                TranscriptSegment.task_id == task.id,
            )
        )
        if segment is None:
            raise NotFoundError("逐字稿证据不属于当前任务。")


async def replace_pending_conclusions(
    session: AsyncSession,
    task: ProcessingTask,
    body: InternalConclusionBatchWrite,
) -> None:
    await session.execute(
        delete(AnalysisConclusion).where(
            AnalysisConclusion.task_id == task.id,
            AnalysisConclusion.owner_id == task.owner_id,
            AnalysisConclusion.review_status == ReviewStatus.PENDING,
        )
    )
    for item in body.conclusions:
        for reference in item.evidence_refs:
            await _validate_evidence_scope(
                session,
                task,
                source_type=reference.source_type,
                asset_id=reference.asset_id,
                segment_id=reference.segment_id,
                page_no=reference.page_no,
                image_ref=reference.image_ref,
            )
        conclusion = AnalysisConclusion(
            owner_id=task.owner_id,
            classroom_id=task.classroom_id,
            task_id=task.id,
            type=item.type,
            content=item.content,
            review_status=ReviewStatus.PENDING,
            trace_id=item.trace_id,
            model_name=item.model_name,
            skill=item.skill,
            prompt_version=item.prompt_version,
        )
        session.add(conclusion)
        await session.flush()
        session.add_all([
            EvidenceReference(
                owner_id=task.owner_id,
                conclusion_id=conclusion.id,
                source_type=reference.source_type,
                asset_id=reference.asset_id,
                segment_id=reference.segment_id,
                start_ms=reference.start_ms,
                end_ms=reference.end_ms,
                page_no=reference.page_no,
                image_ref=reference.image_ref,
                quote=reference.quote,
            )
            for reference in item.evidence_refs
        ])
    await session.flush()


async def list_conclusions(
    session: AsyncSession,
    owner_id: UUID,
    classroom_id: UUID,
) -> list[AnalysisConclusion]:
    rows = await session.scalars(
        select(AnalysisConclusion)
        .options(selectinload(AnalysisConclusion.evidence_refs))
        .where(
            AnalysisConclusion.owner_id == owner_id,
            AnalysisConclusion.classroom_id == classroom_id,
        )
        .order_by(AnalysisConclusion.created_at, AnalysisConclusion.id)
    )
    return list(rows)

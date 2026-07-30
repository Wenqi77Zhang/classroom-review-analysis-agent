"""Build deterministic in-memory evidence drafts for member 3/5 handoff."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from agent.contracts import EvidenceItem
from backend.app.schemas.analysis_report import EvidenceReference, EvidenceSourceType
from backend.app.schemas.transcript import InternalTranscriptWrite
from worker.courseware_types import CoursewareDocument
from worker.errors import WorkerError, WorkerErrorCode

EVIDENCE_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "classroom-review-analysis-agent/worker-evidence-v1",
)
PIPELINE_VERSION = "worker-evidence-v1"


def _evidence_id(
    *,
    task_id: UUID,
    source_type: EvidenceSourceType,
    asset_id: UUID,
    locator: str,
    text: str,
) -> UUID:
    digest = sha256(text.encode("utf-8")).hexdigest()
    name = "|".join(
        [str(task_id), source_type.value, str(asset_id), locator, digest]
    )
    return uuid5(EVIDENCE_NAMESPACE, name)


def _validate_inputs(
    *,
    task_id: UUID,
    owner_id: UUID,
    video_asset_id: UUID,
    transcript: InternalTranscriptWrite,
    courseware: Sequence[CoursewareDocument],
) -> None:
    if task_id is None or owner_id is None or video_asset_id is None:
        raise ValueError("evidence scope IDs are required")
    if not transcript.segments or transcript.duration_ms <= 0:
        raise ValueError("transcript evidence is empty")

    previous_end = 0
    for segment in transcript.segments:
        if segment.start_ms < previous_end or segment.end_ms > transcript.duration_ms:
            raise ValueError("transcript range is outside duration or non-monotonic")
        previous_end = segment.end_ms

    for document in courseware:
        page_numbers = [page.page_no for page in document.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("courseware page numbers must be unique")


def build_evidence_index(
    *,
    task_id: UUID,
    owner_id: UUID,
    video_asset_id: UUID,
    transcript: InternalTranscriptWrite,
    courseware: Sequence[CoursewareDocument] = (),
) -> tuple[EvidenceItem, ...]:
    """Create validated evidence without persisting or inventing source IDs."""

    try:
        _validate_inputs(
            task_id=task_id,
            owner_id=owner_id,
            video_asset_id=video_asset_id,
            transcript=transcript,
            courseware=courseware,
        )
        evidence: list[EvidenceItem] = []
        for segment in transcript.segments:
            locator = f"{segment.start_ms}:{segment.end_ms}"
            metadata = {
                "pipeline_version": PIPELINE_VERSION,
                "source_index": segment.index,
            }
            for source_type in (
                EvidenceSourceType.VIDEO,
                EvidenceSourceType.TRANSCRIPT,
            ):
                reference = EvidenceReference(
                    source_type=source_type,
                    asset_id=video_asset_id,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    quote=segment.text[:2000],
                )
                evidence.append(
                    EvidenceItem(
                        id=_evidence_id(
                            task_id=task_id,
                            source_type=source_type,
                            asset_id=video_asset_id,
                            locator=locator,
                            text=segment.text,
                        ),
                        task_id=task_id,
                        owner_id=owner_id,
                        reference=reference,
                        text=segment.text,
                        translation=segment.translation,
                        metadata=metadata,
                    )
                )

        for document in courseware:
            for page in document.pages:
                text = page.text.strip()
                if not text:
                    continue
                source_type = EvidenceSourceType.COURSEWARE
                reference = EvidenceReference(
                    source_type=source_type,
                    asset_id=document.asset_id,
                    page_no=page.page_no,
                    quote=text[:2000],
                )
                evidence.append(
                    EvidenceItem(
                        id=_evidence_id(
                            task_id=task_id,
                            source_type=source_type,
                            asset_id=document.asset_id,
                            locator=str(page.page_no),
                            text=text,
                        ),
                        task_id=task_id,
                        owner_id=owner_id,
                        reference=reference,
                        text=text,
                        metadata={
                            "pipeline_version": PIPELINE_VERSION,
                            "source_index": page.page_no,
                        },
                    )
                )
        if not evidence:
            raise ValueError("evidence index is empty")
        return tuple(evidence)
    except WorkerError:
        raise
    except (TypeError, ValueError, ValidationError):
        raise WorkerError(
            WorkerErrorCode.EVIDENCE_INDEX_INVALID,
            "证据索引输入或生成结果不符合冻结契约。",
            retryable=False,
        ) from None

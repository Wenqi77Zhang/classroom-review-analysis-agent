from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from agent.contracts import EvidenceItem
from backend.app.schemas.analysis_report import EvidenceSourceType
from backend.app.schemas.transcript import (
    InternalTranscriptSegmentWrite,
    InternalTranscriptWrite,
)
from worker.courseware_types import CoursewareDocument, CoursewarePage
from worker.errors import WorkerError, WorkerErrorCode
from worker.stages.build_evidence_index import build_evidence_index


def _transcript(
    *segments: InternalTranscriptSegmentWrite,
    duration_ms: int = 2000,
) -> InternalTranscriptWrite:
    return InternalTranscriptWrite(
        source_language="en",
        translation_language="zh",
        duration_ms=duration_ms,
        trace_id="trace-evidence-test",
        segments=list(segments),
    )


def _segment(
    index: int,
    start_ms: int,
    end_ms: int,
    text: str,
    *,
    translation: str | None = None,
) -> InternalTranscriptSegmentWrite:
    return InternalTranscriptSegmentWrite(
        index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        translation=translation,
    )


def _build(
    transcript: InternalTranscriptWrite,
    *,
    courseware: tuple[CoursewareDocument, ...] = (),
    video_asset_id: UUID | None = None,
) -> tuple[EvidenceItem, ...]:
    return build_evidence_index(
        task_id=uuid4(),
        owner_id=uuid4(),
        video_asset_id=video_asset_id or uuid4(),
        transcript=transcript,
        courseware=courseware,
    )


def test_build_evidence_preserves_transcript_ranges_original_and_translation() -> None:
    transcript = _transcript(
        _segment(0, 0, 800, "Explain AI.", translation="解释人工智能。"),
        _segment(1, 800, 1800, "Second sentence.", translation="第二句。"),
    )

    evidence = _build(transcript)

    assert len(evidence) == 2
    assert [item.reference.source_type for item in evidence] == [
        EvidenceSourceType.TRANSCRIPT,
        EvidenceSourceType.TRANSCRIPT,
    ]
    assert [
        (item.reference.start_ms, item.reference.end_ms)
        for item in evidence
    ] == [(0, 800), (800, 1800)]
    assert [item.text for item in evidence] == [
        "Explain AI.",
        "Second sentence.",
    ]
    assert [item.translation for item in evidence] == [
        "解释人工智能。",
        "第二句。",
    ]
    assert all(item.reference.segment_id is None for item in evidence)


def test_build_evidence_adds_non_empty_courseware_pages() -> None:
    courseware_asset_id = uuid4()
    courseware = CoursewareDocument(
        asset_id=courseware_asset_id,
        pages=(
            CoursewarePage(page_no=1, text="Algorithm definition"),
            CoursewarePage(page_no=2, text=""),
            CoursewarePage(page_no=3, text="Complexity"),
        ),
    )

    evidence = _build(
        _transcript(_segment(0, 0, 800, "中文")),
        courseware=(courseware,),
    )
    pages = [
        item
        for item in evidence
        if item.reference.source_type is EvidenceSourceType.COURSEWARE
    ]

    assert [item.reference.page_no for item in pages] == [1, 3]
    assert [item.reference.asset_id for item in pages] == [
        courseware_asset_id,
        courseware_asset_id,
    ]
    assert [item.text for item in pages] == ["Algorithm definition", "Complexity"]


def test_build_evidence_ids_are_deterministic_for_same_scope() -> None:
    task_id = uuid4()
    owner_id = uuid4()
    asset_id = uuid4()
    transcript = _transcript(_segment(0, 0, 800, "Explain AI."))

    first = build_evidence_index(
        task_id=task_id,
        owner_id=owner_id,
        video_asset_id=asset_id,
        transcript=transcript,
    )
    second = build_evidence_index(
        task_id=task_id,
        owner_id=owner_id,
        video_asset_id=asset_id,
        transcript=transcript,
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert all(item.task_id == task_id for item in first)
    assert all(item.owner_id == owner_id for item in first)
    assert all(len(item.reference.quote or "") <= 2000 for item in first)
    assert all("text" not in item.metadata for item in first)


def test_build_evidence_rejects_empty_transcript() -> None:
    invalid = InternalTranscriptWrite.model_construct(
        source_language="zh",
        translation_language=None,
        duration_ms=0,
        segments=[],
        trace_id="trace-invalid",
    )

    with pytest.raises(WorkerError) as raised:
        _build(invalid)

    assert raised.value.code is WorkerErrorCode.EVIDENCE_INDEX_INVALID


def test_build_evidence_rejects_segment_past_duration() -> None:
    transcript = _transcript(
        _segment(0, 0, 1200, "越界"),
        duration_ms=1000,
    )

    with pytest.raises(WorkerError) as raised:
        _build(transcript)

    assert raised.value.code is WorkerErrorCode.EVIDENCE_INDEX_INVALID


def test_build_evidence_rejects_duplicate_courseware_pages() -> None:
    courseware = CoursewareDocument(
        asset_id=uuid4(),
        pages=(
            CoursewarePage(page_no=1, text="first"),
            CoursewarePage(page_no=1, text="duplicate"),
        ),
    )

    with pytest.raises(WorkerError) as raised:
        _build(
            _transcript(_segment(0, 0, 800, "中文")),
            courseware=(courseware,),
        )

    assert raised.value.code is WorkerErrorCode.EVIDENCE_INDEX_INVALID


def test_build_evidence_rejects_missing_video_asset_id() -> None:
    with pytest.raises(WorkerError) as raised:
        build_evidence_index(
            task_id=uuid4(),
            owner_id=uuid4(),
            video_asset_id=None,  # type: ignore[arg-type]
            transcript=_transcript(_segment(0, 0, 800, "中文")),
        )

    assert raised.value.code is WorkerErrorCode.EVIDENCE_INDEX_INVALID


def test_build_evidence_maps_pydantic_size_limit_to_stable_error() -> None:
    transcript = _transcript(
        _segment(0, 0, 800, "x" * 10001),
    )

    with pytest.raises(WorkerError) as raised:
        _build(transcript)

    assert raised.value.code is WorkerErrorCode.EVIDENCE_INDEX_INVALID
    assert "x" * 100 not in str(raised.value)

"""Persistence metadata invariants for the member 3 backend."""

from sqlalchemy.orm import configure_mappers

from backend.app.database import Base
from backend.app.models import (  # noqa: F401
    AnalysisConclusion,
    Asset,
    AuditEvent,
    Classroom,
    Course,
    EvidenceReference,
    ProcessingTask,
    Report,
    ReviewDecision,
    TaskEvent,
    TranscriptSegment,
    TranscriptSegmentRevision,
    User,
)

BUSINESS_TABLES = {
    "analysis_conclusions",
    "assets",
    "audit_events",
    "classrooms",
    "courses",
    "evidence_references",
    "processing_tasks",
    "reports",
    "review_decisions",
    "task_events",
    "transcript_segment_revisions",
    "transcript_segments",
}


def test_all_mappers_configure() -> None:
    configure_mappers()


def test_every_business_table_has_explicit_owner_id() -> None:
    for name in BUSINESS_TABLES:
        assert "owner_id" in Base.metadata.tables[name].columns, name


def test_video_binary_is_not_a_database_column() -> None:
    asset_columns = set(Base.metadata.tables["assets"].columns.keys())
    assert "object_key" in asset_columns
    assert not asset_columns.intersection({"data", "binary", "blob", "content"})


def test_critical_uniqueness_constraints_exist() -> None:
    transcript = Base.metadata.tables["transcript_segments"]
    reports = Base.metadata.tables["reports"]
    assert any(
        constraint.name == "uq_transcript_task_index" for constraint in transcript.constraints
    )
    assert any(constraint.name == "uq_reports_classroom" for constraint in reports.constraints)


def test_association_tables_use_composite_primary_keys() -> None:
    for name in ("task_assets", "report_conclusions"):
        table = Base.metadata.tables[name]
        assert len(table.primary_key.columns) == 2

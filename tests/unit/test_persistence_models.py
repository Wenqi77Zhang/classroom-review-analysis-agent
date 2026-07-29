"""Persistence metadata invariants for the member 3 backend."""

from sqlalchemy import ForeignKeyConstraint
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
        assert "owner_id" in table.columns


def _has_owner_scoped_fk(
    table_name: str,
    resource_column: str,
    remote_table: str,
) -> bool:
    table = Base.metadata.tables[table_name]
    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        local_columns = {column.name for column in constraint.columns}
        remote_columns = {element.target_fullname for element in constraint.elements}
        if local_columns == {resource_column, "owner_id"} and remote_columns == {
            f"{remote_table}.id",
            f"{remote_table}.owner_id",
        }:
            return True
    return False


def test_cross_resource_links_are_owner_scoped_in_database_metadata() -> None:
    expected_links = (
        ("classrooms", "course_id", "courses"),
        ("assets", "classroom_id", "classrooms"),
        ("processing_tasks", "classroom_id", "classrooms"),
        ("task_assets", "task_id", "processing_tasks"),
        ("task_assets", "asset_id", "assets"),
        ("evidence_references", "conclusion_id", "analysis_conclusions"),
        ("evidence_references", "asset_id", "assets"),
        ("report_conclusions", "report_id", "reports"),
        ("report_conclusions", "conclusion_id", "analysis_conclusions"),
    )
    for link in expected_links:
        assert _has_owner_scoped_fk(*link), link


def test_audit_owner_reference_prevents_cascade_deletion() -> None:
    audit = Base.metadata.tables["audit_events"]
    owner_foreign_key = next(iter(audit.c.owner_id.foreign_keys))
    assert owner_foreign_key.ondelete == "RESTRICT"

"""Import all persistence models so SQLAlchemy and Alembic see one metadata graph."""

from backend.app.models.identity import Classroom, Course, User
from backend.app.models.processing import (
    Asset,
    ProcessingTask,
    TaskEvent,
    TranscriptSegment,
    TranscriptSegmentRevision,
    task_assets,
)
from backend.app.models.review_report import (
    AnalysisConclusion,
    AuditEvent,
    EvidenceReference,
    Report,
    ReviewDecision,
    report_conclusions,
)

__all__ = [
    "AnalysisConclusion",
    "Asset",
    "AuditEvent",
    "Classroom",
    "Course",
    "EvidenceReference",
    "ProcessingTask",
    "Report",
    "ReviewDecision",
    "TaskEvent",
    "TranscriptSegment",
    "TranscriptSegmentRevision",
    "User",
    "report_conclusions",
    "task_assets",
]

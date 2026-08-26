"""Add M2 improvement cycles and evidence comparisons.

Revision ID: 9d2e6f4a8b10
Revises: 4a1c9e8b7d32
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9d2e6f4a8b10"
down_revision: str | None = "4a1c9e8b7d32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "improvement_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_classroom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followup_classroom_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("validation_mode", sa.String(length=16), nullable=False, server_default="real"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id", "owner_id"], ["courses.id", "courses.owner_id"], name="fk_improvement_cycles_course_owner", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_classroom_id", "owner_id"], ["classrooms.id", "classrooms.owner_id"], name="fk_improvement_cycles_baseline_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["followup_classroom_id", "owner_id"], ["classrooms.id", "classrooms.owner_id"], name="fk_improvement_cycles_followup_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_improvement_cycles_id_owner"),
    )
    for column in ("owner_id", "course_id", "baseline_classroom_id", "followup_classroom_id", "status"):
        op.create_index(f"ix_improvement_cycles_{column}", "improvement_cycles", [column])

    op.create_table(
        "improvement_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_conclusion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_text", sa.Text(), nullable=False),
        sa.Column("success_criterion", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("progress", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("priority BETWEEN 1 AND 3", name="ck_improvement_action_priority"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id", "owner_id"], ["improvement_cycles.id", "improvement_cycles.owner_id"], name="fk_improvement_actions_cycle_owner", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_actions_conclusion_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_improvement_actions_id_owner"),
        sa.UniqueConstraint("cycle_id", "source_conclusion_id", name="uq_improvement_action_source"),
    )
    for column in ("owner_id", "cycle_id", "source_conclusion_id"):
        op.create_index(f"ix_improvement_actions_{column}", "improvement_actions", [column])

    op.create_table(
        "improvement_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_conclusion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("followup_conclusion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_outcome", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("baseline_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("followup_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reviewed_summary", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("skill", sa.String(length=64), nullable=False, server_default="evidence-comparison"),
        sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default="comparison-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id", "owner_id"], ["improvement_cycles.id", "improvement_cycles.owner_id"], name="fk_improvement_comparisons_cycle_owner", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id", "owner_id"], ["improvement_actions.id", "improvement_actions.owner_id"], name="fk_improvement_comparisons_action_owner", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_comparisons_baseline_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["followup_conclusion_id", "owner_id"], ["analysis_conclusions.id", "analysis_conclusions.owner_id"], name="fk_improvement_comparisons_followup_owner", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_improvement_comparisons_id_owner"),
        sa.UniqueConstraint("cycle_id", "action_id", name="uq_improvement_comparison_action"),
    )
    for column in ("owner_id", "cycle_id", "action_id", "baseline_conclusion_id", "review_status", "trace_id"):
        op.create_index(f"ix_improvement_comparisons_{column}", "improvement_comparisons", [column])


def downgrade() -> None:
    op.drop_table("improvement_comparisons")
    op.drop_table("improvement_actions")
    op.drop_table("improvement_cycles")

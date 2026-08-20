"""Store the full extracted-audio duration for transcript playback.

Revision ID: 8c7a4e9d2f11
Revises: 0b5123afcf23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c7a4e9d2f11"
down_revision: str | None = "0b5123afcf23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_tasks",
        sa.Column("transcript_duration_ms", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_tasks_transcript_duration_nonnegative",
        "processing_tasks",
        "transcript_duration_ms IS NULL OR transcript_duration_ms >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tasks_transcript_duration_nonnegative",
        "processing_tasks",
        type_="check",
    )
    op.drop_column("processing_tasks", "transcript_duration_ms")

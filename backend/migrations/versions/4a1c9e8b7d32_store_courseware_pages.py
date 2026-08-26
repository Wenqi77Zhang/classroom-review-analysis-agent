"""Store page-aligned courseware evidence.

Revision ID: 4a1c9e8b7d32
Revises: 8c7a4e9d2f11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4a1c9e8b7d32"
down_revision: str | None = "8c7a4e9d2f11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courseware_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("page_no >= 1", name="ck_courseware_page_positive"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_courseware_page_text_nonempty"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_id", "owner_id"],
            ["processing_tasks.id", "processing_tasks.owner_id"],
            name="fk_courseware_pages_task_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id", "owner_id"],
            ["assets.id", "assets.owner_id"],
            name="fk_courseware_pages_asset_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_courseware_pages_id_owner"),
        sa.UniqueConstraint("task_id", "asset_id", "page_no", name="uq_courseware_task_asset_page"),
    )
    op.create_index("ix_courseware_pages_owner_id", "courseware_pages", ["owner_id"])
    op.create_index("ix_courseware_pages_task_id", "courseware_pages", ["task_id"])
    op.create_index("ix_courseware_pages_asset_id", "courseware_pages", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_courseware_pages_asset_id", table_name="courseware_pages")
    op.drop_index("ix_courseware_pages_task_id", table_name="courseware_pages")
    op.drop_index("ix_courseware_pages_owner_id", table_name="courseware_pages")
    op.drop_table("courseware_pages")

"""Add revocable teacher session version.

Revision ID: a6f4c2d9e013
Revises: 9d2e6f4a8b10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6f4c2d9e013"
down_revision: str | None = "9d2e6f4a8b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_version")

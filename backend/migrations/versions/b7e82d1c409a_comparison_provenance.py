"""Record actual comparison model and reviewed source snapshot fingerprint.

Revision ID: b7e82d1c409a
Revises: a6f4c2d9e013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e82d1c409a"
down_revision: str | None = "a6f4c2d9e013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("improvement_comparisons", sa.Column("model_name", sa.String(128), nullable=True))
    op.add_column("improvement_comparisons", sa.Column("source_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("improvement_comparisons", "source_fingerprint")
    op.drop_column("improvement_comparisons", "model_name")

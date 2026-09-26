"""Add explicit teacher attestations for teaching-effect evidence.

Revision ID: c8f91a2d7e04
Revises: b7e82d1c409a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8f91a2d7e04"
down_revision: str | None = "b7e82d1c409a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "improvement_cycles",
        sa.Column(
            "independent_delivery_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "improvement_cycles",
        sa.Column(
            "intervention_executed_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "improvement_cycles",
        sa.Column("effect_evidence_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("improvement_cycles", "effect_evidence_note")
    op.drop_column("improvement_cycles", "intervention_executed_confirmed")
    op.drop_column("improvement_cycles", "independent_delivery_confirmed")

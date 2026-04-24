"""Add completed_at column to investigation_requests.

InvestigationResult.completed_at was defined in the domain contract but was
never stored.  This migration adds the column with a server-side default of
now() so that existing rows (if any) get a sensible fallback value and the
column is always non-null going forward.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_requests",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("investigation_requests", "completed_at")

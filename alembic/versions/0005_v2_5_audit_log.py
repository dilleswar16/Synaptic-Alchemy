"""V2.5 audit log: add approved_by and approved_at to investigation_requests.

Revision ID: 0005
Revises: 05ac79937721
Create Date: 2026-05-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "05ac79937721"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_requests",
        sa.Column("approved_by", sa.String(255), nullable=True, server_default=None),
    )
    op.add_column(
        "investigation_requests",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True, server_default=None),
    )


def downgrade() -> None:
    op.drop_column("investigation_requests", "approved_at")
    op.drop_column("investigation_requests", "approved_by")

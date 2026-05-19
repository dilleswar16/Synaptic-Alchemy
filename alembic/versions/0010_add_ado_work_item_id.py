"""add ado_work_item_id to investigation_requests

Revision ID: 0010_add_ado_work_item_id
Revises: 0009_v38_corvin_chat_history
Create Date: 2026-05-19
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0010_add_ado_work_item_id"
down_revision = "21871e3fb4d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_requests",
        sa.Column("ado_work_item_id", sa.String(50), nullable=True, server_default=None),
    )


def downgrade() -> None:
    op.drop_column("investigation_requests", "ado_work_item_id")

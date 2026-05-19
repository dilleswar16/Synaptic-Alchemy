"""add tool_results to corvin_messages

Revision ID: 0011_add_tool_results_to_corvin_messages
Revises: 0010_add_ado_work_item_id
Create Date: 2026-05-19
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_add_tool_results_to_corvin_messages"
down_revision = "0010_add_ado_work_item_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use JSONB on Postgres, JSON on SQLite (same pattern as existing migrations)
    op.add_column(
        "corvin_messages",
        sa.Column(
            "tool_results",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("corvin_messages", "tool_results")

"""v38 corvin chat history (sessions and messages)

Revision ID: 0009_v38_corvin_chat_history
Revises: 0008_v37_predictive_alerts
Create Date: 2026-05-16
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_v38_corvin_chat_history"
down_revision = "0008_v37_predictive_alerts"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Create sessions table
    op.create_table(
        "corvin_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, server_default="New conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Create messages table
    op.create_table(
        "corvin_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("corvin_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("thinking", sa.Text(), nullable=True),
        # Using postgresql.JSONB here as this is the postgres-specific migration script
        # On SQLite, the backend skips alembic and uses create_all()
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("corvin_messages")
    op.drop_table("corvin_sessions")

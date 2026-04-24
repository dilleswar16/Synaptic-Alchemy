"""create_initial_tables

Revision ID: 0001
Revises:
Create Date: 2026-04-04

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trigger_source", sa.String(50), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "rca_outputs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("investigation_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("root_cause", sa.Text, nullable=False),
        sa.Column("contributing_factors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("evidence_references", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "fix_strategy_outputs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("investigation_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("actions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("fix_strategy_outputs")
    op.drop_table("rca_outputs")
    op.drop_table("investigation_requests")

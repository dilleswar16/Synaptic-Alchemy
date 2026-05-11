"""add confidence_reasoning to rca_outputs

Revision ID: 0007_confidence_reasoning
Revises: 0006_v3_post_mortems
Create Date: 2026-05-09

Adds confidence_reasoning (Text, NOT NULL, default '') to rca_outputs.
Existing rows are backfilled with an empty string.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_confidence_reasoning"
down_revision = "0006_v3_post_mortems"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rca_outputs",
        sa.Column("confidence_reasoning", sa.Text, nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("rca_outputs", "confidence_reasoning")

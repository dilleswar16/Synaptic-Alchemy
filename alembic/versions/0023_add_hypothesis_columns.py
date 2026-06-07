"""Add hypotheses_json and selected_hypothesis_id to investigation_requests.

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-04

Feature 8 — Root Cause Debate Mode.
Both columns are nullable so existing rows degrade gracefully to empty state.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hypotheses_json stores list[RCAHypothesis] serialised as JSON.
    # Null = investigation was completed before Feature 8 was enabled.
    op.add_column(
        "investigation_requests",
        sa.Column("hypotheses_json", sa.JSON(), nullable=True, server_default=None),
    )
    # selected_hypothesis_id is "h1" | "h2" | "h3" | None.
    # Null = SRE has not yet selected a winning hypothesis (or feature disabled).
    op.add_column(
        "investigation_requests",
        sa.Column(
            "selected_hypothesis_id",
            sa.String(10),
            nullable=True,
            server_default=None,
        ),
    )


def downgrade() -> None:
    op.drop_column("investigation_requests", "selected_hypothesis_id")
    op.drop_column("investigation_requests", "hypotheses_json")

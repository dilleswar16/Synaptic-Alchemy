"""Add predictive_penalties table for the learning feedback loop.

Revision ID: 0020_predictive_penalties
Revises: 0019
Create Date: 2025-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_predictive_penalties"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictive_penalties",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service_name", sa.String(255), nullable=False, index=True),
        sa.Column("environment", sa.String(50), nullable=False, server_default="production"),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("penalty_type", sa.String(30), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False, index=True),
        sa.Column("predictive_alert_id", sa.String(36), nullable=True),
        sa.Column("pattern_description", sa.Text(), nullable=False),
        sa.Column("root_cause_fingerprint", sa.Text(), nullable=False),
        sa.Column("suggested_threshold_adjustment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("predictive_penalties")

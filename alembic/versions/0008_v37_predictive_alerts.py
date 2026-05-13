"""v37 add predictive_alerts table

Revision ID: 0008_v37_predictive_alerts
Revises: 0007
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_v37_predictive_alerts"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictive_alerts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("signal_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("estimated_breach_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_request_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("investigation_request_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("predictive_alerts")
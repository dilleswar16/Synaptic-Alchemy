"""Add validation_automation_policies table for AI-triggered user journeys.

Revision ID: 0019
Revises: 0018
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_automation_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("min_confidence_pct", sa.Float(), nullable=False, server_default="70.0"),
        sa.Column(
            "validation_definition_id",
            sa.String(36),
            sa.ForeignKey("validation_definitions.id"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_vap_service_alert",
        "validation_automation_policies",
        ["service_name", "alert_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_vap_service_alert", table_name="validation_automation_policies")
    op.drop_table("validation_automation_policies")

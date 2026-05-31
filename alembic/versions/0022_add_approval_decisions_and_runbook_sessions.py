"""Add approval_decisions and runbook_sessions tables.

Revision ID: 0022
Revises: 0021
Create Date: 2025-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_type", sa.String(50), nullable=False),  # correlation_suppression | scaling_action
        sa.Column("reference_id", sa.String(255), nullable=False),  # group_id or service_name
        sa.Column("action", sa.String(20), nullable=False),  # approve | reject
        sa.Column("action_detail", sa.String(255), nullable=True),  # e.g. scale_up_replicas
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_approval_decisions_reference", "approval_decisions", ["decision_type", "reference_id"])

    op.create_table(
        "runbook_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="drafting"),
        sa.Column("messages_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("current_draft_content", sa.Text(), nullable=True),
        sa.Column("current_draft_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_runbook_sessions_request", "runbook_sessions", ["request_id"])

    # Add suppression_status to predictive_alerts for correlation approvals
    op.add_column("predictive_alerts", sa.Column("suppression_status", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("predictive_alerts", "suppression_status")
    op.drop_index("ix_runbook_sessions_request", "runbook_sessions")
    op.drop_table("runbook_sessions")
    op.drop_index("ix_approval_decisions_reference", "approval_decisions")
    op.drop_table("approval_decisions")

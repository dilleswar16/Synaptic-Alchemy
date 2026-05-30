"""Add notification_contacts and outbound_connectors tables

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-01

Adds tables for:
- notification_contacts: who to alert and via which method (email/phone/teams)
- outbound_connectors: destinations for sending notifications (Teams webhook, ServiceNow, etc.)
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_contacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False, index=True),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),  # email|phone|teams
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("priority_filter", sa.String(20), nullable=False, server_default="all"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "outbound_connectors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False, index=True),
        sa.Column("connector_type", sa.String(50), nullable=False),  # teams_webhook|servicenow|email|pagerduty
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("config_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_status", sa.String(20), nullable=True),
        sa.Column("test_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("outbound_connectors")
    op.drop_table("notification_contacts")

"""add application panel tables

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# Use JSONB on Postgres, JSON elsewhere
_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("team_name", sa.String(255), nullable=True),
        sa.Column("environment_default", sa.String(50), nullable=False, server_default="dev"),
        sa.Column("topology_json", _JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "application_services",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("namespace", sa.String(255), nullable=True),
        sa.Column("tier", sa.String(50), nullable=True),
        sa.Column("dependencies", _JSONB, nullable=False, server_default="[]"),
        sa.Column("metadata_json", _JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_application_services_app_id", "application_services", ["application_id"])

    op.create_table(
        "log_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("config_json", _JSONB, nullable=False, server_default="{}"),
        sa.Column("credential_type", sa.String(30), nullable=False, server_default="env_var"),
        sa.Column("credential_ref", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_status", sa.String(20), nullable=True),
        sa.Column("test_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_log_sources_app_id", "log_sources", ["application_id"])

    op.create_table(
        "slo_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("sli_type", sa.String(30), nullable=False, server_default="availability"),
        sa.Column("target_pct", sa.Float, nullable=False, server_default="99.9"),
        sa.Column("time_window_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("latency_threshold_ms", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slo_configs_app_id", "slo_configs", ["application_id"])


def downgrade() -> None:
    op.drop_table("slo_configs")
    op.drop_table("log_sources")
    op.drop_table("application_services")
    op.drop_table("applications")

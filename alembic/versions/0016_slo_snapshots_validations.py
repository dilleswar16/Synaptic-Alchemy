"""Add slo_snapshots, validation_definitions, validation_runs tables.

Revision ID: 0016
Revises: 0015
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "slo_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slo_config_id", sa.Integer(), sa.ForeignKey("slo_configs.id"), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("sli_type", sa.String(30), nullable=False),
        sa.Column("target_pct", sa.Float(), nullable=False),
        sa.Column("measured_pct", sa.Float(), nullable=True),
        sa.Column("error_budget_pct", sa.Float(), nullable=True),
        sa.Column("burn_rate", sa.Float(), nullable=True),
        sa.Column("is_compliant", sa.Boolean(), nullable=True),
        sa.Column("data_source", sa.String(30), nullable=False, server_default="simulated"),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_json", _JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_slo_snapshots_slo_config_id", "slo_snapshots", ["slo_config_id"])
    op.create_index("ix_slo_snapshots_application_id", "slo_snapshots", ["application_id"])
    op.create_index("ix_slo_snapshots_sampled_at", "slo_snapshots", ["sampled_at"])

    op.create_table(
        "validation_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("validation_type", sa.String(50), nullable=False, server_default="health_check"),
        sa.Column("config_json", _JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_definitions_application_id", "validation_definitions", ["application_id"])

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("definition_id", sa.String(36), sa.ForeignKey("validation_definitions.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_json", _JSONB, nullable=False, server_default="{}"),
        sa.Column("triggered_by", sa.String(100), nullable=True),
    )
    op.create_index("ix_validation_runs_definition_id", "validation_runs", ["definition_id"])


def downgrade() -> None:
    op.drop_table("validation_runs")
    op.drop_table("validation_definitions")
    op.drop_table("slo_snapshots")

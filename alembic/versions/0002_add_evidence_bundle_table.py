"""add_evidence_bundle_table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-04

Adds the evidence_bundles table to persist EvidenceBundle domain objects.
Existing tables (investigation_requests, rca_outputs, fix_strategy_outputs)
are not modified.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_bundles",
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("investigation_requests.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "elastic_logs",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "elastic_metrics",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "log_analytics_apim",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "aks_context",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "azure_activity_changes",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("evidence_bundles")

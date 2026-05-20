"""add container_resource_metrics, container_inventory, node_inventory, network_metrics to evidence_bundles

Revision ID: 0012_add_kube_metrics_columns
Revises: 0011_add_tool_results_to_corvin_messages
Create Date: 2026-05-20
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

try:
    from sqlalchemy.dialects.postgresql import JSONB
    _JSON_TYPE = JSONB
except ImportError:
    _JSON_TYPE = sa.JSON

revision = "0012_add_kube_metrics_columns"
down_revision = "0011_add_tool_results_to_corvin_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use sa.JSON so it works on both SQLite (local dev) and Postgres (production).
    op.add_column("evidence_bundles", sa.Column("container_resource_metrics", sa.JSON, nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("container_inventory", sa.JSON, nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("node_inventory", sa.JSON, nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("network_metrics", sa.JSON, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("evidence_bundles", "network_metrics")
    op.drop_column("evidence_bundles", "node_inventory")
    op.drop_column("evidence_bundles", "container_inventory")
    op.drop_column("evidence_bundles", "container_resource_metrics")

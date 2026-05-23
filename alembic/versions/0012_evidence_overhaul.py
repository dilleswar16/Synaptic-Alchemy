"""add evidence overhaul columns

Revision ID: 0012
Revises: 0011_add_tool_results_to_corvin_messages
Create Date: 2026-05-28

Adds 4 new evidence fields to evidence_bundles:
  - pod_restarts
  - oom_kill_events
  - autoscaler_events
  - health_probe_failures
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_evidence_overhaul"
down_revision = "0011_add_tool_results_to_corvin_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_bundles", sa.Column("pod_restarts", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("oom_kill_events", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("autoscaler_events", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("evidence_bundles", sa.Column("health_probe_failures", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("evidence_bundles", "health_probe_failures")
    op.drop_column("evidence_bundles", "autoscaler_events")
    op.drop_column("evidence_bundles", "oom_kill_events")
    op.drop_column("evidence_bundles", "pod_restarts")

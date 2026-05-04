"""v3 add post_mortems table

Revision ID: 0006_v3_post_mortems
Revises: 0005_v2_5_audit_log
Create Date: 2026-05-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "0006_v3_post_mortems"
down_revision = "0005_v2_5_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_mortems",
        sa.Column("request_id", sa.String(36), sa.ForeignKey("investigation_requests.id"), primary_key=True),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(100), nullable=False),
        sa.Column("incident_summary", sa.Text, nullable=False),
        sa.Column("detection_timeline", sa.Text, nullable=False),
        sa.Column("investigation_findings", sa.Text, nullable=False),
        sa.Column("actions_taken", sa.Text, nullable=False),
        sa.Column("prevention_recommendations", sa.Text, nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("markdown", sa.Text, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("post_mortems")

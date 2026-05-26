"""add predictive alert extra fields

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013_add_acknowledged_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictive_alerts", sa.Column("confidence_pct", sa.Float(), nullable=False, server_default="0"))
    op.add_column("predictive_alerts", sa.Column("related_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("predictive_alerts", sa.Column("blast_radius_users", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("predictive_alerts", sa.Column("blast_radius_requests", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("predictive_alerts", sa.Column("change_correlation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("predictive_alerts", "change_correlation")
    op.drop_column("predictive_alerts", "blast_radius_requests")
    op.drop_column("predictive_alerts", "blast_radius_users")
    op.drop_column("predictive_alerts", "related_count")
    op.drop_column("predictive_alerts", "confidence_pct")

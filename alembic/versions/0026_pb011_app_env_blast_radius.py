"""PB-011: add blast_radius_users_per_replica, blast_radius_revenue_per_user_per_min to application_environments

Revision ID: 0026_pb011_app_env_blast_radius
Revises: 0025_pb010_app_env_locale_currency
Create Date: 2026-06-11
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0026_pb011_app_env_blast_radius"
down_revision = "0025_pb010_app_env_locale_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("application_environments", sa.Column("blast_radius_users_per_replica", sa.Integer(), nullable=True, server_default=None))
    op.add_column("application_environments", sa.Column("blast_radius_revenue_per_user_per_min", sa.Numeric(12, 6), nullable=True, server_default=None))


def downgrade() -> None:
    op.drop_column("application_environments", "blast_radius_revenue_per_user_per_min")
    op.drop_column("application_environments", "blast_radius_users_per_replica")

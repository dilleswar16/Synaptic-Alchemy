"""add scoring/environment config columns to applications

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("scoring_config_json", sa.JSON(), nullable=True, server_default=None),
    )
    op.add_column(
        "applications",
        sa.Column("environment_config_json", sa.JSON(), nullable=True, server_default=None),
    )


def downgrade() -> None:
    op.drop_column("applications", "environment_config_json")
    op.drop_column("applications", "scoring_config_json")

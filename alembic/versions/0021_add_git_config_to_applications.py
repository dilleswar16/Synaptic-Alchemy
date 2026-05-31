"""Add git repository config fields to applications table.

Revision ID: 0021
Revises: 0020_predictive_penalties
Create Date: 2025-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_add_git_config_to_applications"
down_revision = "0020_predictive_penalties"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("git_provider", sa.String(30), nullable=True))
    op.add_column("applications", sa.Column("git_repo_url", sa.String(500), nullable=True))
    op.add_column("applications", sa.Column("git_branch", sa.String(255), nullable=True))
    op.add_column("applications", sa.Column("git_token_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "git_token_encrypted")
    op.drop_column("applications", "git_branch")
    op.drop_column("applications", "git_repo_url")
    op.drop_column("applications", "git_provider")

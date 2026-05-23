"""add wiki_url and sharepoint_url columns

Revision ID: 0012
Revises: 0011_add_tool_results_to_corvin_messages
Create Date: 2025-06-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012"
down_revision = "0011_add_tool_results_to_corvin_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigation_requests",
        sa.Column("wiki_url", sa.String(1024), nullable=True),
    )
    op.add_column(
        "investigation_requests",
        sa.Column("sharepoint_url", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("investigation_requests", "sharepoint_url")
    op.drop_column("investigation_requests", "wiki_url")

"""add k8s_app_label to application_services

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-31

Adds `k8s_app_label` to `application_services` so each service can record the
Kubernetes deployment label used in the cluster (e.g. "chad-fundapis") separately
from the logical service name ("fundapis").  This replaces the hardcoded
`_AKS_NAME_MAP` dict that previously lived in the investigations topology route.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_services",
        sa.Column("k8s_app_label", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_services", "k8s_app_label")

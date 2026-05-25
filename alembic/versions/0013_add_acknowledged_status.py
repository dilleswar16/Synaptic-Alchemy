"""add acknowledged status to approval_status constraint

Revision ID: 0013_add_acknowledged_status
Revises: 0012_add_kube_metrics_columns, 0012_evidence_overhaul, 0012
Create Date: 2026-05-23
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0013_add_acknowledged_status"
down_revision = ("0012_add_kube_metrics_columns", "0012_evidence_overhaul", "0012")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE investigation_requests
        DROP CONSTRAINT IF EXISTS ck_investigation_requests_approval_status
        """
    )
    op.execute(
        """
        ALTER TABLE investigation_requests
        ADD CONSTRAINT ck_investigation_requests_approval_status
        CHECK (approval_status IN ('pending', 'approved', 'rejected', 'acknowledged', 'executed'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE investigation_requests
        DROP CONSTRAINT IF EXISTS ck_investigation_requests_approval_status
        """
    )
    op.execute(
        """
        ALTER TABLE investigation_requests
        ADD CONSTRAINT ck_investigation_requests_approval_status
        CHECK (approval_status IN ('pending', 'approved', 'rejected', 'executed'))
        """
    )

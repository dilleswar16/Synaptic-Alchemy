"""PB-015: add toolset_profile JSONB to applications

Revision ID: 0027_pb015_app_toolset_profile
Revises: 0026_pb011_app_env_blast_radius
Create Date: 2026-06-11
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

try:
    from sqlalchemy.dialects.postgresql import JSONB
    _JSON_TYPE = JSONB
except ImportError:
    _JSON_TYPE = sa.JSON

revision = "0027_pb015_app_toolset_profile"
down_revision = "0026_pb011_app_env_blast_radius"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("toolset_profile", _JSON_TYPE(), nullable=True, server_default=None))


def downgrade() -> None:
    op.drop_column("applications", "toolset_profile")

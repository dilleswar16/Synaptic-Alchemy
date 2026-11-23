"""weekly health review: a weekly digest can be marked as reviewed

Spec 31 (C3). The weekly digest (``intelligence_report``) is the weekly document of an application. Three nullable columns record that an application admin went through it with the team:
when, who and an optional note. Nothing is backfilled: earlier digests read as not reviewed.

Revision ID: a1d5c9e3f7b2
Revises: f4a8c2e6b0d7
Create Date: 2026-11-23 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none

revision: str = 'a1d5c9e3f7b2'
down_revision: str | None = 'f4a8c2e6b0d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "intelligence_report"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("reviewed_at", sa.DateTime(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("reviewed_by_user_principal_name", sa.String(320), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("review_note_text", sa.String(2000), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for column in ("review_note_text", "reviewed_by_user_principal_name", "reviewed_at"):
        op.drop_column(TABLE, column, schema=SCHEMA)

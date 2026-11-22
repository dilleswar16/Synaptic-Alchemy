"""application operating notes: the team's guidance for the AI, with who and when it last changed

Three nullable columns on ``application``: the notes (``Text``, which is NVARCHAR(max) on SQL Server, so every length the
APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS setting allows fits), when they were last changed and by whom. There is nothing to backfill:
existing applications have no notes. Adding a nullable column is an ordinary ALTER TABLE on SQLite and SQL Server, so no batch rebuild is needed.

Revision ID: f1b9d3a5c7e2
Revises: e4c8a1d7b2f6
Create Date: 2026-11-21 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import keigan.entities.base_entity
from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none

revision: str = 'f1b9d3a5c7e2'
down_revision: str | None = 'e4c8a1d7b2f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "application"
NOTES_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("operating_notes_text", sa.Text()),
    ("operating_notes_updated_at", keigan.entities.base_entity.UtcDateTime(timezone=True)),
    ("operating_notes_updated_by_user_principal_name", sa.String(length=320)),
)


def upgrade() -> None:
    for column_name, column_type in NOTES_COLUMNS:
        op.add_column(TABLE, sa.Column(column_name, column_type, nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for column_name, _ in reversed(NOTES_COLUMNS):
        op.drop_column(TABLE, column_name, schema=SCHEMA)

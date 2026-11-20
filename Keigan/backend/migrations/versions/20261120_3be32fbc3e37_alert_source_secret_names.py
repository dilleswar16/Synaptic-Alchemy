"""alert source secret names

Names of the plaintext webhook secrets in the secret store (V1b). The secret itself is the HMAC signing key, so it can
no longer be derived from the stored hash. Both columns are nullable: sources created before this revision keep
working with their token (checked by hash) and gain signature support when their secret is rotated.

Revision ID: 3be32fbc3e37
Revises: 1fa7018ae4d6
Create Date: 2026-11-20 17:11:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = '3be32fbc3e37'
down_revision: str | None = '1fa7018ae4d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN works on SQLite and SQL Server. Batch mode is avoided on purpose: on SQLite it rebuilds alert_source,
    # and with foreign keys enabled dropping the old table would cascade-delete every alert_event.
    op.add_column("alert_source", sa.Column("webhook_secret_name", sa.String(length=200), nullable=True), schema=SCHEMA)
    op.add_column("alert_source", sa.Column("previous_webhook_secret_name", sa.String(length=200), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("alert_source", "previous_webhook_secret_name", schema=SCHEMA)
    op.drop_column("alert_source", "webhook_secret_name", schema=SCHEMA)

"""alert open fingerprint unique

At most one open (firing) alert per application and fingerprint, guaranteed by the database (H3), so two pods that
receive repeats of the same alert at the same moment cannot both create it.

Existing databases may already hold duplicates (the old guard was an in-process lock). Before the index is created,
every firing alert that has a newer firing twin is marked resolved at its last sighting; the newest one stays open.

Revision ID: 89afa8e088ba
Revises: 94692c828bd3
Create Date: 2026-11-20 17:10:36.684163
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = '89afa8e088ba'
down_revision: str | None = '94692c828bd3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPEN_ALERT_FILTER = "alert_status = 'firing'"


def resolve_older_duplicate_open_alerts() -> None:
    """Portable SQL (SQLite and SQL Server, also in offline mode): no Python-side reads."""
    alert = sa.table(
        "alert", sa.column("alert_id"), sa.column("application_id"), sa.column("alert_fingerprint"), sa.column("alert_status", sa.String), sa.column("last_seen_at"), sa.column("resolved_at"), schema=SCHEMA
    )
    newer_alert = alert.alias("newer_alert")
    has_newer_open_twin = sa.exists().where(
        sa.and_(
            newer_alert.c.application_id == alert.c.application_id,
            newer_alert.c.alert_fingerprint == alert.c.alert_fingerprint,
            newer_alert.c.alert_status == "firing",
            sa.or_(
                newer_alert.c.last_seen_at > alert.c.last_seen_at,
                sa.and_(newer_alert.c.last_seen_at == alert.c.last_seen_at, newer_alert.c.alert_id > alert.c.alert_id),
            ),
        )
    )
    op.execute(alert.update().where(alert.c.alert_status == "firing", has_newer_open_twin).values(alert_status="resolved", resolved_at=alert.c.last_seen_at))


def upgrade() -> None:
    resolve_older_duplicate_open_alerts()
    op.create_index(
        "uq_alert_open_fingerprint", "alert", ["application_id", "alert_fingerprint"], unique=True, schema=SCHEMA,
        mssql_where=sa.text(OPEN_ALERT_FILTER), postgresql_where=sa.text(OPEN_ALERT_FILTER), sqlite_where=sa.text(OPEN_ALERT_FILTER),
    )


def downgrade() -> None:
    op.drop_index("uq_alert_open_fingerprint", table_name="alert", schema=SCHEMA)

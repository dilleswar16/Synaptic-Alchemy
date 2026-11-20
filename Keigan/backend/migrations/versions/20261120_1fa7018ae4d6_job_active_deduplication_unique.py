"""job active deduplication unique

At most one active (queued or running) background job per deduplication key, guaranteed by the database (H4).
Finished jobs keep their key for history.

Existing databases may already hold duplicates (the old guard was check-then-insert). Before the index is created,
every active job that has a better active twin is cancelled. The twin that stays is a running job in preference to a
queued one, then the newest.

Revision ID: 1fa7018ae4d6
Revises: 89afa8e088ba
Create Date: 2026-11-20 17:10:48.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = '1fa7018ae4d6'
down_revision: str | None = '89afa8e088ba'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_JOB_FILTER = "deduplication_key IS NOT NULL AND job_status IN ('queued', 'running')"


def cancel_duplicate_active_jobs() -> None:
    """Portable SQL (SQLite and SQL Server, also in offline mode): no Python-side reads."""
    job = sa.table(
        "background_job", sa.column("background_job_id"), sa.column("deduplication_key"), sa.column("job_status", sa.String), sa.column("created_at"), sa.column("finished_at"), sa.column("last_error_message", sa.String), schema=SCHEMA
    )
    better_job = job.alias("better_job")
    has_better_active_twin = sa.exists().where(
        sa.and_(
            better_job.c.deduplication_key == job.c.deduplication_key,
            better_job.c.job_status.in_(("queued", "running")),
            sa.or_(
                sa.and_(better_job.c.job_status == "running", job.c.job_status == "queued"),
                sa.and_(
                    better_job.c.job_status == job.c.job_status,
                    sa.or_(
                        better_job.c.created_at > job.c.created_at,
                        sa.and_(better_job.c.created_at == job.c.created_at, better_job.c.background_job_id > job.c.background_job_id),
                    ),
                ),
            ),
        )
    )
    op.execute(
        job.update().where(job.c.deduplication_key.is_not(None), job.c.job_status.in_(("queued", "running")), has_better_active_twin).values(
            job_status="cancelled", finished_at=sa.func.current_timestamp(), last_error_message="Cancelled by a database migration: another active job already had this deduplication key."
        )
    )


def upgrade() -> None:
    cancel_duplicate_active_jobs()
    op.create_index(
        "uq_background_job_active_deduplication_key", "background_job", ["deduplication_key"], unique=True, schema=SCHEMA,
        mssql_where=sa.text(ACTIVE_JOB_FILTER), postgresql_where=sa.text(ACTIVE_JOB_FILTER), sqlite_where=sa.text(ACTIVE_JOB_FILTER),
    )


def downgrade() -> None:
    op.drop_index("uq_background_job_active_deduplication_key", table_name="background_job", schema=SCHEMA)

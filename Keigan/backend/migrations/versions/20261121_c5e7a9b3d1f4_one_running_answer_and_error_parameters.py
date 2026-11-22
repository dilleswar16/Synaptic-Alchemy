"""one running answer per conversation, and the parameters of a failed answer's error

At most one ``running`` Ask Keigan answer per conversation, guaranteed by the database: the in-process registry only knows its own pod, so two pods could
both start an answer in the same conversation. Finished runs keep their history. The application maps a violation of this index to ``answer_in_progress``.

``chat_answer_run.error_parameters_json`` keeps the low-sensitivity values the error message was written from (the failed step, a limit, a retry delay), so a
reload of the run words the same message as the live stream did. Nullable: a run that did not fail has none.

Existing databases may already hold two running runs in one conversation (the old guard was check-then-insert). Before the index is created, every running
run that has a newer running twin in its conversation is ended as ``failed`` with the catalogue code ``answer_interrupted``, as the stale-run sweep ends a
run nothing works on. The newest run stays running.

Revision ID: c5e7a9b3d1f4
Revises: a7c3e9f1b5d2
Create Date: 2026-11-21 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'c5e7a9b3d1f4'
down_revision: str | None = 'a7c3e9f1b5d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_chat_answer_run_one_running_per_conversation"
RUNNING_RUN_FILTER = "run_status = 'running'"


def end_older_duplicate_running_runs() -> None:
    """Portable SQL (SQLite and SQL Server, also in offline mode): no Python-side reads."""
    run = sa.table(
        "chat_answer_run", sa.column("answer_run_id"), sa.column("conversation_id"), sa.column("run_status", sa.String), sa.column("stop_reason", sa.String), sa.column("error_code", sa.String),
        sa.column("started_at"), sa.column("completed_at"), schema=SCHEMA,
    )
    newer_run = run.alias("newer_run")
    has_newer_running_twin = sa.exists().where(
        sa.and_(
            newer_run.c.conversation_id == run.c.conversation_id,
            newer_run.c.run_status == "running",
            sa.or_(
                newer_run.c.started_at > run.c.started_at,
                sa.and_(newer_run.c.started_at == run.c.started_at, newer_run.c.answer_run_id > run.c.answer_run_id),
            ),
        )
    )
    op.execute(
        run.update().where(run.c.run_status == "running", has_newer_running_twin).values(
            run_status="failed", stop_reason="failed", error_code="answer_interrupted", completed_at=sa.func.current_timestamp()
        )
    )


def upgrade() -> None:
    op.add_column("chat_answer_run", sa.Column("error_parameters_json", sa.JSON(), nullable=True), schema=SCHEMA)
    end_older_duplicate_running_runs()
    op.create_index(
        INDEX_NAME, "chat_answer_run", ["conversation_id"], unique=True, schema=SCHEMA,
        mssql_where=sa.text(RUNNING_RUN_FILTER), postgresql_where=sa.text(RUNNING_RUN_FILTER), sqlite_where=sa.text(RUNNING_RUN_FILTER),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="chat_answer_run", schema=SCHEMA)
    op.drop_column("chat_answer_run", "error_parameters_json", schema=SCHEMA)

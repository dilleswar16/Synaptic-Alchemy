"""the applications an Ask Keigan answer used, so a person who loses access to one no longer sees the answer

``chat_answer_run.used_application_ids_json`` lists the applications whose data reached the model through the run's tool calls. It is kept up to date as each call
finishes. A person who can no longer read any one of them sees none of the run: not its answer, notes, citations, steps or step outputs.

Nullable: a run stored before this revision has no list. Every such run belongs to an investigation chat (the global chat did not use the Ask Keigan engine until now),
and an investigation chat is already guarded as a whole by the application of its investigation, so nothing is backfilled.

Revision ID: b8d4f2a6c0e3
Revises: c5e7a9b3d1f4
Create Date: 2026-11-22 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none

revision: str = 'b8d4f2a6c0e3'
down_revision: str | None = 'c5e7a9b3d1f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_answer_run", sa.Column("used_application_ids_json", sa.JSON(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("chat_answer_run", "used_application_ids_json", schema=SCHEMA)

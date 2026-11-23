"""incident keigan help: the resolver's answer to "how did Keigan's analysis help?"

One nullable column on the incident, with a CHECK on its four words. Nothing is backfilled: an incident resolved before this revision (or resolved in ServiceNow) has no answer, and the
metrics page counts only answered incidents.

Revision ID: a1b5c9d3e7f2
Revises: f7c3e9a1b5d2
Create Date: 2026-11-24 20:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none

revision: str = 'a1b5c9d3e7f2'
down_revision: str | None = 'f7c3e9a1b5d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

CONSTRAINT = "ck_incident_keigan_help_values"
ANSWERS = ("found_cause", "helped_partly", "did_not_help", "not_used")


def upgrade() -> None:
    op.add_column("incident", sa.Column("keigan_help", sa.String(20), nullable=True), schema=SCHEMA)
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot add a CHECK constraint without a rebuild that cascade-deletes rows: the new column was added without its check. Recreate the local demo database to get it.")
        return
    op.create_check_constraint(op.f(CONSTRAINT), "incident", sa.text(f"keigan_help IN ({', '.join(repr(answer) for answer in ANSWERS)})"), schema=SCHEMA)


def downgrade() -> None:
    if op.get_context().dialect.name != "sqlite":
        op.drop_constraint(op.f(CONSTRAINT), "incident", type_="check", schema=SCHEMA)
    op.drop_column("incident", "keigan_help", schema=SCHEMA)

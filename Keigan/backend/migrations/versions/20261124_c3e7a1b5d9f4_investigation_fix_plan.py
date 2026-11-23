"""investigation fix plan: the steps the synthesis recommends, as references to the analysts' checked steps

Spec 33 (E1, phase 2). A new investigation stores, next to its three hypotheses (whose ``proposed_fix_json`` now holds checked steps), the plan: an overview and the steps recommended, by reference.
Nothing is backfilled: earlier investigations have no plan and keep showing the fix text they were written with.

Revision ID: c3e7a1b5d9f4
Revises: a1d5c9e3f7b2
Create Date: 2026-11-24 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none

revision: str = 'c3e7a1b5d9f4'
down_revision: str | None = 'a1d5c9e3f7b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("investigation", sa.Column("fix_plan_json", sa.JSON(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("investigation", "fix_plan_json", schema=SCHEMA)

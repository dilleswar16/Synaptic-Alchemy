"""action item links: the task that tracks an item in ServiceNow (D1) and one more source, a finding about a runbook (C4)

Spec 29 (4.7) and spec 32. Five nullable columns say whether an item was sent to another system as a task and what that system last said about it; nothing is backfilled (an item
that was never sent has no value). The item source list gains ``runbook_health``, so that CHECK is replaced, and the new status column gets its own CHECK.

SQLite note: SQLite cannot add or replace a CHECK constraint without a rebuild that cascade-deletes rows, so on SQLite the columns are added without their check and the source check
is left alone (local demo databases are disposable; a new file gets the constraints from the entities).

Revision ID: d5a9b3e7c1f8
Revises: c3e7a1b5d9f4
Create Date: 2026-11-24 12:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'd5a9b3e7c1f8'
down_revision: str | None = 'c3e7a1b5d9f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

SOURCES_BEFORE_THIS_REVISION = ("postmortem", "manual", "error_budget_policy")
SOURCES_NOW = ("postmortem", "manual", "error_budget_policy", "runbook_health")
SOURCE_CONSTRAINT = "ck_action_item_item_source_kind_values"
SYNC_STATUS_CONSTRAINT = "ck_action_item_external_sync_status_values"
SYNC_STATUSES = ("pending", "linked", "failed")
NEW_COLUMNS = (
    ("external_system", sa.String(30)), ("external_record_identifier", sa.String(100)), ("external_status_text", sa.String(100)),
    ("external_synced_at", sa.DateTime()), ("external_sync_status", sa.String(20)),
)


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    for name, column_type in NEW_COLUMNS:
        op.add_column("action_item", sa.Column(name, column_type, nullable=True), schema=SCHEMA)
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot add or replace a CHECK constraint without a rebuild that cascade-deletes rows: the new columns were added without theirs and the source check was left as it is. Recreate the local demo database to get them.")
        return
    op.create_check_constraint(op.f(SYNC_STATUS_CONSTRAINT), "action_item", sa.text(f"external_sync_status IN ({_in_list(SYNC_STATUSES)})"), schema=SCHEMA)
    op.drop_constraint(op.f(SOURCE_CONSTRAINT), "action_item", type_="check", schema=SCHEMA)
    op.create_check_constraint(op.f(SOURCE_CONSTRAINT), "action_item", sa.text(f"item_source_kind IN ({_in_list(SOURCES_NOW)})"), schema=SCHEMA)


def downgrade() -> None:
    if op.get_context().dialect.name != "sqlite":
        op.execute(sa.text(f"DELETE FROM {SCHEMA_PREFIX}action_item WHERE item_source_kind NOT IN ({_in_list(SOURCES_BEFORE_THIS_REVISION)})"))
        op.drop_constraint(op.f(SOURCE_CONSTRAINT), "action_item", type_="check", schema=SCHEMA)
        op.create_check_constraint(op.f(SOURCE_CONSTRAINT), "action_item", sa.text(f"item_source_kind IN ({_in_list(SOURCES_BEFORE_THIS_REVISION)})"), schema=SCHEMA)
        op.drop_constraint(op.f(SYNC_STATUS_CONSTRAINT), "action_item", type_="check", schema=SCHEMA)
    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("action_item", name, schema=SCHEMA)

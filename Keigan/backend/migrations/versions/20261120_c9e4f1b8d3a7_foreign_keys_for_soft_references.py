"""foreign keys for soft references

Columns that name an application, incident, investigation, SLI or service had no foreign key on alerts, alert groups, SLOs,
SLO burn alerts, predictive signals, intelligence reports, notifications, Teams chats, external integrations, knowledge chunks,
discovered resources, service dependencies, the incident timeline, communications, postmortems and conversations (H12), so
deleting a parent left orphans behind. Each now has a real foreign key.

ON DELETE per key is CASCADE where the table has exactly one cascade path from the application, otherwise NO ACTION (SQL Server
rejects a second cascade path); Keigan then deletes or clears those rows itself (``reference_release`` and
``ApplicationService``). Audit events and AI usage records are kept as history on purpose and stay unkeyed.

Existing orphans are repaired BEFORE the keys are added, never by inventing a parent. Rule per key (``repair`` below):
- ``delete``: the row belongs to the missing parent (an alert of a deleted application, a timeline event of a deleted
  incident), so the row is deleted; rows that hang off it by an existing cascade key go with it.
- ``null``: the row only mentions the missing parent through an optional reference (an alert's service, a signal's SLI, a
  group's investigation), so the reference is set to NULL and the row stays. A NULL application id means "platform-wide" by
  design and is never touched.

SQLite note: SQLite cannot add a foreign key to an existing table without rebuilding it, and a rebuild with foreign keys on
cascade-deletes the child rows, so this revision repairs the data on SQLite but does not add the keys there. SQLite is only used
for local demo databases, which are disposable: delete the file (or run with AUTO_CREATE_SCHEMA on an empty one) and Keigan
creates every table with its keys from the entities. Azure SQL gets the keys through this revision (or the generated
database/azure_sql scripts).

Revision ID: c9e4f1b8d3a7
Revises: b7d2e9a4c6f1
Create Date: 2026-11-20 18:20:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, NamedTuple

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'c9e4f1b8d3a7'
down_revision: str | None = 'b7d2e9a4c6f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


class NewForeignKey(NamedTuple):
    table: str
    column: str
    referred_table: str
    referred_column: str
    ondelete: Literal["CASCADE"] | None  # None is NO ACTION
    repair: Literal["delete", "null"]


APPLICATION = ("application", "application_id")
SERVICE = ("monitored_service", "service_id")
INCIDENT = ("incident", "incident_id")
INVESTIGATION = ("investigation", "investigation_id")
SLI = ("service_level_indicator", "sli_id")

# Read by the schema drift test: SQLite databases built by `alembic upgrade head` lack exactly these keys (see the docstring).
FOREIGN_KEYS: tuple[NewForeignKey, ...] = (
    NewForeignKey("alert", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("alert", "service_id", *SERVICE, None, "null"),
    NewForeignKey("alert_event", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("alert_group", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("alert_group", "primary_service_id", *SERVICE, None, "null"),
    NewForeignKey("alert_group", "investigation_id", *INVESTIGATION, None, "null"),
    NewForeignKey("alert_group", "incident_id", *INCIDENT, None, "null"),
    NewForeignKey("service_level_indicator", "service_id", *SERVICE, None, "null"),
    NewForeignKey("service_level_objective", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("sli_measurement", "sli_id", *SLI, "CASCADE", "delete"),
    NewForeignKey("slo_burn_alert", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("predictive_signal", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("predictive_signal", "service_id", *SERVICE, None, "null"),
    NewForeignKey("predictive_signal", "sli_id", *SLI, None, "null"),
    NewForeignKey("intelligence_report", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("notification_delivery", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("notification_delivery", "incident_id", *INCIDENT, None, "null"),
    NewForeignKey("notification_delivery", "investigation_id", *INVESTIGATION, None, "null"),
    NewForeignKey("teams_incident_chat", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("teams_incident_chat", "incident_id", *INCIDENT, None, "delete"),
    NewForeignKey("external_integration", "application_id", *APPLICATION, "CASCADE", "delete"),
    NewForeignKey("discovered_resource", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("service_dependency", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("knowledge_document", "service_id", *SERVICE, None, "null"),
    NewForeignKey("knowledge_chunk", "application_id", *APPLICATION, None, "delete"),
    NewForeignKey("knowledge_chunk", "service_id", *SERVICE, None, "null"),
    NewForeignKey("investigation_evidence", "service_id", *SERVICE, None, "null"),
    NewForeignKey("investigation_timeline_event", "incident_id", *INCIDENT, "CASCADE", "delete"),
    NewForeignKey("investigation_timeline_event", "investigation_id", *INVESTIGATION, None, "delete"),
    NewForeignKey("incident_communication", "incident_id", *INCIDENT, "CASCADE", "delete"),
    NewForeignKey("incident_communication", "investigation_id", *INVESTIGATION, None, "delete"),
    NewForeignKey("postmortem_report", "incident_id", *INCIDENT, "CASCADE", "delete"),
    NewForeignKey("postmortem_report", "investigation_id", *INVESTIGATION, None, "delete"),
    NewForeignKey("conversation", "incident_id", *INCIDENT, None, "delete"),
    NewForeignKey("conversation", "investigation_id", *INVESTIGATION, None, "delete"),
)


def foreign_key_name(foreign_key: NewForeignKey) -> str:
    return f"fk_{foreign_key.table}_{foreign_key.column}_{foreign_key.referred_table}"  # the project's naming convention (entities/base_entity.py)


def repair_rows_naming_a_missing_parent(foreign_key: NewForeignKey) -> None:
    """Portable SQL (SQLite and SQL Server, also in offline mode): no Python-side reads."""
    child = sa.table(foreign_key.table, sa.column(foreign_key.column), schema=SCHEMA)
    parent = sa.table(foreign_key.referred_table, sa.column(foreign_key.referred_column), schema=SCHEMA)
    names_a_missing_parent = sa.and_(child.c[foreign_key.column].is_not(None), ~sa.exists().where(parent.c[foreign_key.referred_column] == child.c[foreign_key.column]))
    if foreign_key.repair == "delete":
        op.execute(child.delete().where(names_a_missing_parent))
    else:
        op.execute(child.update().where(names_a_missing_parent).values({foreign_key.column: None}))


def upgrade() -> None:
    # Deletions first: they may remove rows (and, through cascade keys, their children) that a later "null" repair would otherwise touch for nothing.
    for foreign_key in sorted(FOREIGN_KEYS, key=lambda candidate: candidate.repair != "delete"):
        repair_rows_naming_a_missing_parent(foreign_key)
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot add foreign keys to existing tables without a rebuild that cascade-deletes rows: the data was repaired but the keys were not added. Recreate the local demo database to get them.")
        return
    for foreign_key in FOREIGN_KEYS:
        op.create_foreign_key(
            op.f(foreign_key_name(foreign_key)), foreign_key.table, foreign_key.referred_table, [foreign_key.column], [foreign_key.referred_column],
            source_schema=SCHEMA, referent_schema=SCHEMA, ondelete=foreign_key.ondelete,
        )


def downgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        return  # the keys were never added; the repaired data stays repaired
    for foreign_key in reversed(FOREIGN_KEYS):
        op.drop_constraint(op.f(foreign_key_name(foreign_key)), foreign_key.table, type_="foreignkey", schema=SCHEMA)

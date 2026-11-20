"""ids json to association tables

Lists of ids of other Keigan rows (affected services, subscribed services, matched runbooks, scoped applications, topology
source documents) were JSON columns: nothing stopped a list from naming a deleted row, and "which incidents touch this
service?" needed a scan (H11). Each list becomes an association table ``(owner id, linked id, position)`` with a composite
primary key, real foreign keys and an index on the linked id.

The ids are copied BEFORE the JSON column is dropped, in list order (``position`` is the index in the old list, so gaps mean
a skipped id). Ids of rows that no longer exist and repeated ids are skipped. SQLite reads the list with ``json_each``, SQL
Server with ``OPENJSON``, so the same revision also renders valid T-SQL in offline mode (``alembic upgrade A:B --sql``).

Lists of opaque external ids (Azure resource ids of Log Analytics workspaces, user principal names, e-mail addresses) stay JSON.

SQLite note: columns are dropped with plain ``ALTER TABLE ... DROP COLUMN`` (SQLite 3.35+), never batch mode, because a table
rebuild with foreign keys on cascade-deletes child rows.

Revision ID: a3f5c0d1e2b4
Revises: 3be32fbc3e37
Create Date: 2026-11-20 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'a3f5c0d1e2b4'
down_revision: str | None = '3be32fbc3e37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class ListConversion(NamedTuple):
    """One JSON id list and the association table that replaces it. Ids are String(36) UUIDs everywhere."""

    owner_table: str
    owner_key: str
    json_column: str
    link_table: str
    linked_table: str
    linked_key: str
    linked_column: str


# Every association table cascades from its owner. The linked side is NO ACTION: the owner already cascades from an application,
# and SQL Server allows one cascade path per table; deleting the linked row first releases its rows in code.
CONVERSIONS = (
    ListConversion("incident", "incident_id", "affected_service_ids_json", "incident_affected_service", "monitored_service", "service_id", "service_id"),
    ListConversion("investigation", "investigation_id", "investigated_service_ids_json", "investigation_investigated_service", "monitored_service", "service_id", "service_id"),
    ListConversion("investigation", "investigation_id", "matched_runbook_ids_json", "investigation_matched_runbook", "runbook", "runbook_id", "runbook_id"),
    ListConversion("conversation", "conversation_id", "application_ids_json", "conversation_application", "application", "application_id", "application_id"),
    ListConversion("alert_group", "alert_group_id", "affected_service_ids_json", "alert_group_affected_service", "monitored_service", "service_id", "service_id"),
    ListConversion("maintenance_window", "maintenance_window_id", "applies_to_service_ids_json", "maintenance_window_applies_to_service", "monitored_service", "service_id", "service_id"),
    ListConversion("runbook", "runbook_id", "applies_to_service_ids_json", "runbook_applies_to_service", "monitored_service", "service_id", "service_id"),
    ListConversion("stakeholder", "stakeholder_id", "subscribed_service_ids_json", "stakeholder_subscribed_service", "monitored_service", "service_id", "service_id"),
    ListConversion("application_topology", "topology_id", "generated_from_document_ids_json", "topology_source_document", "knowledge_document", "knowledge_document_id", "knowledge_document_id"),
)
# conversation_application is the one table whose linked side may cascade: conversations are not part of any application's cascade tree.
LINKED_SIDE_CASCADES = {"conversation_application"}


def qualified(table: str) -> str:
    return f"{SCHEMA_PREFIX}{table}"


def foreign_key_name(table: str, column: str, referred_table: str) -> str:
    return f"fk_{table}_{column}_{referred_table}"  # the project's naming convention (entities/base_entity.py)


def create_association_table(conversion: ListConversion) -> None:
    link_table = conversion.link_table
    op.create_table(
        link_table,
        sa.Column(conversion.owner_key, sa.String(length=36), nullable=False),
        sa.Column(conversion.linked_column, sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint([conversion.owner_key], [f"{qualified(conversion.owner_table)}.{conversion.owner_key}"], name=op.f(foreign_key_name(link_table, conversion.owner_key, conversion.owner_table)), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            [conversion.linked_column], [f"{qualified(conversion.linked_table)}.{conversion.linked_key}"], name=op.f(foreign_key_name(link_table, conversion.linked_column, conversion.linked_table)),
            ondelete="CASCADE" if link_table in LINKED_SIDE_CASCADES else None,
        ),
        sa.PrimaryKeyConstraint(conversion.owner_key, conversion.linked_column, name=op.f(f"pk_{link_table}")),
        schema=SCHEMA,
    )
    op.create_index(op.f(f"ix_{link_table}_{conversion.linked_column}"), link_table, [conversion.linked_column], unique=False, schema=SCHEMA)


def copy_list_into_association_table(conversion: ListConversion) -> None:
    """INSERT ... SELECT with the dialect's JSON array reader. Skips ids of rows that do not exist; a repeated id keeps its first position."""
    owner, link, linked = qualified(conversion.owner_table), qualified(conversion.link_table), qualified(conversion.linked_table)
    json_column, owner_key, linked_column, linked_key = conversion.json_column, conversion.owner_key, conversion.linked_column, conversion.linked_key
    if op.get_context().dialect.name == "mssql":
        op.execute(
            f"INSERT INTO {link} ({owner_key}, {linked_column}, position) "
            f"SELECT owner.{owner_key}, list_item.value, MIN(CAST(list_item.[key] AS INT)) "
            f"FROM {owner} AS owner CROSS APPLY OPENJSON(CASE WHEN ISJSON(owner.{json_column}) = 1 AND LEFT(LTRIM(owner.{json_column}), 1) = '[' THEN owner.{json_column} ELSE N'[]' END) AS list_item "
            f"WHERE list_item.type = 1 "
            f"AND EXISTS (SELECT 1 FROM {linked} AS linked WHERE linked.{linked_key} = list_item.value) "
            f"GROUP BY owner.{owner_key}, list_item.value"
        )
    else:
        op.execute(
            f"INSERT INTO {link} ({owner_key}, {linked_column}, position) "
            f"SELECT owner.{owner_key}, list_item.value, MIN(list_item.key) "
            f"FROM {owner} AS owner, json_each(owner.{json_column}) AS list_item "
            f"WHERE json_type(owner.{json_column}) = 'array' AND list_item.type = 'text' "
            f"AND EXISTS (SELECT 1 FROM {linked} AS linked WHERE linked.{linked_key} = list_item.value) "
            f"GROUP BY owner.{owner_key}, list_item.value"
        )


def copy_association_table_back_into_list(conversion: ListConversion) -> None:
    """Downgrade: rebuild the JSON array (in position order) for owners that have at least one row; others stay NULL."""
    owner, link = qualified(conversion.owner_table), qualified(conversion.link_table)
    json_column, owner_key, linked_column = conversion.json_column, conversion.owner_key, conversion.linked_column
    if op.get_context().dialect.name == "mssql":
        op.execute(
            f"UPDATE owner SET owner.{json_column} = "
            f"'[' + (SELECT STRING_AGG('\"' + link.{linked_column} + '\"', ',') WITHIN GROUP (ORDER BY link.position) FROM {link} AS link WHERE link.{owner_key} = owner.{owner_key}) + ']' "
            f"FROM {owner} AS owner WHERE EXISTS (SELECT 1 FROM {link} AS link WHERE link.{owner_key} = owner.{owner_key})"
        )
    else:
        op.execute(
            f"UPDATE {owner} SET {json_column} = "
            f"(SELECT json_group_array({linked_column}) FROM (SELECT {linked_column} FROM {link} WHERE {link}.{owner_key} = {owner}.{owner_key} ORDER BY position)) "
            f"WHERE EXISTS (SELECT 1 FROM {link} WHERE {link}.{owner_key} = {owner}.{owner_key})"
        )


def upgrade() -> None:
    for conversion in CONVERSIONS:
        create_association_table(conversion)
        copy_list_into_association_table(conversion)
    for conversion in CONVERSIONS:
        op.drop_column(conversion.owner_table, conversion.json_column, schema=SCHEMA)


def downgrade() -> None:
    for conversion in CONVERSIONS:
        op.add_column(conversion.owner_table, sa.Column(conversion.json_column, sa.JSON(), nullable=True), schema=SCHEMA)
        copy_association_table_back_into_list(conversion)
    for conversion in CONVERSIONS:
        op.drop_index(op.f(f"ix_{conversion.link_table}_{conversion.linked_column}"), table_name=conversion.link_table, schema=SCHEMA)
        op.drop_table(conversion.link_table, schema=SCHEMA)

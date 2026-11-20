"""team members: invitation facts, four new roles, one person per application per address

A stakeholder now also records whether the person was invited and has signed in (four nullable columns, no backfill: existing rows read
as "listed"). The role list gains lead, infra, devops and tester, so the CHECK on ``stakeholder.stakeholder_role`` is replaced by one built
from the enum. A filtered unique index keeps one person per application per email address.

Existing data is checked BEFORE the index is created: two people on one application with the same address (ignoring letter case) are
never merged by guessing; the migration stops with a message that names the rows to correct, and nothing is changed. On SQL Server this is a
``THROW`` in the generated script, so DBAs who run the delta script by hand get the same message. Addresses are then stored in lower case.

SQLite note: SQLite cannot replace a CHECK constraint without a rebuild that cascade-deletes rows, so the role check is left alone there
(local demo databases are disposable; a new file gets the constraint from the entities). Columns and the index are added on every database.

Revision ID: e4c8a1d7b2f6
Revises: d2a6b0c5e8f9
Create Date: 2026-11-21 09:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import keigan.entities.base_entity
from keigan.config.settings import get_settings
from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase
from keigan.entities.status_values import StakeholderRecipientType

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'e4c8a1d7b2f6'
down_revision: str | None = 'd2a6b0c5e8f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "stakeholder"
ROLE_CONSTRAINT = "ck_stakeholder_stakeholder_role_values"
EMAIL_INDEX = "uq_stakeholder_application_email"
PERSON_WITH_EMAIL_FILTER = f"email_address IS NOT NULL AND recipient_type = '{StakeholderRecipientType.PERSON.value}'"
ROLES_BEFORE_THIS_REVISION = ("sre", "developer", "manager", "executive", "business_owner", "vendor_contact")
INVITATION_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("invited_at", keigan.entities.base_entity.UtcDateTime(timezone=True)),
    ("invited_by_user_principal_name", sa.String(length=320)),
    ("last_invitation_sent_at", keigan.entities.base_entity.UtcDateTime(timezone=True)),
    ("joined_at", keigan.entities.base_entity.UtcDateTime(timezone=True)),
)


def _stop_when(dialect_query_condition: str, message: str) -> None:
    """Stop the migration with ``message`` if any stakeholder row matches ``dialect_query_condition`` (a SELECT body after FROM)."""
    qualified_table = f"{SCHEMA_PREFIX}{TABLE}"
    dialect_name = op.get_context().dialect.name
    if dialect_name == "mssql":
        op.execute(f"IF EXISTS (SELECT 1 FROM {qualified_table} {dialect_query_condition}) THROW 50000, N'{message.replace(chr(39), chr(39) * 2)}', 1")
    elif not op.get_context().as_sql:
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {qualified_table} {dialect_query_condition} LIMIT 1")).first():
            raise RuntimeError(message)


def _stop_when_two_people_share_an_address() -> None:
    message = (
        f"Keigan migration {revision} stopped: two people of one application share an email address in {SCHEMA_PREFIX}{TABLE}. "
        f"Run SELECT application_id, LOWER(email_address) FROM {SCHEMA_PREFIX}{TABLE} WHERE {PERSON_WITH_EMAIL_FILTER} GROUP BY application_id, LOWER(email_address) HAVING COUNT(*) > 1 "
        "to see them, delete or correct the extra rows, then run this script again. Nothing was changed."
    )
    duplicate_condition = (
        f"WHERE {PERSON_WITH_EMAIL_FILTER} AND EXISTS (SELECT 1 FROM {SCHEMA_PREFIX}{TABLE} other WHERE other.application_id = {SCHEMA_PREFIX}{TABLE}.application_id "
        f"AND other.stakeholder_id <> {SCHEMA_PREFIX}{TABLE}.stakeholder_id AND other.recipient_type = '{StakeholderRecipientType.PERSON.value}' "
        f"AND LOWER(other.email_address) = LOWER({SCHEMA_PREFIX}{TABLE}.email_address))"
    )
    _stop_when(duplicate_condition, message)


def _role_condition_from_the_entity() -> str:
    entity_table = next(candidate for candidate in EntityBase.metadata.sorted_tables if candidate.name == TABLE)
    return next(str(constraint.sqltext) for constraint in entity_table.constraints if constraint.name == ROLE_CONSTRAINT)


def upgrade() -> None:
    _stop_when_two_people_share_an_address()
    for column_name, column_type in INVITATION_COLUMNS:
        op.add_column(TABLE, sa.Column(column_name, column_type, nullable=True), schema=SCHEMA)
    op.execute(f"UPDATE {SCHEMA_PREFIX}{TABLE} SET email_address = LOWER(email_address) WHERE email_address IS NOT NULL")
    op.create_index(
        EMAIL_INDEX, TABLE, ["application_id", "email_address"], unique=True, schema=SCHEMA,
        mssql_where=sa.text(PERSON_WITH_EMAIL_FILTER), postgresql_where=sa.text(PERSON_WITH_EMAIL_FILTER), sqlite_where=sa.text(PERSON_WITH_EMAIL_FILTER),
    )
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot replace a CHECK constraint without a rebuild that cascade-deletes rows: the stakeholder role check was left as it is. Recreate the local demo database to get it.")
        return
    op.drop_constraint(op.f(ROLE_CONSTRAINT), TABLE, type_="check", schema=SCHEMA)
    op.create_check_constraint(op.f(ROLE_CONSTRAINT), TABLE, sa.text(_role_condition_from_the_entity()), schema=SCHEMA)


def downgrade() -> None:
    quoted_roles = ", ".join(f"'{role}'" for role in ROLES_BEFORE_THIS_REVISION)
    if op.get_context().dialect.name != "sqlite":
        _stop_when(
            f"WHERE stakeholder_role NOT IN ({quoted_roles})",
            f"Keigan migration {revision} cannot be undone: {SCHEMA_PREFIX}{TABLE} holds people with the roles lead, infra, devops or tester, which the earlier schema does not allow. Change their role first. Nothing was changed.",
        )
    op.drop_index(EMAIL_INDEX, table_name=TABLE, schema=SCHEMA)
    for column_name, _ in reversed(INVITATION_COLUMNS):
        op.drop_column(TABLE, column_name, schema=SCHEMA)
    if op.get_context().dialect.name == "sqlite":
        return
    op.drop_constraint(op.f(ROLE_CONSTRAINT), TABLE, type_="check", schema=SCHEMA)
    op.create_check_constraint(op.f(ROLE_CONSTRAINT), TABLE, sa.text(f"stakeholder_role IN ({quoted_roles})"), schema=SCHEMA)

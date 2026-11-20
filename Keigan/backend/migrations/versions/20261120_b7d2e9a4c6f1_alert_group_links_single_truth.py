"""alert group links single truth

An alert group, the investigation that covers it and the incident it belongs to were linked from both sides
(``alert_group.investigation_id`` / ``incident_id`` and ``investigation.alert_group_id`` / ``incident_id``), and the two sides
could disagree (H14). The alert group's own columns are now the single source of truth: several groups can share one
investigation or incident, so it is the group that says what covers it. ``investigation.alert_group_id`` is dropped.
Keigan writes the links through one method (AlertGroupLinkService) that refuses a group and its investigation naming different
incidents. The foreign keys on the group's columns arrive in the next revision.

Repair of existing rows, in this order (portable SQL, also rendered in offline mode):
1. A group without an investigation takes the oldest investigation that named it as its origin.
2. An investigation without an incident takes the lowest incident id among the groups that point at it.
3. A group whose investigation has an incident takes that incident. The investigation's incident wins a disagreement because it
   is a real foreign key that the incident room already shows. Where an investigation named an origin group that already has a
   different investigation, that origin pointer is simply lost with the column.

Revision ID: b7d2e9a4c6f1
Revises: a3f5c0d1e2b4
Create Date: 2026-11-20 18:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'b7d2e9a4c6f1'
down_revision: str | None = 'a3f5c0d1e2b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_definitions() -> tuple[sa.TableClause, sa.TableClause, sa.TableClause]:
    alert_group = sa.table("alert_group", sa.column("alert_group_id"), sa.column("investigation_id"), sa.column("incident_id"), schema=SCHEMA)
    investigation = sa.table("investigation", sa.column("investigation_id"), sa.column("alert_group_id"), sa.column("incident_id"), sa.column("created_at"), schema=SCHEMA)
    incident = sa.table("incident", sa.column("incident_id"), schema=SCHEMA)
    return alert_group, investigation, incident


def give_groups_the_investigation_that_named_them() -> None:
    alert_group, investigation, _ = table_definitions()
    origin = investigation.alias("origin")
    oldest_origin = (
        sa.select(origin.c.investigation_id).where(origin.c.alert_group_id == alert_group.c.alert_group_id).order_by(origin.c.created_at, origin.c.investigation_id).limit(1).scalar_subquery()
    )
    has_origin = sa.exists().where(origin.c.alert_group_id == alert_group.c.alert_group_id)
    op.execute(alert_group.update().where(alert_group.c.investigation_id.is_(None), has_origin).values(investigation_id=oldest_origin))


def give_investigations_without_an_incident_the_incident_of_their_groups() -> None:
    alert_group, investigation, incident = table_definitions()
    group = alert_group.alias("covered_group")
    existing_incident = sa.exists().where(incident.c.incident_id == group.c.incident_id)
    lowest_group_incident = (
        sa.select(sa.func.min(group.c.incident_id)).where(group.c.investigation_id == investigation.c.investigation_id, group.c.incident_id.is_not(None), existing_incident).scalar_subquery()
    )
    has_group_with_incident = sa.exists().where(group.c.investigation_id == investigation.c.investigation_id, group.c.incident_id.is_not(None), existing_incident)
    op.execute(investigation.update().where(investigation.c.incident_id.is_(None), has_group_with_incident).values(incident_id=lowest_group_incident))


def make_groups_follow_the_incident_of_their_investigation() -> None:
    alert_group, investigation, _ = table_definitions()
    covering = investigation.alias("covering")
    incident_of_investigation = sa.select(covering.c.incident_id).where(covering.c.investigation_id == alert_group.c.investigation_id).scalar_subquery()
    disagrees = sa.exists().where(
        covering.c.investigation_id == alert_group.c.investigation_id, covering.c.incident_id.is_not(None), sa.or_(alert_group.c.incident_id.is_(None), alert_group.c.incident_id != covering.c.incident_id)
    )
    op.execute(alert_group.update().where(alert_group.c.investigation_id.is_not(None), disagrees).values(incident_id=incident_of_investigation))


def upgrade() -> None:
    give_groups_the_investigation_that_named_them()
    give_investigations_without_an_incident_the_incident_of_their_groups()
    make_groups_follow_the_incident_of_their_investigation()
    # Plain DROP INDEX / DROP COLUMN, never batch mode: on SQLite a table rebuild with foreign keys on cascade-deletes child rows.
    op.drop_index("ix_investigation_alert_group_id", table_name="investigation", schema=SCHEMA)
    op.drop_column("investigation", "alert_group_id", schema=SCHEMA)


def downgrade() -> None:
    op.add_column("investigation", sa.Column("alert_group_id", sa.String(length=36), nullable=True), schema=SCHEMA)
    op.create_index("ix_investigation_alert_group_id", "investigation", ["alert_group_id"], unique=False, schema=SCHEMA)
    alert_group, investigation, _ = table_definitions()
    covered_group = alert_group.alias("covered_group")
    first_group = sa.select(sa.func.min(covered_group.c.alert_group_id)).where(covered_group.c.investigation_id == investigation.c.investigation_id).scalar_subquery()
    has_group = sa.exists().where(covered_group.c.investigation_id == investigation.c.investigation_id)
    op.execute(investigation.update().where(has_group).values(alert_group_id=first_group))

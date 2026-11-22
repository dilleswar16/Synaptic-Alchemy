"""action items: follow-up tasks after an incident, tracked to done

Spec 29 (C1). Until now the action items of a postmortem were only text inside the report (and a pydantic output schema), so nothing could be tracked, queried or reminded.
``action_item`` makes each one a row with an owner (a team member chosen by a person), a due date, a priority, a type and a status. An item the AI suggests starts as ``proposed``
and is not tracked until a person accepts it. Nothing is backfilled: the follow-ups of earlier postmortems were never agreed by anyone.

Revision ID: e7b3a9d1c5f2
Revises: c8a2e4f6b1d3
Create Date: 2026-11-23 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'e7b3a9d1c5f2'
down_revision: str | None = 'c8a2e4f6b1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class ActionItemStatus(StrEnum):
    PROPOSED = "proposed"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    WONT_DO = "wont_do"


class ActionItemType(StrEnum):
    PREVENT = "prevent"
    DETECT = "detect"
    MITIGATE = "mitigate"


class ActionItemPriority(StrEnum):
    TOP = "top"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ActionItemSource(StrEnum):
    POSTMORTEM = "postmortem"
    MANUAL = "manual"


def _check(column: str, values: type[StrEnum]) -> sa.CheckConstraint:
    allowed = ", ".join(repr(member.value) for member in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_action_item_{column}_values"))


def upgrade() -> None:
    op.create_table(
        "action_item",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("updated_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("action_item_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=True),
        sa.Column("postmortem_id", sa.String(36), nullable=True),
        sa.Column("incident_reference_text", sa.String(60), nullable=True),
        sa.Column("item_source_kind", sa.String(30), nullable=False),
        sa.Column("source_record_id", sa.String(36), nullable=True),
        sa.Column("item_title", sa.String(300), nullable=False),
        sa.Column("item_details_markdown", sa.Text(), nullable=True),
        sa.Column("action_type", sa.String(10), nullable=False),
        sa.Column("action_priority", sa.String(10), nullable=False),
        sa.Column("item_status", sa.String(20), nullable=False),
        sa.Column("suggested_owner_role_text", sa.String(200), nullable=True),
        sa.Column("owner_stakeholder_id", sa.String(36), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("original_due_on", sa.Date(), nullable=True),
        sa.Column("due_on_change_count", sa.Integer(), nullable=False),
        sa.Column("status_reason_text", sa.String(1000), nullable=True),
        sa.Column("completion_note_text", sa.String(2000), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("accepted_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("external_reference_text", sa.String(60), nullable=True),
        sa.Column("last_reminded_at", sa.DateTime(), nullable=True),
        sa.Column("reminder_count", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("action_item_id", name=op.f("pk_action_item")),
        sa.ForeignKeyConstraint(["application_id"], [f"{SCHEMA_PREFIX}application.application_id"], name=op.f("fk_action_item_application_id_application"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], [f"{SCHEMA_PREFIX}incident.incident_id"], name=op.f("fk_action_item_incident_id_incident")),
        sa.ForeignKeyConstraint(["postmortem_id"], [f"{SCHEMA_PREFIX}postmortem_report.postmortem_id"], name=op.f("fk_action_item_postmortem_id_postmortem_report")),
        sa.ForeignKeyConstraint(["owner_stakeholder_id"], [f"{SCHEMA_PREFIX}stakeholder.stakeholder_id"], name=op.f("fk_action_item_owner_stakeholder_id_stakeholder")),
        _check("item_source_kind", ActionItemSource),
        _check("action_type", ActionItemType),
        _check("action_priority", ActionItemPriority),
        _check("item_status", ActionItemStatus),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_action_item_application_id_item_status_due_on"), "action_item", ["application_id", "item_status", "due_on"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_action_item_incident_id"), "action_item", ["incident_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_action_item_postmortem_id"), "action_item", ["postmortem_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_action_item_owner_stakeholder_id"), "action_item", ["owner_stakeholder_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("action_item", schema=SCHEMA)

"""similar incident memory: the remembered incidents, the facts they can share, and people's answers on whether a suggestion was relevant

Spec 34. ``incident_memory_entry`` is one masked, shortened account of an investigated incident (title, cause, fix, search terms) with one live row per investigation;
``incident_memory_key`` holds the facts two incidents can share (a kind and a hash of the normalised value); ``incident_memory_relevance_feedback`` holds one person's
"relevant" or "not relevant" per suggestion. Nothing is backfilled here: entries are built by the ``refresh_incident_memory_entry`` job, and a script rebuilds them for
investigations that already exist.

Revision ID: e6b2d8f4a0c3
Revises: d5a9b3e7c1f8
Create Date: 2026-11-24 15:00:00.000000
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

revision: str = 'e6b2d8f4a0c3'
down_revision: str | None = 'd5a9b3e7c1f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class IncidentMemoryEntryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    HIDDEN = "hidden"


class IncidentMemoryKeyKind(StrEnum):
    SERVICE = "service"
    SHARED_RESOURCE = "shared_resource"
    ALERT_RULE = "alert_rule"
    ERROR_SIGNATURE = "error_signature"
    CHANGE_OPERATION = "change_operation"
    DEPENDENCY_TARGET = "dependency_target"
    INCIDENT_CATEGORY = "incident_category"


class IncidentMemoryCauseSource(StrEnum):
    POSTMORTEM = "postmortem"
    INVESTIGATION = "investigation"
    NONE = "none"


class IncidentMemoryFixSource(StrEnum):
    RESOLUTION_NOTE = "resolution_note"
    FIX_PLAN = "fix_plan"
    HYPOTHESIS_FIX = "hypothesis_fix"
    NONE = "none"


class IncidentMemoryRelevanceVerdict(StrEnum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"


def _check(table: str, column: str, values: type[StrEnum]) -> sa.CheckConstraint:
    condition = f"{column} IN ({', '.join(repr(member.value) for member in values)})"
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{column}_values"))


def upgrade() -> None:
    op.create_table(
        "incident_memory_entry",
        sa.Column("incident_memory_entry_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=True),
        sa.Column("entry_status", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("incident_title_text", sa.String(500), nullable=False),
        sa.Column("cause_text", sa.Text(), nullable=True),
        sa.Column("fix_text", sa.Text(), nullable=True),
        sa.Column("cause_source", sa.String(20), nullable=False),
        sa.Column("fix_source", sa.String(20), nullable=False),
        sa.Column("search_terms_json", sa.JSON(), nullable=False),
        sa.Column("service_ids_json", sa.JSON(), nullable=False),
        sa.Column("hidden_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("hidden_at", sa.DateTime(), nullable=True),
        sa.Column("hide_reason_text", sa.String(500), nullable=True),
        sa.Column("built_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("updated_by_user_principal_name", sa.String(320), nullable=True),
        sa.PrimaryKeyConstraint("incident_memory_entry_id", name=op.f("pk_incident_memory_entry")),
        sa.ForeignKeyConstraint(["application_id"], [f"{SCHEMA_PREFIX}application.application_id"], name=op.f("fk_incident_memory_entry_application_id_application"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["investigation_id"], [f"{SCHEMA_PREFIX}investigation.investigation_id"], name=op.f("fk_incident_memory_entry_investigation_id_investigation")),
        sa.ForeignKeyConstraint(["incident_id"], [f"{SCHEMA_PREFIX}incident.incident_id"], name=op.f("fk_incident_memory_entry_incident_id_incident")),
        sa.UniqueConstraint("investigation_id", name=op.f("uq_incident_memory_entry_investigation_id")),
        _check("incident_memory_entry", "entry_status", IncidentMemoryEntryStatus),
        _check("incident_memory_entry", "cause_source", IncidentMemoryCauseSource),
        _check("incident_memory_entry", "fix_source", IncidentMemoryFixSource),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_incident_memory_entry_application_id_entry_status_occurred_at"), "incident_memory_entry", ["application_id", "entry_status", "occurred_at"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_incident_memory_entry_incident_id"), "incident_memory_entry", ["incident_id"], unique=False, schema=SCHEMA)

    op.create_table(
        "incident_memory_key",
        sa.Column("incident_memory_entry_id", sa.String(36), nullable=False),
        sa.Column("key_kind", sa.String(30), nullable=False),
        sa.Column("key_value_hash", sa.String(64), nullable=False),
        sa.Column("key_display_text", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("incident_memory_entry_id", "key_kind", "key_value_hash", name=op.f("pk_incident_memory_key")),
        sa.ForeignKeyConstraint(["incident_memory_entry_id"], [f"{SCHEMA_PREFIX}incident_memory_entry.incident_memory_entry_id"], name=op.f("fk_incident_memory_key_incident_memory_entry_id_incident_memory_entry"), ondelete="CASCADE"),
        _check("incident_memory_key", "key_kind", IncidentMemoryKeyKind),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_incident_memory_key_key_kind_key_value_hash"), "incident_memory_key", ["key_kind", "key_value_hash"], unique=False, schema=SCHEMA)

    op.create_table(
        "incident_memory_relevance_feedback",
        sa.Column("relevance_feedback_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("incident_memory_entry_id", sa.String(36), nullable=False),
        sa.Column("user_principal_name", sa.String(320), nullable=False),
        sa.Column("relevance_verdict", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("relevance_feedback_id", name=op.f("pk_incident_memory_relevance_feedback")),
        sa.ForeignKeyConstraint(["investigation_id"], [f"{SCHEMA_PREFIX}investigation.investigation_id"], name=op.f("fk_incident_memory_relevance_feedback_investigation_id_investigation")),
        sa.ForeignKeyConstraint(
            ["incident_memory_entry_id"], [f"{SCHEMA_PREFIX}incident_memory_entry.incident_memory_entry_id"],
            name=op.f("fk_incident_memory_relevance_feedback_incident_memory_entry_id_incident_memory_entry"), ondelete="CASCADE",
        ),
        sa.UniqueConstraint("investigation_id", "incident_memory_entry_id", "user_principal_name", name="uq_incident_memory_relevance_feedback_person"),
        _check("incident_memory_relevance_feedback", "relevance_verdict", IncidentMemoryRelevanceVerdict),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_incident_memory_relevance_feedback_investigation_id"), "incident_memory_relevance_feedback", ["investigation_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_incident_memory_relevance_feedback_incident_memory_entry_id"), "incident_memory_relevance_feedback", ["incident_memory_entry_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("incident_memory_relevance_feedback", schema=SCHEMA)
    op.drop_table("incident_memory_key", schema=SCHEMA)
    op.drop_table("incident_memory_entry", schema=SCHEMA)

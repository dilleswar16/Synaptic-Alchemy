"""error budget policy: the team's agreement, what each incident cost, and the breaches

Spec 30 (C2). Three tables: ``error_budget_policy`` (one row per application, off until a team turns it on), ``incident_budget_impact`` (how much of each SLO's error budget one
incident used, with its inputs; stored because the raw SLI measurements expire) and ``error_budget_policy_breach`` (a threshold was crossed, and whether the requirement that follows
was met, waived or has ended). Three filtered unique indexes keep one breach per incident, one open breach per outage class and one open breach per exhausted SLO. The action item
source list gains ``error_budget_policy``, so that CHECK is replaced. Nothing is backfilled: there is no history of agreements to restate.

SQLite note: SQLite cannot replace a CHECK constraint without a rebuild that cascade-deletes rows, so the action item source check is left alone there (local demo databases are
disposable; a new file gets the constraint from the entities).

Revision ID: f4a8c2e6b0d7
Revises: e7b3a9d1c5f2
Create Date: 2026-11-23 20:00:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from enum import StrEnum

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'f4a8c2e6b0d7'
down_revision: str | None = 'e7b3a9d1c5f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


class IncidentBudgetImpactState(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"
    INSUFFICIENT_DATA = "insufficient_data"


class ErrorBudgetBreachKind(StrEnum):
    SINGLE_INCIDENT = "single_incident"
    OUTAGE_CLASS = "outage_class"
    BUDGET_EXHAUSTED = "budget_exhausted"


class ErrorBudgetRequirementStatus(StrEnum):
    OPEN = "open"
    MET = "met"
    WAIVED = "waived"
    ENDED = "ended"


SOURCES_BEFORE_THIS_REVISION = ("postmortem", "manual")
SOURCES_NOW = ("postmortem", "manual", "error_budget_policy")
SOURCE_CONSTRAINT = "ck_action_item_item_source_kind_values"

_SINGLE_INCIDENT_FILTER = f"breach_kind = '{ErrorBudgetBreachKind.SINGLE_INCIDENT.value}'"
_OPEN_OUTAGE_CLASS_FILTER = f"breach_kind = '{ErrorBudgetBreachKind.OUTAGE_CLASS.value}' AND requirement_status = '{ErrorBudgetRequirementStatus.OPEN.value}'"
_OPEN_EXHAUSTED_FILTER = f"breach_kind = '{ErrorBudgetBreachKind.BUDGET_EXHAUSTED.value}' AND requirement_status = '{ErrorBudgetRequirementStatus.OPEN.value}'"


def _check(table: str, column: str, values: type[StrEnum]) -> sa.CheckConstraint:
    allowed = ", ".join(repr(member.value) for member in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}_values"))


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "error_budget_policy",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("updated_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("error_budget_policy_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("single_incident_threshold_percent", sa.Float(), nullable=True),
        sa.Column("outage_class_threshold_percent", sa.Float(), nullable=True),
        sa.Column("outage_class_window_days", sa.Integer(), nullable=True),
        sa.Column("exhausted_budget_guidance_text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("error_budget_policy_id", name=op.f("pk_error_budget_policy")),
        sa.ForeignKeyConstraint(["application_id"], [f"{SCHEMA_PREFIX}application.application_id"], name=op.f("fk_error_budget_policy_application_id_application"), ondelete="CASCADE"),
        sa.UniqueConstraint("application_id", name=op.f("uq_error_budget_policy_application_id")),
        schema=SCHEMA,
    )
    op.create_table(
        "incident_budget_impact",
        sa.Column("incident_budget_impact_id", sa.String(36), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("slo_id", sa.String(36), nullable=True),
        sa.Column("sli_name_text", sa.String(200), nullable=False),
        sa.Column("target_percentage", sa.Float(), nullable=False),
        sa.Column("budget_window_days", sa.Integer(), nullable=False),
        sa.Column("impact_window_start", sa.DateTime(), nullable=False),
        sa.Column("impact_window_end", sa.DateTime(), nullable=False),
        sa.Column("budget_window_start", sa.DateTime(), nullable=False),
        sa.Column("budget_window_end", sa.DateTime(), nullable=False),
        sa.Column("bad_event_count", sa.BigInteger(), nullable=False),
        sa.Column("impact_total_event_count", sa.BigInteger(), nullable=False),
        sa.Column("window_total_event_count", sa.BigInteger(), nullable=False),
        sa.Column("data_coverage_percent", sa.Float(), nullable=False),
        sa.Column("budget_event_count", sa.Float(), nullable=True),
        sa.Column("budget_share_percent", sa.Float(), nullable=True),
        sa.Column("is_service_matched", sa.Boolean(), nullable=False),
        sa.Column("impact_state", sa.String(20), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("incident_budget_impact_id", name=op.f("pk_incident_budget_impact")),
        sa.ForeignKeyConstraint(["incident_id"], [f"{SCHEMA_PREFIX}incident.incident_id"], name=op.f("fk_incident_budget_impact_incident_id_incident"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slo_id"], [f"{SCHEMA_PREFIX}service_level_objective.slo_id"], name=op.f("fk_incident_budget_impact_slo_id_service_level_objective")),
        sa.UniqueConstraint("incident_id", "slo_id", name=op.f("uq_incident_budget_impact_incident_id_slo_id")),
        _check("incident_budget_impact", "impact_state", IncidentBudgetImpactState),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_incident_budget_impact_application_id_evaluated_at"), "incident_budget_impact", ["application_id", "evaluated_at"], unique=False, schema=SCHEMA)
    op.create_table(
        "error_budget_policy_breach",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("updated_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("error_budget_policy_breach_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.String(36), nullable=False),
        sa.Column("breach_kind", sa.String(30), nullable=False),
        sa.Column("incident_id", sa.String(36), nullable=True),
        sa.Column("incident_reference_text", sa.String(60), nullable=True),
        sa.Column("slo_id", sa.String(36), nullable=True),
        sa.Column("sli_name_text", sa.String(200), nullable=True),
        sa.Column("recurrence_category", sa.String(40), nullable=True),
        sa.Column("recurrence_service_id", sa.String(36), nullable=True),
        sa.Column("recurrence_service_name_text", sa.String(200), nullable=True),
        sa.Column("measured_share_percent", sa.Float(), nullable=True),
        sa.Column("threshold_percent", sa.Float(), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("requirement_status", sa.String(20), nullable=False),
        sa.Column("requirement_changed_at", sa.DateTime(), nullable=False),
        sa.Column("qualifying_action_item_id", sa.String(36), nullable=True),
        sa.Column("waived_by_user_principal_name", sa.String(320), nullable=True),
        sa.Column("waiver_reason_text", sa.String(1000), nullable=True),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("is_provisional", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("error_budget_policy_breach_id", name=op.f("pk_error_budget_policy_breach")),
        sa.ForeignKeyConstraint(["application_id"], [f"{SCHEMA_PREFIX}application.application_id"], name=op.f("fk_error_budget_policy_breach_application_id_application"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], [f"{SCHEMA_PREFIX}incident.incident_id"], name=op.f("fk_error_budget_policy_breach_incident_id_incident")),
        sa.ForeignKeyConstraint(["slo_id"], [f"{SCHEMA_PREFIX}service_level_objective.slo_id"], name=op.f("fk_error_budget_policy_breach_slo_id_service_level_objective")),
        sa.ForeignKeyConstraint(["qualifying_action_item_id"], [f"{SCHEMA_PREFIX}action_item.action_item_id"], name=op.f("fk_error_budget_policy_breach_qualifying_action_item_id_action_item")),
        _check("error_budget_policy_breach", "breach_kind", ErrorBudgetBreachKind),
        _check("error_budget_policy_breach", "requirement_status", ErrorBudgetRequirementStatus),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_error_budget_policy_breach_application_id"), "error_budget_policy_breach", ["application_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_error_budget_policy_breach_incident_id"), "error_budget_policy_breach", ["incident_id"], unique=False, schema=SCHEMA)
    for name, columns, condition in (
        ("uq_error_budget_policy_breach_single_incident", ["incident_id"], _SINGLE_INCIDENT_FILTER),
        ("uq_error_budget_policy_breach_open_outage_class", ["application_id", "recurrence_category", "recurrence_service_id"], _OPEN_OUTAGE_CLASS_FILTER),
        ("uq_error_budget_policy_breach_open_exhausted", ["slo_id"], _OPEN_EXHAUSTED_FILTER),
    ):
        op.create_index(
            name, "error_budget_policy_breach", columns, unique=True, schema=SCHEMA,
            mssql_where=sa.text(condition), postgresql_where=sa.text(condition), sqlite_where=sa.text(condition),
        )
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot replace a CHECK constraint without a rebuild that cascade-deletes rows: the action item source check was left as it is. Recreate the local demo database to get it.")
        return
    op.drop_constraint(op.f(SOURCE_CONSTRAINT), "action_item", type_="check", schema=SCHEMA)
    op.create_check_constraint(op.f(SOURCE_CONSTRAINT), "action_item", sa.text(f"item_source_kind IN ({_in_list(SOURCES_NOW)})"), schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("error_budget_policy_breach", schema=SCHEMA)  # first: it points at action items
    op.drop_table("incident_budget_impact", schema=SCHEMA)
    op.drop_table("error_budget_policy", schema=SCHEMA)
    if op.get_context().dialect.name != "sqlite":
        op.execute(sa.text(f"DELETE FROM {SCHEMA_PREFIX}action_item WHERE item_source_kind NOT IN ({_in_list(SOURCES_BEFORE_THIS_REVISION)})"))
        op.drop_constraint(op.f(SOURCE_CONSTRAINT), "action_item", type_="check", schema=SCHEMA)
        op.create_check_constraint(op.f(SOURCE_CONSTRAINT), "action_item", sa.text(f"item_source_kind IN ({_in_list(SOURCES_BEFORE_THIS_REVISION)})"), schema=SCHEMA)

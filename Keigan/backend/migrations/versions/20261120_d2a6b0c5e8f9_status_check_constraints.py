"""status check constraints

Status, kind and priority columns accepted any text, so a typo or a retired value could be stored silently (H13). Each column
with a fixed value set now has a CHECK constraint ``ck_<table>_<column>_values``. The allowed values are NOT typed here: they come
from the enums in ``keigan/entities/status_values.py`` through the constraints the entities declare, so the migration, the
entities and the code that writes the values cannot disagree. ``CONSTRAINED_COLUMNS`` freezes which columns this revision covers
(later constraints get their own revision); a test keeps it equal to the entities.

Existing rows are checked BEFORE each constraint is added. Rows with another value are not rewritten (no safe mapping exists for a
status nobody wrote): the migration stops with a message that names the column and says what to do, and nothing is changed. On SQL
Server this is a ``THROW`` in the generated script, so DBAs who run the delta script by hand get the same message.

SQLite note: SQLite cannot add a CHECK to an existing table without a rebuild, and a rebuild with foreign keys on cascade-deletes the
child rows, so this revision leaves existing SQLite databases as they are. SQLite is only used for local demo databases, which are
disposable: recreate the file and Keigan creates every table with its constraints from the entities.

Revision ID: d2a6b0c5e8f9
Revises: c9e4f1b8d3a7
Create Date: 2026-11-20 18:30:00.000000
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from keigan.config.settings import get_settings
from keigan.entities import all_entities  # noqa: F401  (registers every table)
from keigan.entities.base_entity import EntityBase

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'd2a6b0c5e8f9'
down_revision: str | None = 'c9e4f1b8d3a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Read by the schema drift test, which keeps it equal to the CHECK constraints the entities declare.
CONSTRAINED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("alert_source", "source_tool"), ("alert_source", "source_status"), ("alert_event", "processing_status"), ("alert", "alert_status"), ("alert", "final_disposition"),
    ("alert_decision", "pipeline_stage"), ("alert_group", "group_status"), ("alert_group", "user_feedback_verdict"), ("noise_reduction_policy", "policy_mode"),
    ("servicenow_assignment_group", "verification_status"), ("incident", "incident_source"), ("incident", "incident_status"), ("incident", "keigan_priority"),
    ("investigation", "investigation_trigger"), ("investigation", "investigation_status"), ("investigation", "current_stage_name"), ("investigation", "user_feedback_verdict"),
    ("investigation_hypothesis", "analysis_perspective"), ("investigation_hypothesis", "fix_risk_level"), ("investigation_evidence", "signal_strength"),
    ("incident_communication", "communication_status"), ("postmortem_report", "report_status"), ("conversation", "conversation_scope"), ("conversation_message", "author_role"),
    ("application", "lifecycle_status"), ("application", "criticality_tier"), ("monitored_service", "criticality_tier"), ("application_component", "component_type"),
    ("application_component", "access_verification_status"), ("log_tool_connection", "connection_status"), ("service_log_source", "last_read_test_status"),
    ("external_integration", "integration_status"), ("knowledge_document", "ai_digest_status"), ("application_topology", "generation_status"), ("application_topology", "review_status"),
    ("topology_review_comment", "review_verdict"), ("stakeholder", "recipient_type"), ("stakeholder", "stakeholder_role"), ("stakeholder", "minimum_priority"),
    ("notification_delivery", "delivery_channel"), ("notification_delivery", "delivery_status"), ("teams_incident_chat", "chat_status"), ("background_job", "job_status"),
    ("predictive_signal", "signal_status"), ("predictive_signal", "signal_severity"), ("slo_burn_alert", "burn_alert_severity"), ("intelligence_report", "report_type"),
)


def constraint_name(table: str, column: str) -> str:
    return f"ck_{table}_{column}_values"  # the project's naming convention (entities/base_entity.py)


def condition_from_the_entity(table: str, column: str) -> str:
    """The SQL of the CHECK the entity declares for the column (built from the enum in status_values.py)."""
    entity_table = next(candidate for candidate in EntityBase.metadata.sorted_tables if candidate.name == table)
    for constraint in entity_table.constraints:
        if constraint.name == constraint_name(table, column):
            return str(constraint.sqltext)
    raise RuntimeError(f"The entity for {table} declares no values check for {column}; add it with values_check() in keigan/entities.")


def stop_if_rows_hold_other_values(table: str, column: str, condition: str) -> None:
    qualified_table = f"{SCHEMA_PREFIX}{table}"
    other_values = f"{column} IS NOT NULL AND NOT ({condition})"
    message = (
        f"Keigan migration {revision} stopped: {qualified_table}.{column} holds a value that is not one of the allowed values. "
        f"Run SELECT DISTINCT {column} FROM {qualified_table} to see them, correct those rows, then run this script again. Nothing was changed."
    )
    dialect_name = op.get_context().dialect.name
    if dialect_name == "mssql":
        op.execute(f"IF EXISTS (SELECT 1 FROM {qualified_table} WHERE {other_values}) THROW 50000, N'{message}', 1")
    elif not op.get_context().as_sql:
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {qualified_table} WHERE {other_values}")).scalar():
            raise RuntimeError(message)


def upgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot add CHECK constraints to existing tables without a rebuild that cascade-deletes rows: no constraint was added. Recreate the local demo database to get them.")
        return
    for table, column in CONSTRAINED_COLUMNS:
        condition = condition_from_the_entity(table, column)
        stop_if_rows_hold_other_values(table, column, condition)
        op.create_check_constraint(op.f(constraint_name(table, column)), table, sa.text(condition), schema=SCHEMA)


def downgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        return  # the constraints were never added
    for table, column in reversed(CONSTRAINED_COLUMNS):
        op.drop_constraint(op.f(constraint_name(table, column)), table, type_="check", schema=SCHEMA)

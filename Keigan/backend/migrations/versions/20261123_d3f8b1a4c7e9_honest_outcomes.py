"""honest outcomes: a state for every hypothesis, an outcome for every investigation, a check outcome for every evidence item, and the checks an investigation could not make

Spec 27 (honest outcomes). A hypothesis ends supported, ruled out or inconclusive, with the state the model proposed kept beside it and the rule that lowered it, if one did.
An investigation ends with the cause identified, inconclusive or "cause not visible in the data Keigan can see". Each evidence item says whether it found a signal and whether it was
compared with the healthy window. The new table ``investigation_coverage_gap`` lists what Keigan meant to check and could not, or did not because of a limit.

All new columns are nullable: an investigation stored before this revision has no states and no outcome (the screen says "not recorded"). Evidence rows are different. Their text
was written by Keigan's own code in a fixed form, so the check outcome and the baseline comparison are backfilled from it:

* ``check_outcome = 'not_checked'`` where the summary starts with "Not available:" (a failed read that was stored as if it were evidence),
* ``'no_signal'`` where the summary starts with "Rule-out:" or nothing matched,
* ``'signal'`` for every other row (a row written by some other code, none today, lands here),
* ``baseline_comparison = 'no_baseline_for_source'`` for change events and synthetic probes, ``'compared'`` for the rest.

The CHECK constraints of the new columns are created on SQL Server. SQLite cannot add a CHECK to an existing table without a rebuild that cascade-deletes rows, so a local database
created by this migration (rather than by ``create_all``) has the columns without them, as with the earlier status CHECK revision.

Revision ID: d3f8b1a4c7e9
Revises: b8d4f2a6c0e3
Create Date: 2026-11-23 09:00:00.000000
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

revision: str = 'd3f8b1a4c7e9'
down_revision: str | None = 'b8d4f2a6c0e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


class HypothesisState(StrEnum):
    SUPPORTED = "supported"
    RULED_OUT = "ruled_out"
    INCONCLUSIVE = "inconclusive"


class HypothesisStateGuard(StrEnum):
    SUPPORT_NOT_IN_EVIDENCE = "support_not_in_evidence"
    CONFIDENCE_BELOW_SUPPORTED_MINIMUM = "confidence_below_supported_minimum"
    RULE_OUT_NOT_IN_EVIDENCE = "rule_out_not_in_evidence"
    CONFIDENCE_ABOVE_RULED_OUT_MAXIMUM = "confidence_above_ruled_out_maximum"


class InvestigationOutcome(StrEnum):
    CAUSE_IDENTIFIED = "cause_identified"
    INCONCLUSIVE = "inconclusive"
    CAUSE_NOT_VISIBLE = "cause_not_visible"


class InvestigationOutcomeGuard(StrEnum):
    NOTHING_CHANGED_IN_CHECKED_SOURCES = "nothing_changed_in_checked_sources"
    LEADING_HYPOTHESIS_NOT_SUPPORTED = "leading_hypothesis_not_supported"
    SYNTHESIS_UNAVAILABLE = "synthesis_unavailable"


class EvidenceCheckOutcome(StrEnum):
    SIGNAL = "signal"
    NO_SIGNAL = "no_signal"
    NOT_CHECKED = "not_checked"


class BaselineComparison(StrEnum):
    COMPARED = "compared"
    NO_BASELINE_FOR_SOURCE = "no_baseline_for_source"


class CoverageGapKind(StrEnum):
    SOURCE_NOT_READABLE = "source_not_readable"
    CHANGES_NOT_READABLE = "changes_not_readable"
    SERVICE_WITHOUT_TELEMETRY = "service_without_telemetry"
    SERVICES_BEYOND_LIMIT = "services_beyond_limit"
    CHECKS_BEYOND_LIMIT = "checks_beyond_limit"
    PLANNED_QUERY_REJECTED = "planned_query_rejected"
    PLANNED_QUERY_FAILED = "planned_query_failed"
    RESULTS_LEFT_OUT = "results_left_out"
    PERSPECTIVE_NOT_ANALYSED = "perspective_not_analysed"


class CoverageGapReason(StrEnum):
    ACCESS_REFUSED = "access_refused"
    THROTTLED = "throttled"
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_ERROR = "source_error"
    TIMED_OUT = "timed_out"
    NOT_APPROVED = "not_approved"
    QUERY_REJECTED = "query_rejected"
    READER_NOT_AVAILABLE = "reader_not_available"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_OUTPUT_INVALID = "ai_output_invalid"
    UNKNOWN = "unknown"


# (table, column, type, the enum its CHECK allows or None). The values are copied into this revision on purpose: a migration describes the schema as it was written.
NEW_COLUMNS: list[tuple[str, str, sa.types.TypeEngine, type[StrEnum] | None]] = [
    ("investigation_hypothesis", "hypothesis_state", sa.String(20), HypothesisState),
    ("investigation_hypothesis", "proposed_hypothesis_state", sa.String(20), HypothesisState),
    ("investigation_hypothesis", "state_guard_code", sa.String(40), HypothesisStateGuard),
    ("investigation_hypothesis", "state_reason_markdown", sa.Text(), None),
    ("investigation", "investigation_outcome", sa.String(30), InvestigationOutcome),
    ("investigation", "proposed_investigation_outcome", sa.String(30), InvestigationOutcome),
    ("investigation", "outcome_guard_code", sa.String(40), InvestigationOutcomeGuard),
    ("investigation", "outcome_reason_markdown", sa.Text(), None),
    ("investigation", "leading_perspective_reason_markdown", sa.Text(), None),
    ("investigation_evidence", "check_outcome", sa.String(20), EvidenceCheckOutcome),
    ("investigation_evidence", "baseline_comparison", sa.String(30), BaselineComparison),
]
EVIDENCE_TABLE = f"{SCHEMA_PREFIX}investigation_evidence"


def _values_condition(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(member.value) for member in values)})"


def _check_name(table: str, column: str) -> str:
    return f"ck_{table}_{column}_values"


def _backfill_evidence() -> None:
    """From the exact strings ``evidence_service.py`` writes (see the module docstring)."""
    op.execute(f"UPDATE {EVIDENCE_TABLE} SET check_outcome = 'not_checked' WHERE evidence_summary LIKE 'Not available:%'")
    op.execute(f"UPDATE {EVIDENCE_TABLE} SET check_outcome = 'no_signal' WHERE check_outcome IS NULL AND (evidence_summary LIKE 'Rule-out:%' OR matched_record_count = 0)")
    op.execute(f"UPDATE {EVIDENCE_TABLE} SET check_outcome = 'signal' WHERE check_outcome IS NULL")
    op.execute(f"UPDATE {EVIDENCE_TABLE} SET baseline_comparison = 'no_baseline_for_source' WHERE evidence_category IN ('change_event', 'synthetic_probe')")
    op.execute(f"UPDATE {EVIDENCE_TABLE} SET baseline_comparison = 'compared' WHERE baseline_comparison IS NULL")


def upgrade() -> None:
    for table, column, column_type, _ in NEW_COLUMNS:
        op.add_column(table, sa.Column(column, column_type, nullable=True), schema=SCHEMA)
    if op.get_context().dialect.name == "sqlite":
        logger.warning("SQLite cannot add a CHECK constraint to an existing table without a rebuild that cascade-deletes rows: the new columns were added without theirs. Recreate the local demo database to get them.")
    else:
        for table, column, _, values in NEW_COLUMNS:
            if values is not None:
                op.create_check_constraint(op.f(_check_name(table, column)), table, sa.text(_values_condition(column, values)), schema=SCHEMA)
    op.create_table(
        "investigation_coverage_gap",
        sa.Column("coverage_gap_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("gap_kind", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=True),
        sa.Column("service_id", sa.String(36), nullable=True),
        sa.Column("service_name", sa.String(200), nullable=True),
        sa.Column("source_kind", sa.String(40), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("coverage_gap_id", name=op.f("pk_investigation_coverage_gap")),
        sa.ForeignKeyConstraint(["investigation_id"], [f"{SCHEMA_PREFIX}investigation.investigation_id"], name=op.f("fk_investigation_coverage_gap_investigation_id_investigation"), ondelete="CASCADE"),
        sa.CheckConstraint(_values_condition("gap_kind", CoverageGapKind), name=op.f(_check_name("investigation_coverage_gap", "gap_kind"))),
        sa.CheckConstraint(_values_condition("reason_code", CoverageGapReason), name=op.f(_check_name("investigation_coverage_gap", "reason_code"))),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_investigation_coverage_gap_investigation_id"), "investigation_coverage_gap", ["investigation_id"], unique=False, schema=SCHEMA)
    _backfill_evidence()


def downgrade() -> None:
    op.drop_index(op.f("ix_investigation_coverage_gap_investigation_id"), table_name="investigation_coverage_gap", schema=SCHEMA)
    op.drop_table("investigation_coverage_gap", schema=SCHEMA)
    for table, column, _, values in reversed(NEW_COLUMNS):
        if values is not None and op.get_context().dialect.name != "sqlite":
            op.drop_constraint(op.f(_check_name(table, column)), table, type_="check", schema=SCHEMA)
        op.drop_column(table, column, schema=SCHEMA)

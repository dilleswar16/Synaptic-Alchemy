"""investigation decision trace: one ordered step table per investigation, and the link from an AI attempt to its step

Spec 28 (decision trace). ``investigation_trace_step`` holds, per investigation and in order, its inputs, each AI call (prompt key and version, template and system-prompt hashes,
the manifest of the sections that went in, the raw answer before Keigan's checks, what the checks changed), the evidence summary, the deterministic decisions and the outcome.
``llm_usage_record.investigation_trace_step_id`` ties each attempt (one usage row per attempt) to its step, and the new index on ``investigation_id`` serves the trace and the
token totals, which were a scan.

Nothing is backfilled: an investigation that ran before this revision has no steps, and the screen says so (only its AI usage can be shown).

Revision ID: c8a2e4f6b1d3
Revises: d3f8b1a4c7e9
Create Date: 2026-11-23 15:00:00.000000
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

revision: str = 'c8a2e4f6b1d3'
down_revision: str | None = 'd3f8b1a4c7e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class InvestigationStage(StrEnum):
    TRIAGE = "triage"
    CONTEXT = "context"
    EVIDENCE = "evidence"
    HYPOTHESES = "hypotheses"
    SYNTHESIS = "synthesis"
    COMMUNICATIONS = "communications"
    COMPLETED = "completed"


class InvestigationTraceStepKind(StrEnum):
    INPUTS = "inputs"
    AI_CALL = "ai_call"
    EVIDENCE = "evidence"
    DECISION = "decision"
    OUTCOME = "outcome"


class InvestigationTraceStepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationDecisionKind(StrEnum):
    SERVICES_SELECTED = "services_selected"
    PRIORITY_SET = "priority_set"
    PLANNER_REQUESTED = "planner_requested"
    EVIDENCE_ONLY_MODE = "evidence_only_mode"
    SYNTHESIS_FALLBACK = "synthesis_fallback"


class InvestigationAiCallFailure(StrEnum):
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_RATE_LIMITED = "ai_rate_limited"
    AI_OUTPUT_INVALID = "ai_output_invalid"
    FAILED = "failed"


def _values_condition(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(member.value) for member in values)})"


def _check(column: str, values: type[StrEnum]) -> sa.CheckConstraint:
    return sa.CheckConstraint(_values_condition(column, values), name=op.f(f"ck_investigation_trace_step_{column}_values"))


def upgrade() -> None:
    op.create_table(
        "investigation_trace_step",
        sa.Column("trace_step_id", sa.String(36), nullable=False),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(30), nullable=False),
        sa.Column("step_kind", sa.String(20), nullable=False),
        sa.Column("step_status", sa.String(20), nullable=False),
        sa.Column("decision_kind", sa.String(40), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_milliseconds", sa.Integer(), nullable=True),
        sa.Column("feature_name", sa.String(80), nullable=True),
        sa.Column("prompt_key", sa.String(80), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("prompt_template_sha256", sa.String(64), nullable=True),
        sa.Column("system_prompt_sha256", sa.String(64), nullable=True),
        sa.Column("provider_name", sa.String(40), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("model_tier", sa.String(20), nullable=True),
        sa.Column("input_manifest_json", sa.JSON(), nullable=True),
        sa.Column("estimated_input_token_count", sa.Integer(), nullable=True),
        sa.Column("estimated_output_token_count", sa.Integer(), nullable=True),
        sa.Column("raw_output_json", sa.JSON(), nullable=True),
        sa.Column("raw_output_character_count", sa.Integer(), nullable=True),
        sa.Column("raw_output_is_truncated", sa.Boolean(), nullable=True),
        sa.Column("raw_output_sha256", sa.String(64), nullable=True),
        sa.Column("adjustments_json", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(40), nullable=True),
        sa.Column("hypothesis_id", sa.String(36), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("trace_step_id", name=op.f("pk_investigation_trace_step")),
        sa.ForeignKeyConstraint(["investigation_id"], [f"{SCHEMA_PREFIX}investigation.investigation_id"], name=op.f("fk_investigation_trace_step_investigation_id_investigation"), ondelete="CASCADE"),
        sa.UniqueConstraint("investigation_id", "sequence_number", name=op.f("uq_investigation_trace_step_investigation_id_sequence_number")),
        _check("stage_name", InvestigationStage),
        _check("step_kind", InvestigationTraceStepKind),
        _check("step_status", InvestigationTraceStepStatus),
        _check("decision_kind", InvestigationDecisionKind),
        _check("failure_code", InvestigationAiCallFailure),
        schema=SCHEMA,
    )
    op.add_column("llm_usage_record", sa.Column("investigation_trace_step_id", sa.String(36), nullable=True), schema=SCHEMA)
    op.create_index(op.f("ix_llm_usage_record_investigation_id"), "llm_usage_record", ["investigation_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_usage_record_investigation_id"), table_name="llm_usage_record", schema=SCHEMA)
    op.drop_column("llm_usage_record", "investigation_trace_step_id", schema=SCHEMA)
    op.drop_table("investigation_trace_step", schema=SCHEMA)

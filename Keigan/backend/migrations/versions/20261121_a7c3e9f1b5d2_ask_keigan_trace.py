"""ask keigan trace: one row per answered question and one row per model turn or tool call

``chat_answer_run`` keeps what Keigan did to answer one question (scope, model, tools offered, totals, cited sources) and ``chat_run_step``
the ordered model turns and tool calls inside it, so a person can check an answer later and the evaluation harness can replay it. Both
are new, so there is nothing to backfill. Cascades follow one path only (conversation, run, step); the two message keys, the investigation
key and the step's parent key are NO ACTION, as SQL Server requires, so the code deletes runs before messages. ``chat_run_step.application_id``
is a recorded fact without a foreign key, like ``audit_event.application_id``.

The CHECK values are written out here on purpose: a revision describes the database as it was when it ran, so a value added to an enum later
gets its own revision that replaces the constraint.

Revision ID: a7c3e9f1b5d2
Revises: f1b9d3a5c7e2
Create Date: 2026-11-21 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import keigan.entities.base_entity
from keigan.config.settings import get_settings

# Keigan's tables live in DATABASE_SCHEMA ("keigan" on Azure SQL); None on SQLite.
SCHEMA = get_settings().database_schema_or_none
SCHEMA_PREFIX = f"{SCHEMA}." if SCHEMA else ""

revision: str = 'a7c3e9f1b5d2'
down_revision: str | None = 'f1b9d3a5c7e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UtcDateTime = keigan.entities.base_entity.UtcDateTime(timezone=True)


def upgrade() -> None:
    op.create_table('chat_answer_run',
    sa.Column('answer_run_id', sa.String(length=36), nullable=False),
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('user_message_id', sa.String(length=36), nullable=False),
    sa.Column('assistant_message_id', sa.String(length=36), nullable=True),
    sa.Column('client_request_id', sa.String(length=64), nullable=False),
    sa.Column('conversation_scope', sa.String(length=30), nullable=False),
    sa.Column('investigation_id', sa.String(length=36), nullable=True),
    sa.Column('requested_by_user_principal_name', sa.String(length=320), nullable=False),
    sa.Column('scope_snapshot_json', sa.JSON(), nullable=False),
    sa.Column('run_status', sa.String(length=20), nullable=False),
    sa.Column('stop_reason', sa.String(length=30), nullable=True),
    sa.Column('engine_version', sa.String(length=20), nullable=False),
    sa.Column('prompt_key', sa.String(length=80), nullable=False),
    sa.Column('prompt_version', sa.String(length=20), nullable=False),
    sa.Column('system_prompt_sha256', sa.String(length=64), nullable=False),
    sa.Column('tool_catalog_sha256', sa.String(length=64), nullable=False),
    sa.Column('offered_tools_json', sa.JSON(), nullable=False),
    sa.Column('provider_name', sa.String(length=40), nullable=False),
    sa.Column('model_name', sa.String(length=120), nullable=False),
    sa.Column('model_tier', sa.String(length=20), nullable=False),
    sa.Column('tool_calling_mode', sa.String(length=20), nullable=False),
    sa.Column('limits_json', sa.JSON(), nullable=False),
    sa.Column('total_input_token_count', sa.Integer(), nullable=False),
    sa.Column('total_output_token_count', sa.Integer(), nullable=False),
    sa.Column('token_counts_estimated', sa.Boolean(), nullable=False),
    sa.Column('model_turn_count', sa.Integer(), nullable=False),
    sa.Column('tool_call_count', sa.Integer(), nullable=False),
    sa.Column('citations_json', sa.JSON(), nullable=False),
    sa.Column('follow_up_questions_json', sa.JSON(), nullable=False),
    sa.Column('is_unverified', sa.Boolean(), nullable=False),
    sa.Column('cancel_requested_at', UtcDateTime, nullable=True),
    sa.Column('error_code', sa.String(length=60), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('started_at', UtcDateTime, nullable=False),
    sa.Column('completed_at', UtcDateTime, nullable=True),
    sa.Column('duration_milliseconds', sa.Integer(), nullable=True),
    sa.Column('last_progress_at', UtcDateTime, nullable=False),
    sa.CheckConstraint("conversation_scope IN ('investigation', 'keigan_ai_chat', 'teams_incident_chat')", name=op.f('ck_chat_answer_run_conversation_scope_values')),
    sa.CheckConstraint("run_status IN ('running', 'completed', 'failed', 'cancelled')", name=op.f('ck_chat_answer_run_run_status_values')),
    sa.CheckConstraint("stop_reason IN ('answered', 'tool_limit_reached', 'token_budget_reached', 'cancelled_by_user', 'failed')", name=op.f('ck_chat_answer_run_stop_reason_values')),
    sa.CheckConstraint("tool_calling_mode IN ('native', 'prompted_json', 'scripted_mock')", name=op.f('ck_chat_answer_run_tool_calling_mode_values')),
    sa.ForeignKeyConstraint(['assistant_message_id'], [f'{SCHEMA_PREFIX}conversation_message.message_id'], name=op.f('fk_chat_answer_run_assistant_message_id_conversation_message')),
    sa.ForeignKeyConstraint(['conversation_id'], [f'{SCHEMA_PREFIX}conversation.conversation_id'], name=op.f('fk_chat_answer_run_conversation_id_conversation'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['investigation_id'], [f'{SCHEMA_PREFIX}investigation.investigation_id'], name=op.f('fk_chat_answer_run_investigation_id_investigation')),
    sa.ForeignKeyConstraint(['user_message_id'], [f'{SCHEMA_PREFIX}conversation_message.message_id'], name=op.f('fk_chat_answer_run_user_message_id_conversation_message')),
    sa.PrimaryKeyConstraint('answer_run_id', name=op.f('pk_chat_answer_run')),
    sa.UniqueConstraint('conversation_id', 'client_request_id', name='uq_chat_answer_run_conversation_id_client_request_id'),
    schema=SCHEMA,
    )
    with op.batch_alter_table('chat_answer_run', schema=SCHEMA) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_answer_run_conversation_id'), ['conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_answer_run_investigation_id'), ['investigation_id'], unique=False)
        batch_op.create_index('ix_chat_answer_run_requested_by_user_principal_name_started_at', ['requested_by_user_principal_name', 'started_at'], unique=False)

    op.create_table('chat_run_step',
    sa.Column('run_step_id', sa.String(length=36), nullable=False),
    sa.Column('answer_run_id', sa.String(length=36), nullable=False),
    sa.Column('sequence_number', sa.Integer(), nullable=False),
    sa.Column('step_kind', sa.String(length=20), nullable=False),
    sa.Column('parent_run_step_id', sa.String(length=36), nullable=True),
    sa.Column('step_status', sa.String(length=20), nullable=False),
    sa.Column('started_at', UtcDateTime, nullable=False),
    sa.Column('completed_at', UtcDateTime, nullable=True),
    sa.Column('duration_milliseconds', sa.Integer(), nullable=True),
    sa.Column('turn_number', sa.Integer(), nullable=True),
    sa.Column('turn_finish', sa.String(length=30), nullable=True),
    sa.Column('model_text', sa.Text(), nullable=True),
    sa.Column('input_token_count', sa.Integer(), nullable=True),
    sa.Column('output_token_count', sa.Integer(), nullable=True),
    sa.Column('tool_name', sa.String(length=64), nullable=True),
    sa.Column('tool_version', sa.Integer(), nullable=True),
    sa.Column('tool_source', sa.String(length=80), nullable=True),
    sa.Column('citation_code', sa.String(length=8), nullable=True),
    sa.Column('provider_request_id', sa.String(length=200), nullable=True),
    sa.Column('requested_arguments_json', sa.JSON(), nullable=True),
    sa.Column('effective_arguments_json', sa.JSON(), nullable=True),
    sa.Column('application_id', sa.String(length=36), nullable=True),
    sa.Column('records_json', sa.JSON(), nullable=True),
    sa.Column('output_json', sa.JSON(), nullable=True),
    sa.Column('output_character_count', sa.Integer(), nullable=True),
    sa.Column('output_is_truncated', sa.Boolean(), nullable=True),
    sa.Column('output_item_count', sa.Integer(), nullable=True),
    sa.Column('model_view_text', sa.Text(), nullable=True),
    sa.Column('model_view_sha256', sa.String(length=64), nullable=True),
    sa.Column('masked_value_count', sa.Integer(), nullable=True),
    sa.Column('injection_flagged', sa.Boolean(), nullable=True),
    sa.Column('outcome_code', sa.String(length=60), nullable=True),
    sa.Column('outcome_message', sa.String(length=400), nullable=True),
    sa.CheckConstraint("step_kind IN ('model_turn', 'tool_call')", name=op.f('ck_chat_run_step_step_kind_values')),
    sa.CheckConstraint("step_status IN ('running', 'succeeded', 'failed', 'refused', 'skipped', 'cancelled')", name=op.f('ck_chat_run_step_step_status_values')),
    sa.ForeignKeyConstraint(['answer_run_id'], [f'{SCHEMA_PREFIX}chat_answer_run.answer_run_id'], name=op.f('fk_chat_run_step_answer_run_id_chat_answer_run'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_run_step_id'], [f'{SCHEMA_PREFIX}chat_run_step.run_step_id'], name=op.f('fk_chat_run_step_parent_run_step_id_chat_run_step')),
    sa.PrimaryKeyConstraint('run_step_id', name=op.f('pk_chat_run_step')),
    sa.UniqueConstraint('answer_run_id', 'sequence_number', name='uq_chat_run_step_answer_run_id_sequence_number'),
    schema=SCHEMA,
    )
    with op.batch_alter_table('chat_run_step', schema=SCHEMA) as batch_op:
        batch_op.create_index(batch_op.f('ix_chat_run_step_application_id'), ['application_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chat_run_step_tool_name'), ['tool_name'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('chat_run_step', schema=SCHEMA) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chat_run_step_tool_name'))
        batch_op.drop_index(batch_op.f('ix_chat_run_step_application_id'))

    op.drop_table('chat_run_step', schema=SCHEMA)
    with op.batch_alter_table('chat_answer_run', schema=SCHEMA) as batch_op:
        batch_op.drop_index('ix_chat_answer_run_requested_by_user_principal_name_started_at')
        batch_op.drop_index(batch_op.f('ix_chat_answer_run_investigation_id'))
        batch_op.drop_index(batch_op.f('ix_chat_answer_run_conversation_id'))

    op.drop_table('chat_answer_run', schema=SCHEMA)

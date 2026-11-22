"""The stored trace of one Ask Keigan answer run as the snapshot the screen reads (spec 23, 6.6 and 7.2).

The snapshot is the truth and the event stream is an accelerator: a reload, a dropped connection and the history of a conversation all read it. It is built
from the stored rows only. A step on an application the reader can no longer read is returned redacted (no arguments, output or target), whoever asks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import AgentFinish
from keigan.ai.tool_registry import AskKeiganScope, ToolPresentation, tool_registry
from keigan.config.settings import get_settings
from keigan.dtos.ask_keigan_dtos import (
    AnswerRunView, AnswerView, CitationView, ProblemSummaryView, RecordReferenceView, RunStepToolTargetView, RunStepToolView, RunStepView,
)
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, ConversationMessage
from keigan.entities.status_values import ChatAnswerRunStatus, ChatRunStepKind, ToolCallingMode
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry
from keigan.services.ask_keigan_scopes import bound_argument_names
from keigan.services.ask_keigan_trace import TRUNCATED_OUTPUT_KEY, OutputFlags, output_json_text, output_preview
from keigan.services.authorization_service import AuthorizationService

NOTE_TURN_FINISH: AgentFinish = "tool_requests"  # a model turn that asked for tools: its text is a note in the trace, not the answer
_FALLBACK_PRESENTATION = ToolPresentation.RECORD  # for a tool that is no longer registered: its output is shown as a plain record
_FALLBACK_SOURCE = "keigan"


class AnswerRunSnapshotBuilder:
    def __init__(self, session: AsyncSession, registry: AnswerRunRegistry):
        self.session = session
        self.registry = registry

    async def build(self, run: ChatAnswerRun, current_user: CurrentUser) -> AnswerRunView:
        steps = list((await self.session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == run.answer_run_id).order_by(ChatRunStep.sequence_number))).all())
        readable_application_ids = await AuthorizationService(self.session).readable_application_ids(current_user)
        application_names = await self._application_names({step.application_id for step in steps if step.application_id})
        bound_arguments: Mapping[str, str] = run.scope_snapshot_json.get("boundArguments", {})
        live_run = self.registry.get(run.answer_run_id)
        return AnswerRunView(
            answer_run_id=run.answer_run_id, conversation_id=run.conversation_id, status=run.run_status, stop_reason=run.stop_reason,
            scope=AskKeiganScope(run.scope_snapshot_json["scope"]), started_at=run.started_at, completed_at=run.completed_at,
            duration_milliseconds=run.duration_milliseconds, tool_call_count=run.tool_call_count, maximum_tool_calls=run.limits_json["maximumToolCalls"],
            input_token_count=run.total_input_token_count, output_token_count=run.total_output_token_count, token_counts_estimated=run.token_counts_estimated,
            model_name=run.model_name, tool_calling_mode=ToolCallingMode(run.tool_calling_mode),
            steps=[self._step_view(step, bound_arguments, readable_application_ids, application_names) for step in steps], answer=await self._answer_view(run),
            error=self._error_view(run, current_user), last_sequence=live_run.channel.last_sequence if live_run else 0,
        )

    async def _application_names(self, application_ids: set[str]) -> dict[str, str]:
        if not application_ids:
            return {}
        rows = await self.session.execute(select(Application.application_id, Application.application_name).where(Application.application_id.in_(application_ids)))
        return dict(rows.all())

    def _step_view(self, step: ChatRunStep, bound_arguments: Mapping[str, str], readable_application_ids: set[str], application_names: Mapping[str, str]) -> RunStepView:
        is_note = step.step_kind == ChatRunStepKind.MODEL_TURN and step.turn_finish == NOTE_TURN_FINISH and bool(step.model_text)
        is_tool_call = step.step_kind == ChatRunStepKind.TOOL_CALL
        return RunStepView(
            run_step_id=step.run_step_id, sequence_number=step.sequence_number, kind=step.step_kind, status=step.step_status, started_at=step.started_at,
            duration_milliseconds=step.duration_milliseconds, note=step.model_text if is_note else None,
            tool=self._tool_view(step, bound_arguments, readable_application_ids, application_names) if is_tool_call else None,
        )

    @staticmethod
    def _tool_view(step: ChatRunStep, bound_arguments: Mapping[str, str], readable_application_ids: set[str], application_names: Mapping[str, str]) -> RunStepToolView:
        tool_name = step.tool_name or ""
        definition = tool_registry.definition_named(tool_name)
        is_redacted = step.application_id is not None and step.application_id not in readable_application_ids
        output_values: dict[str, Any] = {} if is_redacted else step.output_json or {}
        visible_application_id = None if is_redacted else step.application_id
        flags = OutputFlags.of(output_values)
        records = [] if is_redacted else [RecordReferenceView(kind=record["kind"], id=record["id"], label=record["label"], application_id=record["application_id"]) for record in step.records_json or []]
        return RunStepToolView(
            name=tool_name, bound_argument_names=list(bound_argument_names(definition, bound_arguments)) if definition else [], label=definition.label if definition else tool_name,
            label_key=definition.label_key if definition else f"chat:tools.{tool_name}.label", source=step.tool_source or _FALLBACK_SOURCE,
            presentation=definition.presentation if definition else _FALLBACK_PRESENTATION, citation_code=step.citation_code,
            arguments={} if is_redacted else step.effective_arguments_json or step.requested_arguments_json or {},
            target=RunStepToolTargetView(application_id=visible_application_id, application_name=application_names.get(visible_application_id or ""), records=records),
            summary=output_values.get("summary"), output_preview=_stored_output_preview(output_values), output_character_count=step.output_character_count or 0,
            output_is_truncated=bool(step.output_is_truncated), item_count=step.output_item_count, is_simulated=flags.is_simulated, total_count=flags.total_count,
            is_truncated=flags.is_truncated, masked_value_count=step.masked_value_count or 0,
            injection_flagged=bool(step.injection_flagged), outcome_code=step.outcome_code, outcome_message=None if is_redacted else step.outcome_message, is_redacted=is_redacted,
        )

    async def _answer_view(self, run: ChatAnswerRun) -> AnswerView | None:
        if run.assistant_message_id is None:
            return None
        message = await self.session.get(ConversationMessage, run.assistant_message_id)
        if message is None:
            return None
        payload = message.message_payload_json or {}
        return AnswerView(
            message_id=message.message_id, markdown=message.message_text, citations=[CitationView.model_validate(citation) for citation in payload.get("citations", [])],
            follow_ups=payload.get("followUps", []), is_unverified=bool(payload.get("isUnverified")), is_refusal=bool(payload.get("isRefusal")),
        )

    @staticmethod
    def _error_view(run: ChatAnswerRun, current_user: CurrentUser) -> ProblemSummaryView | None:
        if run.run_status not in (ChatAnswerRunStatus.FAILED, ChatAnswerRunStatus.CANCELLED) or run.error_code is None:
            return None
        stored_parameters = run.error_parameters_json if run.error_parameters_json is not None else {"modelTier": run.model_tier, "reference": run.correlation_id}  # what the live message used
        failure = AskKeiganErrorCatalogue.describe(run.error_code, stored_parameters, current_user.preferred_locale)
        return ProblemSummaryView(
            error_code=failure.error_code, title=failure.title, detail=failure.detail, correlation_id=run.correlation_id, is_retryable=failure.is_retryable, parameters=dict(failure.parameters),
        )


def _stored_output_preview(output_values: Mapping[str, Any]) -> JsonValue:
    """The preview the live event carried for the same output (the rule is ``output_preview``); None for a step with no stored output."""
    if not output_values:
        return None
    preview_characters = get_settings().ask_keigan_tool_output_preview_characters
    if TRUNCATED_OUTPUT_KEY in output_values:
        return str(output_values[TRUNCATED_OUTPUT_KEY])[:preview_characters]
    return output_preview(output_values, output_json_text(output_values), preview_characters)

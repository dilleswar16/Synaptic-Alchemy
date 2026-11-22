"""Writes the trace of one Ask Keigan answer run: the run row, its model turns and tool calls, the answer and the audit row (spec 23, sections 6 and 7.3).

Every write is its own short transaction through ``open_session()`` and is committed before the matching event is published, so a stream reader and a
later snapshot never disagree, and no database session is held while a model or a tool works. Text is masked before it is stored or published; a tool
output larger than ``ASK_KEIGAN_TOOL_OUTPUT_STORED_CHARACTERS`` is cut and marked. The recorder is the only writer of the steps, so step numbers are kept in memory.

The run row, however, can be ended by more than one party (the engine, a stop request, the stale-run sweep of another process, a shutdown). Every end of a run is
therefore one conditional ``UPDATE ... WHERE run_status = 'running'`` and the caller learns whether it won: the loser changes nothing (no message, no audit row,
no event), so a run is ended once, by whoever got there first, and a finished answer is never overwritten.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from dataclasses import replace
from typing import Any, TypeVar, cast

from pydantic import JsonValue
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ask_keigan_errors import AnswerFailure
from keigan.ai.llm_gateway import AgentTurnResult, estimate_token_count
from keigan.ai.tool_registry import AskKeiganScope, ToolDefinition, ToolOutcome, ToolPresentation
from keigan.config.database_config import open_session
from keigan.config.logging_config import current_correlation_id
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus, ConversationScope, MessageAuthorRole, ToolCallingMode
from keigan.services.ask_keigan_events import AnswerEventName, RunEventChannel
from keigan.services.ask_keigan_run_state import AnswerCitation
from keigan.services.audit_service import AuditService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import ensure_utc, utc_now

RowType = TypeVar("RowType")
logger = logging.getLogger(__name__)
TRUNCATED_OUTPUT_KEY = "truncated_output_text"  # a stored output that was cut is kept as {TRUNCATED_OUTPUT_KEY: first characters of its JSON text, plus its trust flags}
IS_SIMULATED_FIELD, TOTAL_COUNT_FIELD, IS_TRUNCATED_FIELD = "is_simulated", "total_count", "is_truncated"  # the output fields the card's trust flags come from
ASSISTANT_DISPLAY_NAME = "Keigan"
ANSWER_RUN_ID_KEY = "answerRunId"  # the key of a message payload that links the message to its answer run
AUDIT_ACTION_NAME = "chat.answer"
AUDIT_TARGET_ENTITY_TYPE = "chat_answer_run"
_OUTCOME_MESSAGE_MAXIMUM_CHARACTERS = ChatRunStep.__table__.c.outcome_message.type.length  # type: ignore[attr-defined]
_ASSISTANT_MESSAGE_DELAY = timedelta(milliseconds=1)  # the answer sorts after the question even when both are written in the same millisecond


def _rows_changed(result: object) -> int:
    """The number of rows an UPDATE matched (``execute`` is typed as the general ``Result``; an UPDATE statement always gives a ``CursorResult``)."""
    return cast(CursorResult[Any], result).rowcount


def output_json_text(output_values: Mapping[str, Any]) -> str:
    """The text a tool output is measured and cut by (``outputCharacterCount``, the stored cut and the live preview)."""
    return json.dumps(output_values, ensure_ascii=False, separators=(",", ":"), default=str)


def output_preview(output_values: Mapping[str, Any], output_text: str, preview_characters: int) -> JsonValue:
    """The output itself when its text fits the preview, otherwise the first characters of the text: the same rule for the live event and for the stored snapshot."""
    return dict(output_values) if len(output_text) <= preview_characters else output_text[:preview_characters]


@dataclass(frozen=True)
class OutputFlags:
    """What a card says about how far an output can be trusted: simulated data, "showing N of M". None when the tool has no such notion. Read from the whole output (or from the
    flags kept beside a cut one), never from a preview that may be only the first characters of the text."""

    is_simulated: bool | None = None
    total_count: int | None = None
    is_truncated: bool | None = None

    @classmethod
    def of(cls, stored_or_whole_output: Mapping[str, Any]) -> OutputFlags:
        is_simulated, total_count, is_truncated = (stored_or_whole_output.get(name) for name in (IS_SIMULATED_FIELD, TOTAL_COUNT_FIELD, IS_TRUNCATED_FIELD))
        return cls(
            is_simulated if isinstance(is_simulated, bool) else None, total_count if isinstance(total_count, int) and not isinstance(total_count, bool) else None,
            is_truncated if isinstance(is_truncated, bool) else None,
        )

    def stored_beside_cut_text(self) -> dict[str, bool | int]:
        return {name: value for name, value in ((IS_SIMULATED_FIELD, self.is_simulated), (TOTAL_COUNT_FIELD, self.total_count), (IS_TRUNCATED_FIELD, self.is_truncated)) if value is not None}


class SkipReason(StrEnum):
    """Why a tool request was recorded but not run. It is stored as the step's ``outcome_code``."""

    TOOL_LIMIT_REACHED = "tool_limit_reached"
    PARALLEL_LIMIT_REACHED = "parallel_limit_reached"
    TOKEN_BUDGET_REACHED = "token_budget_reached"


@dataclass(frozen=True)
class RunSetup:
    """What is decided before the first model turn: the code and prompt versions, the offered tools, the model and the effective limits."""

    engine_version: str
    prompt_key: str
    prompt_version: str
    system_prompt_sha256: str
    tool_catalog_sha256: str
    offered_tools: list[dict[str, Any]]
    provider_name: str
    model_name: str
    model_tier: str
    tool_calling_mode: ToolCallingMode
    limits: dict[str, Any]


@dataclass(frozen=True)
class QuestionToStore:
    """The question as it is stored: ``masked_text`` is already masked with the run's masker."""

    masked_text: str
    author_display_name: str
    author_user_principal_name: str


@dataclass(frozen=True)
class RunRegistration:
    """Everything needed to store a new ``running`` run and its question. ``answer_run_id`` is chosen by the caller (``new_identifier()``) so the event channel can carry it from the first event."""

    answer_run_id: str
    conversation_id: str
    question: QuestionToStore
    client_request_id: str
    conversation_scope: ConversationScope
    investigation_id: str | None
    requested_by_user_principal_name: str
    scope_snapshot: dict[str, Any]
    setup: RunSetup


@dataclass(frozen=True)
class ToolIdentity:
    name: str
    version: int | None
    source: str | None
    label: str
    label_key: str
    presentation: ToolPresentation

    @classmethod
    def of(cls, definition: ToolDefinition) -> ToolIdentity:
        return cls(definition.name, definition.version, definition.source, definition.label, definition.label_key, definition.presentation)


@dataclass(frozen=True)
class ToolTarget:
    application_id: str | None
    application_name: str | None


@dataclass(frozen=True)
class StepHandle:
    run_step_id: str
    sequence_number: int
    turn_number: int | None
    started_at_monotonic: float


@dataclass(frozen=True)
class RunCompletion:
    markdown: str
    follow_ups: tuple[str, ...]
    citations: tuple[AnswerCitation, ...]
    is_unverified: bool
    is_refusal: bool
    stop_reason: ChatAnswerStopReason


@dataclass
class _RunTotals:
    model_turn_count: int = 0
    tool_call_count: int = 0
    input_token_count: int = 0
    output_token_count: int = 0
    token_counts_estimated: bool = False


@dataclass
class _StoredOutput:
    values: dict[str, Any] | None = None
    character_count: int = 0
    is_truncated: bool = False
    preview: JsonValue = None
    item_count: int | None = None
    summary: str | None = None
    flags: OutputFlags = field(default_factory=OutputFlags)


class TraceRecorder:
    def __init__(self, answer_run_id: str, channel: RunEventChannel, masker: PiiMasker):
        self.answer_run_id = answer_run_id
        self._channel = channel
        self._masker = masker  # the run's masker: the same placeholders as in the question and in every tool output
        self._totals = _RunTotals()
        self._next_sequence_number = 1
        self._started_at_monotonic = time.monotonic()

    @classmethod
    async def begin(cls, registration: RunRegistration, channel: RunEventChannel, masker: PiiMasker) -> TraceRecorder:
        """Store the question and the new ``running`` run in one transaction (committed before it returns) and give back the recorder that writes the rest of the trace.

        Raises ``IntegrityError`` when the database refuses the run: the same ``client_request_id`` was stored already, or the conversation already has a running run.
        Neither the run nor the question is stored then, so a refused run leaves no question behind that points at a run that never existed.
        """
        setup = registration.setup
        async with open_session() as session:
            question = ConversationMessage(
                conversation_id=registration.conversation_id, author_role=MessageAuthorRole.USER, author_display_name=registration.question.author_display_name,
                author_user_principal_name=registration.question.author_user_principal_name, message_text=registration.question.masked_text,
                message_payload_json={ANSWER_RUN_ID_KEY: registration.answer_run_id}, input_token_count=estimate_token_count(registration.question.masked_text), output_token_count=0,
                created_at=utc_now(),
            )
            session.add(question)
            await session.flush()
            session.add(ChatAnswerRun(
                answer_run_id=registration.answer_run_id, conversation_id=registration.conversation_id, user_message_id=question.message_id,
                client_request_id=registration.client_request_id, conversation_scope=registration.conversation_scope, investigation_id=registration.investigation_id,
                requested_by_user_principal_name=registration.requested_by_user_principal_name, scope_snapshot_json=registration.scope_snapshot, run_status=ChatAnswerRunStatus.RUNNING,
                engine_version=setup.engine_version, prompt_key=setup.prompt_key, prompt_version=setup.prompt_version, system_prompt_sha256=setup.system_prompt_sha256,
                tool_catalog_sha256=setup.tool_catalog_sha256, offered_tools_json=setup.offered_tools, provider_name=setup.provider_name, model_name=setup.model_name,
                model_tier=setup.model_tier, tool_calling_mode=setup.tool_calling_mode, limits_json=setup.limits, correlation_id=current_correlation_id() or None,
            ))
        return cls(registration.answer_run_id, channel, masker)

    @classmethod
    def for_interrupted_run(cls, answer_run_id: str, started_at: datetime) -> TraceRecorder:
        """A recorder for a run whose engine is gone (the process restarted or shut down): it can only end the run, with the duration counted from ``started_at``.
        Its event channel is closed, so nothing is published."""
        channel = RunEventChannel(answer_run_id)
        channel.close()
        recorder = cls(answer_run_id, channel, PiiMasker())
        recorder._started_at_monotonic = time.monotonic() - (utc_now() - (ensure_utc(started_at) or utc_now())).total_seconds()
        return recorder

    # ── Start ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def record_start(self, *, scope: AskKeiganScope, offered_tools: Sequence[ToolDefinition], maximum_tool_calls: int) -> None:
        """Publish ``answer.started``: the question as stored, the scope, the tools on offer and the tool-call limit."""
        async with open_session() as session:
            run = await self._run_row(session)
            question = self._existing(await session.get(ConversationMessage, run.user_message_id), "question")
            await self._touch(session)
        self._publish(AnswerEventName.ANSWER_STARTED, {
            "userMessage": {"messageId": question.message_id, "messageText": question.message_text, "createdAt": question.created_at.isoformat()},
            "scope": scope.value, "maximumToolCalls": maximum_tool_calls,
            "offeredTools": [{"name": tool.name, "label": tool.label, "labelKey": tool.label_key} for tool in offered_tools],
        })

    # ── Model turns ───────────────────────────────────────────────────────────────────────────────────────────────────────
    def publish_answer_text(self, turn_number: int, paragraph: str) -> None:
        """Publish one finished, sanitised paragraph of the text a model turn is streaming (``answer.text``). Nothing is stored: the turn's whole text is stored when it ends."""
        self._publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": turn_number, "text": self._masker.mask_text(paragraph)})

    def close_events(self) -> None:
        """The run is over: a reader of the event channel receives what is queued and stops."""
        self._channel.close()

    async def start_model_turn(self, turn_number: int) -> StepHandle:
        return await self._start_step(ChatRunStep(step_kind=ChatRunStepKind.MODEL_TURN, step_status=ChatRunStepStatus.RUNNING, turn_number=turn_number), turn_number)

    async def finish_model_turn(self, handle: StepHandle, result: AgentTurnResult, *, model_text: str, is_note: bool) -> None:
        """Store the turn's tokens, finish reason and (masked) text. ``is_note``: the turn asked for tools, so its text is shown in the trace, not as the answer."""
        masked_text = self._masker.mask_text(model_text)
        self._totals.model_turn_count += 1
        self._totals.input_token_count += result.input_token_count
        self._totals.output_token_count += result.output_token_count
        self._totals.token_counts_estimated = self._totals.token_counts_estimated or result.token_counts_estimated
        async with open_session() as session:
            await session.execute(update(ChatRunStep).where(ChatRunStep.run_step_id == handle.run_step_id).values(
                step_status=ChatRunStepStatus.SUCCEEDED, completed_at=utc_now(), duration_milliseconds=self._elapsed_milliseconds(handle), turn_finish=result.finish, model_text=masked_text,
                input_token_count=result.input_token_count, output_token_count=result.output_token_count,
            ))
            run = await self._run_row(session)
            run.model_turn_count, run.total_input_token_count, run.total_output_token_count = self._totals.model_turn_count, self._totals.input_token_count, self._totals.output_token_count
            run.token_counts_estimated, run.model_name, run.tool_calling_mode = self._totals.token_counts_estimated, result.model_name, result.tool_calling_mode
            await self._touch(session)
        if is_note and masked_text:
            self._publish(AnswerEventName.TURN_NOTE, {"turnNumber": handle.turn_number, "runStepId": handle.run_step_id, "sequenceNumber": handle.sequence_number, "text": masked_text})

    # ── Tool calls ────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def start_tool_call(
        self, *, parent: StepHandle, request_id: str, tool: ToolIdentity, citation_code: str | None, requested_arguments: Mapping[str, Any], effective_arguments: Mapping[str, Any], target: ToolTarget,
        bound_argument_names: Sequence[str],
    ) -> StepHandle:
        """Store the call as ``running`` and publish ``tool.started``. ``effective_arguments``: what the model asked for with the scope's bound arguments applied (``bound_argument_names``)."""
        masked_requested, masked_effective = self._masker.mask_value(dict(requested_arguments)), self._masker.mask_value(dict(effective_arguments))
        handle = await self._start_step(
            ChatRunStep(
                step_kind=ChatRunStepKind.TOOL_CALL, step_status=ChatRunStepStatus.RUNNING, parent_run_step_id=parent.run_step_id, tool_name=tool.name, tool_version=tool.version,
                tool_source=tool.source, citation_code=citation_code, provider_request_id=request_id, requested_arguments_json=masked_requested, effective_arguments_json=masked_effective,
            ),
            None,
        )
        self._publish_tool_started(handle, parent, tool, citation_code, masked_effective, target, bound_argument_names)
        return handle

    async def record_tool_progress(self, handle: StepHandle, stage: str, detail: Mapping[str, Any]) -> None:
        async with open_session() as session:
            await self._touch(session)
        self._publish(AnswerEventName.TOOL_PROGRESS, {"runStepId": handle.run_step_id, "sequenceNumber": handle.sequence_number, "stage": stage, "detail": self._masker.mask_value(dict(detail))})

    async def finish_tool_call(self, handle: StepHandle, outcome: ToolOutcome, masked_value_count: int) -> None:
        stored = self._stored_output(outcome)
        masked_outcome_message = self._masker.mask_text(outcome.outcome_message)[:_OUTCOME_MESSAGE_MAXIMUM_CHARACTERS] if outcome.outcome_message else None
        records = [record.model_dump(mode="json") for record in outcome.records]
        duration_milliseconds = self._elapsed_milliseconds(handle)
        self._totals.tool_call_count += 1
        async with open_session() as session:
            await session.execute(update(ChatRunStep).where(ChatRunStep.run_step_id == handle.run_step_id).values(
                step_status=outcome.status, completed_at=utc_now(), duration_milliseconds=duration_milliseconds, application_id=outcome.application_id, records_json=records,
                output_json=stored.values, output_character_count=stored.character_count, output_is_truncated=stored.is_truncated, output_item_count=stored.item_count,
                model_view_text=outcome.model_view_text, model_view_sha256=outcome.model_view_sha256, masked_value_count=masked_value_count, injection_flagged=outcome.injection_flagged,
                outcome_code=outcome.outcome_code, outcome_message=masked_outcome_message,
            ))
            (await self._run_row(session)).tool_call_count = self._totals.tool_call_count
            await self._touch(session)
        self._publish_tool_finished(handle, outcome.status, duration_milliseconds, stored, records, masked_value_count, outcome.injection_flagged, outcome.outcome_code, masked_outcome_message)

    async def record_skipped_tool_call(
        self, *, parent: StepHandle, request_id: str, tool: ToolIdentity, requested_arguments: Mapping[str, Any], target: ToolTarget, bound_argument_names: Sequence[str],
        reason: SkipReason, outcome_message: str | None = None,
    ) -> StepHandle:
        """A request the engine did not run (over a limit). It still gets a card, so the person sees what the model wanted; it uses no citation code and does not count as a tool call."""
        masked_arguments = self._masker.mask_value(dict(requested_arguments))
        masked_message = self._masker.mask_text(outcome_message)[:_OUTCOME_MESSAGE_MAXIMUM_CHARACTERS] if outcome_message else None
        handle = await self._start_step(
            ChatRunStep(
                step_kind=ChatRunStepKind.TOOL_CALL, step_status=ChatRunStepStatus.SKIPPED, parent_run_step_id=parent.run_step_id, tool_name=tool.name, tool_version=tool.version,
                tool_source=tool.source, provider_request_id=request_id, requested_arguments_json=masked_arguments, completed_at=utc_now(), duration_milliseconds=0,
                outcome_code=reason, outcome_message=masked_message,
            ),
            None,
        )
        self._publish_tool_started(handle, parent, tool, None, masked_arguments, target, bound_argument_names)
        self._publish_tool_finished(handle, ChatRunStepStatus.SKIPPED, 0, _StoredOutput(), [], 0, False, reason, masked_message)
        return handle

    # ── Ending the run ────────────────────────────────────────────────────────────────────────────────────────────────────
    async def complete_run(self, completion: RunCompletion) -> str | None:
        """Finish the run, store the assistant message and write the audit row (one transaction), then publish ``answer.completed``. Returns the id of the assistant message.

        Returns None, having written and published nothing, when the run was no longer ``running``: it was ended by a stop request, an interruption or a shutdown first.
        """
        masked_markdown = self._masker.mask_text(completion.markdown)
        masked_follow_ups = [self._masker.mask_text(follow_up) for follow_up in completion.follow_ups]
        citation_payloads = [replace(citation, title=self._masker.mask_text(citation.title)).as_payload() for citation in completion.citations]
        answer_payload: dict[str, Any] = {
            "citations": citation_payloads, "followUps": masked_follow_ups, "isUnverified": completion.is_unverified, "isRefusal": completion.is_refusal,
        }
        async with open_session() as session:
            duration_milliseconds = await self._claim_run_end(session, ChatAnswerRunStatus.COMPLETED, completion.stop_reason, error_code=None)
            if duration_milliseconds is None:
                return None
            run = await self._run_row(session)
            assistant_message = ConversationMessage(
                conversation_id=run.conversation_id, author_role=MessageAuthorRole.ASSISTANT, author_display_name=ASSISTANT_DISPLAY_NAME, message_text=masked_markdown,
                message_payload_json={"answerRunId": run.answer_run_id, **answer_payload, "stopReason": completion.stop_reason.value}, input_token_count=self._totals.input_token_count,
                output_token_count=self._totals.output_token_count, created_at=utc_now() + _ASSISTANT_MESSAGE_DELAY,
            )
            session.add(assistant_message)
            await session.flush()
            run.assistant_message_id = assistant_message.message_id
            run.citations_json, run.follow_up_questions_json, run.is_unverified = citation_payloads, masked_follow_ups, completion.is_unverified
            await self._mark_conversation_updated(session, run)
            await self._record_audit(session, run)
        self._publish(AnswerEventName.ANSWER_COMPLETED, {
            "answer": {"messageId": assistant_message.message_id, "markdown": masked_markdown, **answer_payload}, "stopReason": completion.stop_reason.value,
            "toolCallCount": self._totals.tool_call_count, "inputTokenCount": self._totals.input_token_count, "outputTokenCount": self._totals.output_token_count,
            "durationMilliseconds": duration_milliseconds,
        })
        return assistant_message.message_id

    async def fail_run(self, failure: AnswerFailure) -> bool:
        """End the run as failed. False, with nothing written or published, when the run was no longer ``running``."""
        return await self._end_without_answer(failure, ChatAnswerRunStatus.FAILED, ChatAnswerStopReason.FAILED, only_if_silent_since=None)

    async def cancel_run(self, failure: AnswerFailure) -> bool:
        """The person stopped the answer. ``failure`` is the catalogue's ``cancelled`` row. False, with nothing written or published, when the run was no longer ``running``."""
        return await self._end_without_answer(failure, ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, only_if_silent_since=None)

    async def interrupt_run(self, failure: AnswerFailure, *, only_if_silent_since: datetime | None) -> bool:
        """End a run nothing works on as failed. ``only_if_silent_since``: leave it running when it made progress after that moment (the reader judged it silent from an older
        read, and it has beaten since). None for a run known to be dead, such as one cut off by this process's own shutdown. False when it was not ended."""
        return await self._end_without_answer(failure, ChatAnswerRunStatus.FAILED, ChatAnswerStopReason.FAILED, only_if_silent_since=only_if_silent_since)

    async def is_cancel_requested(self) -> bool:
        """A stop request stored by another pod (``cancel_requested_at``)."""
        async with open_session() as session:
            return (await self._run_row(session)).cancel_requested_at is not None

    @staticmethod
    async def store_cancel_request(answer_run_id: str) -> bool:
        """Store a stop request for a run that may live in another pod, in its own committed transaction (it is written, then the in-process flag is set). Asking again keeps the first
        time. False when the run is no longer ``running``."""
        async with open_session() as session:
            result = await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == answer_run_id, ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING).values(
                cancel_requested_at=func.coalesce(ChatAnswerRun.cancel_requested_at, utc_now()),
            ).execution_options(synchronize_session=False))
        return _rows_changed(result) == 1

    async def touch_progress(self) -> bool:
        """The heartbeat: say the answer is alive. False when the run is no longer ``running`` (an ended run is never touched again)."""
        async with open_session() as session:
            result = await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == self.answer_run_id, ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING).values(
                last_progress_at=utc_now(),
            ).execution_options(synchronize_session=False))
        return _rows_changed(result) == 1

    # ── Internals ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _end_without_answer(
        self, failure: AnswerFailure, status: ChatAnswerRunStatus, stop_reason: ChatAnswerStopReason, *, only_if_silent_since: datetime | None,
    ) -> bool:
        async with open_session() as session:
            claimed = await self._claim_run_end(
                session, status, stop_reason, error_code=failure.error_code, error_parameters=dict(failure.parameters), only_if_silent_since=only_if_silent_since,
            )
            if claimed is None:
                return False
            await session.execute(update(ChatRunStep).where(ChatRunStep.answer_run_id == self.answer_run_id, ChatRunStep.step_status == ChatRunStepStatus.RUNNING).values(
                step_status=ChatRunStepStatus.CANCELLED, completed_at=utc_now(),
            ))
            run = await self._run_row(session)
            question = self._existing(await session.get(ConversationMessage, run.user_message_id), "question")
            question.message_payload_json = {**(question.message_payload_json or {}), "answerRunId": run.answer_run_id}  # so a reload shows the run next to the question
            await self._mark_conversation_updated(session, run)
            await self._record_audit(session, run)
        self._publish(AnswerEventName.ANSWER_FAILED, {
            "error": {
                "errorCode": failure.error_code, "title": failure.title, "detail": failure.detail, "correlationId": current_correlation_id() or None, "isRetryable": failure.is_retryable,
                "parameters": dict(failure.parameters),
            },
            "stopReason": stop_reason.value,
        })
        return True

    async def _claim_run_end(
        self, session: AsyncSession, status: ChatAnswerRunStatus, stop_reason: ChatAnswerStopReason, *, error_code: str | None, error_parameters: dict[str, Any] | None = None,
        only_if_silent_since: datetime | None = None,
    ) -> int | None:
        """Move the run from ``running`` to its end state with one conditional UPDATE (the first statement of the caller's transaction, so a loser writes nothing else).

        Returns the run's duration in milliseconds when this call ended the run, and None when it did not: the run was no longer ``running`` (ended by someone else, which is
        logged and left alone), or it had made progress after ``only_if_silent_since``.
        """
        duration_milliseconds = int((time.monotonic() - self._started_at_monotonic) * 1000)
        ended_at = utc_now()
        conditions = [ChatAnswerRun.answer_run_id == self.answer_run_id, ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING]
        if only_if_silent_since is not None:
            conditions.append(ChatAnswerRun.last_progress_at <= only_if_silent_since)
        result = await session.execute(update(ChatAnswerRun).where(*conditions).values(
            run_status=status, stop_reason=stop_reason, error_code=error_code, error_parameters_json=error_parameters, completed_at=ended_at, duration_milliseconds=duration_milliseconds,
            last_progress_at=ended_at,
        ).execution_options(synchronize_session=False))
        if _rows_changed(result) == 1:
            return duration_milliseconds
        logger.info("Answer run %s was not ended as %s: it is no longer running or made progress meanwhile; what ended it first stays.", self.answer_run_id, status.value)
        return None

    async def _mark_conversation_updated(self, session: AsyncSession, run: ChatAnswerRun) -> None:
        conversation = self._existing(await session.get(Conversation, run.conversation_id), "conversation")
        conversation.updated_by_user_principal_name, conversation.updated_at = run.requested_by_user_principal_name, utc_now()

    async def _record_audit(self, session: AsyncSession, run: ChatAnswerRun) -> None:
        """The durable summary of what the run read (no content): it survives the deletion of the conversation and its trace."""
        called_tools = (await session.execute(
            select(ChatRunStep.tool_name, ChatRunStep.application_id)
            .where(ChatRunStep.answer_run_id == run.answer_run_id, ChatRunStep.step_kind == ChatRunStepKind.TOOL_CALL, ChatRunStep.step_status != ChatRunStepStatus.SKIPPED)
            .order_by(ChatRunStep.sequence_number)
        )).all()
        tool_names = list(dict.fromkeys(tool_name for tool_name, _ in called_tools))
        application_ids = sorted({application_id for _, application_id in called_tools if application_id})
        await AuditService(session).record(
            run.requested_by_user_principal_name, AUDIT_ACTION_NAME, target_entity_type=AUDIT_TARGET_ENTITY_TYPE, target_entity_id=run.answer_run_id,
            application_id=application_ids[0] if len(application_ids) == 1 else None,
            action_details={
                "scope": run.conversation_scope, "toolNames": tool_names, "applicationIds": application_ids, "stopReason": run.stop_reason, "toolCallCount": run.tool_call_count,
                "conversationId": run.conversation_id,
            },
        )

    async def _start_step(self, step: ChatRunStep, turn_number: int | None) -> StepHandle:
        step.answer_run_id, step.sequence_number = self.answer_run_id, self._next_sequence_number
        async with open_session() as session:
            session.add(step)
            await session.flush()
            await self._touch(session)
            run_step_id = step.run_step_id
        self._next_sequence_number += 1
        return StepHandle(run_step_id, step.sequence_number, turn_number, time.monotonic())

    async def _run_row(self, session: AsyncSession) -> ChatAnswerRun:
        return self._existing(await session.get(ChatAnswerRun, self.answer_run_id), "run")

    @staticmethod
    def _existing(row: RowType | None, description: str) -> RowType:
        """The rows of a run are created before the recorder is used and are only removed with the whole conversation, so a missing one is a bug, not a user error."""
        if row is None:
            raise LookupError(f"The {description} of this answer run no longer exists.")
        return row

    async def _touch(self, session: AsyncSession) -> None:
        """``last_progress_at`` is what tells a stale run (a restarted pod) from a slow one."""
        (await self._run_row(session)).last_progress_at = utc_now()

    @staticmethod
    def _elapsed_milliseconds(handle: StepHandle) -> int:
        return int((time.monotonic() - handle.started_at_monotonic) * 1000)

    def _stored_output(self, outcome: ToolOutcome) -> _StoredOutput:
        if outcome.output is None:
            return _StoredOutput()
        settings = get_settings()
        output_values: dict[str, Any] = self._masker.mask_value(outcome.output.model_dump(mode="json"))
        output_text = output_json_text(output_values)
        is_truncated = len(output_text) > settings.ask_keigan_tool_output_stored_characters
        flags = OutputFlags.of(output_values)
        return _StoredOutput(
            values={TRUNCATED_OUTPUT_KEY: output_text[:settings.ask_keigan_tool_output_stored_characters], **flags.stored_beside_cut_text()} if is_truncated else output_values,
            character_count=len(output_text), is_truncated=is_truncated, preview=output_preview(output_values, output_text, settings.ask_keigan_tool_output_preview_characters),
            item_count=output_values.get("item_count"), summary=output_values.get("summary"), flags=flags,
        )

    def _publish_tool_started(
        self, handle: StepHandle, parent: StepHandle, tool: ToolIdentity, citation_code: str | None, arguments: Mapping[str, Any], target: ToolTarget, bound_argument_names: Sequence[str],
    ) -> None:
        self._publish(AnswerEventName.TOOL_STARTED, {
            "runStepId": handle.run_step_id, "sequenceNumber": handle.sequence_number, "parentRunStepId": parent.run_step_id, "citationCode": citation_code,
            "boundArgumentNames": list(bound_argument_names),
            "tool": {"name": tool.name, "label": tool.label, "labelKey": tool.label_key, "source": tool.source, "presentation": tool.presentation.value},
            "arguments": dict(arguments), "target": {"applicationId": target.application_id, "applicationName": target.application_name},
        })

    def _publish_tool_finished(
        self, handle: StepHandle, status: ChatRunStepStatus, duration_milliseconds: int, stored: _StoredOutput, records: list[dict[str, Any]], masked_value_count: int,
        injection_flagged: bool, outcome_code: str | None, outcome_message: str | None,
    ) -> None:
        self._publish(AnswerEventName.TOOL_FINISHED, {
            "runStepId": handle.run_step_id, "sequenceNumber": handle.sequence_number, "status": status.value, "durationMilliseconds": duration_milliseconds, "summary": stored.summary,
            "outputPreview": stored.preview, "outputCharacterCount": stored.character_count, "outputIsTruncated": stored.is_truncated, "itemCount": stored.item_count,
            "isSimulated": stored.flags.is_simulated, "totalCount": stored.flags.total_count, "isTruncated": stored.flags.is_truncated,
            "records": [{"kind": record["kind"], "id": record["id"], "label": record["label"], "applicationId": record["application_id"]} for record in records],
            "maskedValueCount": masked_value_count, "injectionFlagged": injection_flagged, "outcomeCode": outcome_code, "outcomeMessage": outcome_message,
        })

    def _publish(self, name: AnswerEventName, fields: Mapping[str, Any]) -> None:
        self._channel.publish(name, fields)

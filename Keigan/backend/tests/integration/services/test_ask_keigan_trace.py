"""keigan/services/ask_keigan_trace.py: the stored trace of an answer run, written in short transactions, masked, size-capped and published as events (spec 23, 6, 7.3, AC-9)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import AgentTurnResult
from keigan.ai.tool_registry import AskKeiganScope, RecordReference, ToolOutcome, ToolPresentation, tool_registry
from keigan.config.database_config import open_session
from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import get_settings
from keigan.entities.base_entity import new_identifier
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.platform_entities import AuditEvent
from keigan.entities.status_values import (
    ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus, ConversationScope, MessageAuthorRole, ToolCallingMode,
)
from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName, RunEventChannel
from keigan.services.ask_keigan_run_state import AnswerCitation
from keigan.services.ask_keigan_trace import (
    TRUNCATED_OUTPUT_KEY, QuestionToStore, RunCompletion, RunRegistration, RunSetup, SkipReason, StepHandle, ToolIdentity, ToolTarget, TraceRecorder,
)
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from support.ask_keigan_conversations import runs_of
from keigan.utils.pii_masker import PiiMasker

pytestmark = pytest.mark.usefixtures("seed_context")

OWNER = "rui.reader@keigan.local"
SETUP = RunSetup(
    engine_version="1", prompt_key="ask_keigan_investigation", prompt_version="1", system_prompt_sha256="a" * 64, tool_catalog_sha256="b" * 64,
    offered_tools=[{"name": "get_evidence", "version": 1, "source": "keigan", "schemaSha256": "c" * 64}], provider_name="mock", model_name="mock", model_tier="deep",
    tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK, limits={"maximumToolCalls": 6},
)
EVIDENCE_TOOL = ToolIdentity(name="get_evidence", version=1, source="keigan", label="Opened evidence", label_key="chat:tools.get_evidence.label", presentation=ToolPresentation.RECORD)
TARGET = ToolTarget(application_id="app-1", application_name="Claims Processing (JP)")


class SampleOutput(BaseModel):
    summary: str
    detail: str
    item_count: int = 2
    records: list[RecordReference] = []


@dataclass
class Started:
    recorder: TraceRecorder
    channel: RunEventChannel
    run_id: str
    conversation_id: str
    user_message_id: str


async def new_conversation() -> str:
    async with open_session() as session:
        conversation = Conversation(conversation_scope=ConversationScope.KEIGAN_AI_CHAT, owner_user_principal_name=OWNER)
        session.add(conversation)
        await session.flush()
        return conversation.conversation_id


def registration_for(conversation_id: str, *, client_request_id: str | None = None, question_text: str = "Which SLOs are at risk?") -> RunRegistration:
    return RunRegistration(
        answer_run_id=new_identifier(), conversation_id=conversation_id, question=QuestionToStore(question_text, "Rui Reader", OWNER), client_request_id=client_request_id or uuid.uuid4().hex,
        conversation_scope=ConversationScope.KEIGAN_AI_CHAT, investigation_id=None, requested_by_user_principal_name=OWNER,
        scope_snapshot={"scope": "global", "applications": [], "boundArguments": {}, "withheldTools": []}, setup=SETUP,
    )


async def begin_run(*, queue_size: int = 100) -> Started:
    conversation_id = await new_conversation()
    set_correlation_id("corr-trace-test")
    registration = registration_for(conversation_id)
    channel = RunEventChannel(registration.answer_run_id, maximum_queued_events=queue_size)
    recorder = await TraceRecorder.begin(registration, channel, PiiMasker())
    return Started(recorder, channel, recorder.answer_run_id, conversation_id, (await load_run(recorder.answer_run_id)).user_message_id)


async def messages_of(conversation_id: str) -> list[ConversationMessage]:
    async with open_session() as session:
        return list((await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))).all())


async def audit_rows_of(run_id: str) -> list[AuditEvent]:
    async with open_session() as session:
        return list((await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == run_id))).all())


def drain(channel: RunEventChannel) -> list[AnswerEvent]:
    events: list[AnswerEvent] = []
    while not channel._queue.empty():  # noqa: SLF001 — the channel is read without a task here
        item = channel._queue.get_nowait()  # noqa: SLF001
        if isinstance(item, AnswerEvent):
            events.append(item)
    return events


async def load_run(run_id: str) -> ChatAnswerRun:
    async with open_session() as session:
        return await session.get(ChatAnswerRun, run_id)


async def load_steps(run_id: str) -> list[ChatRunStep]:
    async with open_session() as session:
        return list((await session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == run_id).order_by(ChatRunStep.sequence_number))).all())


def turn_result(text: str = "Checking.", finish: str = "tool_requests", input_tokens: int = 100, output_tokens: int = 10, estimated: bool = False) -> AgentTurnResult:
    return AgentTurnResult(
        text=text, tool_requests=(), finish=finish, input_token_count=input_tokens, output_token_count=output_tokens, token_counts_estimated=estimated, model_name="mock-model",
        tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK,
    )


def succeeded(output: BaseModel, *, model_view: str = '{"summary":"x"}', flagged: bool = False, records: list[RecordReference] | None = None) -> ToolOutcome:
    return ToolOutcome(
        status=ChatRunStepStatus.SUCCEEDED, output=output, application_id="app-1", records=records or [], outcome_code=None, outcome_message=None, model_view_text=model_view,
        model_view_sha256=hashlib.sha256(model_view.encode()).hexdigest(), model_message="<wrapped>", injection_flagged=flagged,
    )


async def run_one_tool_call(started: Started, outcome: ToolOutcome, *, arguments: dict | None = None, citation_code: str | None = "T1") -> StepHandle:
    turn = await started.recorder.start_model_turn(1)
    await started.recorder.finish_model_turn(turn, turn_result(), model_text="Checking.", is_note=True)
    step = await started.recorder.start_tool_call(
        parent=turn, request_id="call_1", tool=EVIDENCE_TOOL, citation_code=citation_code, requested_arguments=arguments or {"evidence_code": "E1"},
        effective_arguments=arguments or {"evidence_code": "E1"}, target=TARGET, bound_argument_names=(),
    )
    await started.recorder.finish_tool_call(step, outcome, masked_value_count=0)
    return step


# ── The run row ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_beginning_a_run_stores_a_running_row_with_everything_known_before_the_first_model_turn() -> None:
    started = await begin_run()
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.conversation_scope, run.requested_by_user_principal_name) == (ChatAnswerRunStatus.RUNNING, None, "keigan_ai_chat", OWNER)
    assert (run.engine_version, run.prompt_key, run.prompt_version, run.system_prompt_sha256, run.tool_catalog_sha256) == ("1", "ask_keigan_investigation", "1", "a" * 64, "b" * 64)
    assert (run.provider_name, run.model_name, run.model_tier, run.tool_calling_mode, run.limits_json) == ("mock", "mock", "deep", "scripted_mock", {"maximumToolCalls": 6})
    assert run.offered_tools_json == SETUP.offered_tools and run.scope_snapshot_json == {"scope": "global", "applications": [], "boundArguments": {}, "withheldTools": []}
    assert (run.user_message_id, run.conversation_id, run.correlation_id, run.cancel_requested_at) == (started.user_message_id, started.conversation_id, "corr-trace-test", None)
    assert (run.model_turn_count, run.tool_call_count, run.total_input_token_count, run.total_output_token_count) == (0, 0, 0, 0)
    assert started.recorder.answer_run_id == run.answer_run_id


async def test_a_run_begins_with_no_application_used_and_each_succeeded_call_adds_the_applications_it_read() -> None:
    started = await begin_run()
    assert (await load_run(started.run_id)).used_application_ids_json == []
    await run_one_tool_call(started, replace(succeeded(SampleOutput(summary="x", detail="y")), applications_read=frozenset({"app-2", "app-1"})))
    assert (await load_run(started.run_id)).used_application_ids_json == ["app-1", "app-2"]
    turn = await started.recorder.start_model_turn(2)
    second = await started.recorder.start_tool_call(
        parent=turn, request_id="call_2", tool=EVIDENCE_TOOL, citation_code="T2", requested_arguments={}, effective_arguments={}, target=TARGET, bound_argument_names=(),
    )
    await started.recorder.finish_tool_call(second, replace(succeeded(SampleOutput(summary="x", detail="y")), applications_read=frozenset({"app-3", "app-1"})), masked_value_count=0)
    assert (await load_run(started.run_id)).used_application_ids_json == ["app-1", "app-2", "app-3"]


async def test_a_call_that_gave_no_data_and_a_skipped_request_use_no_application() -> None:
    started = await begin_run()
    refused = ToolOutcome(
        status=ChatRunStepStatus.REFUSED, output=None, application_id="app-9", records=[], outcome_code="access_denied", outcome_message="You can't read that.", model_message="refused",
        applications_read=frozenset({"app-9"}),  # a refusal names the application it concerned, but no data of it reached the model
    )
    turn = await started.recorder.start_model_turn(1)
    step = await started.recorder.start_tool_call(
        parent=turn, request_id="call_1", tool=EVIDENCE_TOOL, citation_code="T1", requested_arguments={}, effective_arguments={}, target=TARGET, bound_argument_names=(),
    )
    await started.recorder.finish_tool_call(step, refused, masked_value_count=0)
    await started.recorder.record_skipped_tool_call(
        parent=turn, request_id="call_2", tool=EVIDENCE_TOOL, requested_arguments={}, target=TARGET, bound_argument_names=(), reason=SkipReason.TOOL_LIMIT_REACHED,
    )
    assert (await load_run(started.run_id)).used_application_ids_json == []


async def test_the_start_event_tells_the_screen_the_question_the_tools_and_the_limit() -> None:
    started = await begin_run()
    offered = tuple(tool_registry.tools_for(AskKeiganScope.INVESTIGATION))
    await started.recorder.record_start(scope=AskKeiganScope.INVESTIGATION, offered_tools=offered, maximum_tool_calls=6)
    (event,) = drain(started.channel)
    assert event.name is AnswerEventName.ANSWER_STARTED and event.sequence == 1 and event.data["answerRunId"] == started.run_id
    assert event.data["userMessage"]["messageId"] == started.user_message_id and event.data["userMessage"]["messageText"] == "Which SLOs are at risk?"
    assert event.data["scope"] == "investigation" and event.data["maximumToolCalls"] == 6
    assert {"name": "get_evidence", "label": "Opened evidence", "labelKey": "chat:tools.get_evidence.label"} in event.data["offeredTools"]


# ── Model turns ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_streamed_paragraphs_are_published_masked_and_numbered_with_their_turn_and_the_channel_can_be_closed() -> None:
    started = await begin_run()
    started.recorder.publish_answer_text(2, "Ask ops.lead@keigan.local to check.")
    started.recorder.close_events()
    (event,) = [event async for event in started.channel.events()]
    assert event.name is AnswerEventName.ANSWER_TEXT and event.data["turnNumber"] == 2 and event.data["text"] == "Ask <EMAIL_1> to check."
    assert started.channel.is_open is False


async def test_a_model_turn_is_stored_with_its_tokens_and_adds_to_the_totals_of_the_run() -> None:
    started = await begin_run()
    first = await started.recorder.start_model_turn(1)
    assert (first.sequence_number) == 1
    (running,) = await load_steps(started.run_id)
    assert (running.step_kind, running.step_status, running.turn_number) == (ChatRunStepKind.MODEL_TURN, ChatRunStepStatus.RUNNING, 1)  # visible before the turn ends: short transactions
    await started.recorder.finish_model_turn(first, turn_result("Checking the SLOs.", input_tokens=100, output_tokens=10), model_text="Checking the SLOs.", is_note=False)
    second = await started.recorder.start_model_turn(2)
    await started.recorder.finish_model_turn(second, turn_result("Done.", finish="answer", input_tokens=200, output_tokens=20, estimated=True), model_text="Done.", is_note=False)
    first_row, second_row = await load_steps(started.run_id)
    assert (first_row.step_status, first_row.turn_finish, first_row.model_text, first_row.input_token_count, first_row.output_token_count) == (ChatRunStepStatus.SUCCEEDED, "tool_requests", "Checking the SLOs.", 100, 10)
    assert first_row.completed_at is not None and first_row.duration_milliseconds is not None and second_row.sequence_number == 2
    run = await load_run(started.run_id)
    assert (run.model_turn_count, run.total_input_token_count, run.total_output_token_count, run.token_counts_estimated, run.model_name) == (2, 300, 30, True, "mock-model")


async def test_the_text_of_a_turn_that_asked_for_tools_is_published_as_a_note_and_other_text_is_not() -> None:
    started = await begin_run()
    note_turn = await started.recorder.start_model_turn(1)
    await started.recorder.finish_model_turn(note_turn, turn_result("Checking the SLOs first."), model_text="Checking the SLOs first.", is_note=True)
    answer_turn = await started.recorder.start_model_turn(2)
    await started.recorder.finish_model_turn(answer_turn, turn_result("Final.", finish="answer"), model_text="Final.", is_note=False)
    (note,) = drain(started.channel)
    assert note.name is AnswerEventName.TURN_NOTE
    assert (note.data["turnNumber"], note.data["runStepId"], note.data["text"]) == (1, note_turn.run_step_id, "Checking the SLOs first.")


async def test_model_text_is_masked_before_it_is_stored_or_published() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    await started.recorder.finish_model_turn(turn, turn_result(), model_text="Ask ops.lead@keigan.local to check.", is_note=True)
    assert (await load_steps(started.run_id))[0].model_text == "Ask <EMAIL_1> to check."
    assert drain(started.channel)[0].data["text"] == "Ask <EMAIL_1> to check."


# ── Tool calls ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_a_tool_call_is_visible_while_it_runs_and_announced_with_its_arguments_and_target() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    step = await started.recorder.start_tool_call(
        parent=turn, request_id="call_1", tool=EVIDENCE_TOOL, citation_code="T1", requested_arguments={"evidence_code": "e1", "investigation_id": "invented"},
        effective_arguments={"evidence_code": "e1", "investigation_id": "i-1"}, target=TARGET, bound_argument_names=("investigation_id",),
    )
    (turn_row, running) = await load_steps(started.run_id)
    assert (running.step_kind, running.step_status, running.parent_run_step_id, running.sequence_number) == (ChatRunStepKind.TOOL_CALL, ChatRunStepStatus.RUNNING, turn.run_step_id, 2)
    assert (running.tool_name, running.tool_version, running.tool_source, running.citation_code, running.provider_request_id) == ("get_evidence", 1, "keigan", "T1", "call_1")
    assert running.requested_arguments_json == {"evidence_code": "e1", "investigation_id": "invented"} and running.effective_arguments_json == {"evidence_code": "e1", "investigation_id": "i-1"}
    (event,) = drain(started.channel)
    assert event.name is AnswerEventName.TOOL_STARTED
    assert event.data["runStepId"] == step.run_step_id and event.data["parentRunStepId"] == turn.run_step_id and event.data["citationCode"] == "T1"
    assert event.data["tool"] == {"name": "get_evidence", "label": "Opened evidence", "labelKey": "chat:tools.get_evidence.label", "source": "keigan", "presentation": "record"}
    assert event.data["arguments"] == {"evidence_code": "e1", "investigation_id": "i-1"} and event.data["boundArgumentNames"] == ["investigation_id"]
    assert event.data["sequenceNumber"] == running.sequence_number == 2
    assert event.data["target"] == {"applicationId": "app-1", "applicationName": "Claims Processing (JP)"}


async def test_a_finished_tool_call_stores_every_column_and_publishes_the_result() -> None:
    started = await begin_run()
    record = RecordReference(kind="evidence", id="ev-1", label="E1 Error spike", application_id="app-1")
    model_view = '{"summary":"E1: Error spike","detail":"d"}'
    output = SampleOutput(summary="E1: Error spike", detail="d", records=[record])
    step = await run_one_tool_call(started, succeeded(output, model_view=model_view, flagged=True, records=[record]))
    steps = await load_steps(started.run_id)
    row = steps[-1]
    assert row.run_step_id == step.run_step_id and row.step_status == ChatRunStepStatus.SUCCEEDED and row.completed_at is not None and row.duration_milliseconds is not None
    assert row.application_id == "app-1" and row.records_json == [{"kind": "evidence", "id": "ev-1", "label": "E1 Error spike", "application_id": "app-1"}]
    assert row.output_json == output.model_dump(mode="json") and row.output_is_truncated is False and row.output_item_count == 2
    assert row.output_character_count == len(json.dumps(output.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")))
    assert row.model_view_text == model_view and row.model_view_sha256 == hashlib.sha256(model_view.encode()).hexdigest()
    assert (row.injection_flagged, row.masked_value_count, row.outcome_code, row.outcome_message) == (True, 0, None, None)
    finished = [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]
    assert finished.data["runStepId"] == step.run_step_id and finished.data["status"] == "succeeded" and finished.data["summary"] == "E1: Error spike"
    assert finished.data["outputPreview"] == output.model_dump(mode="json") and finished.data["outputIsTruncated"] is False and finished.data["itemCount"] == 2
    assert finished.data["durationMilliseconds"] == row.duration_milliseconds
    assert finished.data["records"] == [{"kind": "evidence", "id": "ev-1", "label": "E1 Error spike", "applicationId": "app-1"}]
    assert (finished.data["maskedValueCount"], finished.data["injectionFlagged"], finished.data["outcomeCode"], finished.data["outcomeMessage"]) == (0, True, None, None)


async def test_a_failed_tool_call_keeps_its_outcome_and_publishes_it_without_output() -> None:
    started = await begin_run()
    failed = ToolOutcome(
        status=ChatRunStepStatus.FAILED, output=None, application_id=None, records=[], outcome_code="source_unavailable", outcome_message="Couldn't complete \"Checked recent changes\".",
        model_message="failed", )
    await run_one_tool_call(started, failed)
    row = (await load_steps(started.run_id))[-1]
    assert (row.step_status, row.outcome_code, row.outcome_message, row.output_json, row.output_character_count, row.model_view_text) == (
        ChatRunStepStatus.FAILED, "source_unavailable", "Couldn't complete \"Checked recent changes\".", None, 0, None,
    )
    finished = [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]
    assert (finished.data["status"], finished.data["outcomeCode"], finished.data["summary"], finished.data["outputPreview"], finished.data["itemCount"]) == ("failed", "source_unavailable", None, None, None)


async def test_the_values_a_tool_masked_are_counted_and_anything_it_left_unmasked_is_masked_before_storage_and_events() -> None:
    started = await begin_run()
    output = SampleOutput(summary="Mail ops.lead@keigan.local", detail="Contact rui.reader@keigan.local about 10.1.2.3")
    outcome = succeeded(output)
    turn = await started.recorder.start_model_turn(1)
    step = await started.recorder.start_tool_call(
        parent=turn, request_id="c1", tool=EVIDENCE_TOOL, citation_code="T1", requested_arguments={"evidence_code": "E1", "note": "ask ops.lead@keigan.local"},
        effective_arguments={"evidence_code": "E1", "note": "ask ops.lead@keigan.local"}, target=TARGET, bound_argument_names=(),
    )
    await started.recorder.finish_tool_call(step, outcome, masked_value_count=4)
    row = (await load_steps(started.run_id))[-1]
    stored = json.dumps([row.output_json, row.requested_arguments_json, row.effective_arguments_json])
    assert "keigan.local" not in stored and "10.1.2.3" not in stored and "<EMAIL_1>" in stored
    published = json.dumps([event.data for event in drain(started.channel)])
    assert "keigan.local" not in published and "10.1.2.3" not in published
    assert row.masked_value_count == 4


async def test_an_output_larger_than_the_stored_limit_is_cut_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ask_keigan_tool_output_preview_characters", 200)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_model_characters", 500)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_stored_characters", 1000)
    started = await begin_run()
    output = SampleOutput(summary="big", detail="x" * 3000)
    full_text = json.dumps(output.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    await run_one_tool_call(started, succeeded(output))
    row = (await load_steps(started.run_id))[-1]
    assert row.output_is_truncated is True and row.output_character_count == len(full_text)
    assert row.output_json == {TRUNCATED_OUTPUT_KEY: full_text[:1000]}
    finished = [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]
    assert finished.data["outputPreview"] == full_text[:200] and finished.data["outputIsTruncated"] is True and finished.data["outputCharacterCount"] == len(full_text)


async def test_an_output_that_fits_the_stored_limit_but_not_the_preview_is_stored_whole_and_previewed_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ask_keigan_tool_output_preview_characters", 200)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_model_characters", 500)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_stored_characters", 1000)
    started = await begin_run()
    output = SampleOutput(summary="medium", detail="y" * 400)
    await run_one_tool_call(started, succeeded(output))
    row = (await load_steps(started.run_id))[-1]
    assert row.output_json == output.model_dump(mode="json") and row.output_is_truncated is False
    finished = [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]
    assert isinstance(finished.data["outputPreview"], str) and len(finished.data["outputPreview"]) == 200 and finished.data["outputIsTruncated"] is False


async def test_progress_of_a_tool_is_published_masked() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    step = await started.recorder.start_tool_call(parent=turn, request_id="c1", tool=EVIDENCE_TOOL, citation_code="T1", requested_arguments={}, effective_arguments={}, target=TARGET, bound_argument_names=())
    drain(started.channel)
    await started.recorder.record_tool_progress(step, "query_generated", {"queryLanguage": "kql", "queryText": "requests | where user == 'ops.lead@keigan.local'"})
    (event,) = drain(started.channel)
    assert event.name is AnswerEventName.TOOL_PROGRESS and event.data["runStepId"] == step.run_step_id and event.data["stage"] == "query_generated"
    assert event.data["detail"] == {"queryLanguage": "kql", "queryText": "requests | where user == '<EMAIL_1>'"}


async def test_a_skipped_request_gets_a_card_that_starts_and_finishes_at_once_and_uses_no_citation_code() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    step = await started.recorder.record_skipped_tool_call(
        parent=turn, request_id="c3", tool=EVIDENCE_TOOL, requested_arguments={"evidence_code": "E9"}, target=TARGET, bound_argument_names=("investigation_id",), reason=SkipReason.TOOL_LIMIT_REACHED,
    )
    row = (await load_steps(started.run_id))[-1]
    assert (row.step_status, row.outcome_code, row.citation_code, row.completed_at is not None, row.sequence_number) == (ChatRunStepStatus.SKIPPED, "tool_limit_reached", None, True, 2)
    assert row.requested_arguments_json == {"evidence_code": "E9"} and row.step_kind == ChatRunStepKind.TOOL_CALL
    started_event, finished_event = drain(started.channel)
    assert (started_event.name, finished_event.name) == (AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED)
    assert started_event.data["citationCode"] is None and started_event.data["arguments"] == {"evidence_code": "E9"} and started_event.data["runStepId"] == step.run_step_id
    assert (finished_event.data["status"], finished_event.data["outcomeCode"]) == ("skipped", "tool_limit_reached")
    assert (await load_run(started.run_id)).tool_call_count == 0  # a skipped request is not a tool call of the answer


async def test_events_and_steps_are_numbered_without_gaps_in_the_order_they_happened() -> None:
    started = await begin_run()
    await started.recorder.record_start(scope=AskKeiganScope.INVESTIGATION, offered_tools=(), maximum_tool_calls=6)
    await run_one_tool_call(started, succeeded(SampleOutput(summary="s", detail="d")))
    events = drain(started.channel)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert [event.name for event in events] == [AnswerEventName.ANSWER_STARTED, AnswerEventName.TURN_NOTE, AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED]
    assert [step.sequence_number for step in await load_steps(started.run_id)] == [1, 2]


async def test_the_run_moves_its_last_progress_time_forward_at_every_step() -> None:
    started = await begin_run()
    before = (await load_run(started.run_id)).last_progress_at
    await run_one_tool_call(started, succeeded(SampleOutput(summary="s", detail="d")))
    assert (await load_run(started.run_id)).last_progress_at > before


async def test_a_tool_call_counts_toward_the_run_when_it_finishes() -> None:
    started = await begin_run()
    await run_one_tool_call(started, succeeded(SampleOutput(summary="s", detail="d")))
    assert (await load_run(started.run_id)).tool_call_count == 1


# ── Ending the run ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def completion(**overrides) -> RunCompletion:
    values = dict(
        markdown="Errors rose [T1].", follow_ups=("Which alerts fired?",), citations=(AnswerCitation(code="T1", title="Opened evidence", run_step_id="s1"),), is_unverified=False, is_refusal=False,
        stop_reason=ChatAnswerStopReason.ANSWERED,
    )
    return RunCompletion(**{**values, **overrides})


async def test_completing_a_run_stores_the_answer_the_audit_row_and_publishes_the_final_event() -> None:
    started = await begin_run()
    await run_one_tool_call(started, succeeded(SampleOutput(summary="s", detail="d")))
    drain(started.channel)
    message_id = await started.recorder.complete_run(completion())
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.assistant_message_id, run.is_unverified, run.error_code) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED, message_id, False, None)
    assert run.citations_json == [{"code": "T1", "runStepId": "s1", "title": "Opened evidence"}] and run.follow_up_questions_json == ["Which alerts fired?"]
    assert run.completed_at is not None and run.duration_milliseconds is not None
    async with open_session() as session:
        message = await session.get(ConversationMessage, message_id)
        audit_rows = list((await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == started.run_id))).all())
    assert (message.author_role, message.message_text, message.conversation_id) == (MessageAuthorRole.ASSISTANT, "Errors rose [T1].", started.conversation_id)
    assert message.message_payload_json == {
        "answerRunId": started.run_id, "citations": [{"code": "T1", "runStepId": "s1", "title": "Opened evidence"}], "followUps": ["Which alerts fired?"], "isUnverified": False, "isRefusal": False,
        "stopReason": "answered",
    }
    assert (message.input_token_count, message.output_token_count) == (100, 10)
    (audit,) = audit_rows
    assert (audit.action_name, audit.actor_user_principal_name, audit.target_entity_type, audit.application_id) == ("chat.answer", OWNER, "chat_answer_run", "app-1")
    assert audit.action_details_json == {
        "scope": "keigan_ai_chat", "toolNames": ["get_evidence"], "applicationIds": ["app-1"], "stopReason": "answered", "toolCallCount": 1, "conversationId": started.conversation_id,
    }
    (final,) = drain(started.channel)
    assert final.name is AnswerEventName.ANSWER_COMPLETED and final.is_final
    assert final.data["answer"] == {
        "messageId": message_id, "markdown": "Errors rose [T1].", "citations": [{"code": "T1", "runStepId": "s1", "title": "Opened evidence"}], "followUps": ["Which alerts fired?"],
        "isUnverified": False, "isRefusal": False,
    }
    assert (final.data["stopReason"], final.data["toolCallCount"], final.data["inputTokenCount"], final.data["outputTokenCount"]) == ("answered", 1, 100, 10)
    assert isinstance(final.data["durationMilliseconds"], int)


async def test_the_stored_answer_text_is_masked() -> None:
    started = await begin_run()
    message_id = await started.recorder.complete_run(completion(markdown="Mail ops.lead@keigan.local."))
    async with open_session() as session:
        assert (await session.get(ConversationMessage, message_id)).message_text == "Mail <EMAIL_1>."


async def test_a_run_that_fails_records_why_cancels_open_steps_links_the_question_and_publishes_the_failure() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    await started.recorder.start_tool_call(parent=turn, request_id="c1", tool=EVIDENCE_TOOL, citation_code="T1", requested_arguments={}, effective_arguments={}, target=TARGET, bound_argument_names=())
    drain(started.channel)
    set_correlation_id("corr-failed-run")
    failure = AskKeiganErrorCatalogue.describe("ai_timeout", {"modelTier": "deep", "seconds": 60})
    await started.recorder.fail_run(failure)
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.error_code, run.assistant_message_id, run.completed_at is not None) == (ChatAnswerRunStatus.FAILED, ChatAnswerStopReason.FAILED, "ai_timeout", None, True)
    assert [step.step_status for step in await load_steps(started.run_id)] == [ChatRunStepStatus.CANCELLED, ChatRunStepStatus.CANCELLED]
    async with open_session() as session:
        question = await session.get(ConversationMessage, started.user_message_id)
        audit = (await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == started.run_id))).one()
    assert question.message_payload_json == {"answerRunId": started.run_id}
    assert audit.action_details_json["stopReason"] == "failed"
    (final,) = drain(started.channel)
    assert final.name is AnswerEventName.ANSWER_FAILED and final.is_final and final.data["stopReason"] == "failed"
    assert final.data["error"] == {
        "errorCode": "ai_timeout", "title": failure.title, "detail": failure.detail, "correlationId": "corr-failed-run", "isRetryable": True, "parameters": dict(failure.parameters),
    }


async def test_stopping_a_run_marks_it_cancelled_and_still_links_the_question() -> None:
    started = await begin_run()
    await started.recorder.start_model_turn(1)
    await started.recorder.cancel_run(AskKeiganErrorCatalogue.describe("cancelled"))
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.error_code) == (ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, "cancelled")
    assert [step.step_status for step in await load_steps(started.run_id)] == [ChatRunStepStatus.CANCELLED]
    async with open_session() as session:
        assert (await session.get(ConversationMessage, started.user_message_id)).message_payload_json == {"answerRunId": started.run_id}
    (final,) = drain(started.channel)
    assert (final.name, final.data["stopReason"], final.data["error"]["errorCode"], final.data["error"]["isRetryable"]) == (AnswerEventName.ANSWER_FAILED, "cancelled_by_user", "cancelled", False)


async def test_linking_the_question_keeps_whatever_else_its_payload_already_holds() -> None:
    started = await begin_run()
    async with open_session() as session:
        (await session.get(ConversationMessage, started.user_message_id)).message_payload_json = {"clientNote": "kept"}
    await started.recorder.fail_run(AskKeiganErrorCatalogue.describe("ai_unavailable"))
    async with open_session() as session:
        assert (await session.get(ConversationMessage, started.user_message_id)).message_payload_json == {"clientNote": "kept", "answerRunId": started.run_id}


async def test_a_stop_request_stored_in_the_run_row_is_seen_by_the_recorder() -> None:
    started = await begin_run()
    assert await started.recorder.is_cancel_requested() is False
    async with open_session() as session:
        from keigan.utils.time_utils import utc_now

        (await session.get(ChatAnswerRun, started.run_id)).cancel_requested_at = utc_now()
    assert await started.recorder.is_cancel_requested() is True


async def test_a_reader_that_never_reads_cannot_stall_the_run() -> None:
    started = await begin_run(queue_size=2)
    for number in range(1, 5):
        turn = await started.recorder.start_model_turn(number)
        await started.recorder.finish_model_turn(turn, turn_result("note"), model_text="note", is_note=True)
    assert started.channel.was_dropped is True
    assert (await load_run(started.run_id)).model_turn_count == 4  # the stored trace is complete even though the stream was dropped


# ── Beginning a run: the question and the run are one transaction ─────────────────────────────────────────────────────────────
async def test_beginning_a_run_stores_the_question_with_its_run_link_in_the_same_transaction() -> None:
    started = await begin_run()
    (question,) = await messages_of(started.conversation_id)
    run = await load_run(started.run_id)
    assert (question.message_id, question.author_role, question.author_display_name, question.author_user_principal_name) == (run.user_message_id, MessageAuthorRole.USER, "Rui Reader", OWNER)
    assert question.message_text == "Which SLOs are at risk?" and question.message_payload_json == {"answerRunId": started.run_id} and question.output_token_count == 0


async def test_a_repeated_client_request_id_is_refused_by_the_database_and_leaves_no_orphan_question() -> None:
    conversation_id = await new_conversation()
    await TraceRecorder.begin(registration_for(conversation_id, client_request_id="same-request"), RunEventChannel("first"), PiiMasker())
    with pytest.raises(IntegrityError):
        await TraceRecorder.begin(registration_for(conversation_id, client_request_id="same-request", question_text="Asked twice"), RunEventChannel("second"), PiiMasker())
    assert [message.message_text for message in await messages_of(conversation_id)] == ["Which SLOs are at risk?"]
    assert len(await runs_of(conversation_id)) == 1


async def test_a_second_running_run_in_one_conversation_is_refused_by_the_database_and_leaves_no_orphan_question() -> None:
    conversation_id = await new_conversation()
    await TraceRecorder.begin(registration_for(conversation_id), RunEventChannel("first"), PiiMasker())
    with pytest.raises(IntegrityError):
        await TraceRecorder.begin(registration_for(conversation_id, question_text="A second question"), RunEventChannel("second"), PiiMasker())
    assert [message.message_text for message in await messages_of(conversation_id)] == ["Which SLOs are at risk?"]
    assert len(await runs_of(conversation_id)) == 1


async def test_a_new_run_may_start_in_a_conversation_once_the_previous_one_ended() -> None:
    first = await begin_run()
    await first.recorder.fail_run(AskKeiganErrorCatalogue.describe("ai_unavailable"))
    await TraceRecorder.begin(registration_for(first.conversation_id, question_text="Try again"), RunEventChannel("again"), PiiMasker())
    assert [run.run_status for run in await runs_of(first.conversation_id)].count(ChatAnswerRunStatus.RUNNING) == 1


# ── Ending a run: every end is a conditional write, so the first end wins and nobody overwrites it (H1) ────────────────────────
INTERRUPTED = AskKeiganErrorCatalogue.describe("answer_interrupted")


async def interrupted_by_another_process(started: Started) -> None:
    other_process = TraceRecorder.for_interrupted_run(started.run_id, (await load_run(started.run_id)).started_at)
    assert await other_process.interrupt_run(INTERRUPTED, only_if_silent_since=None) is True


async def test_completing_a_run_that_another_process_interrupted_changes_nothing_and_publishes_nothing() -> None:
    started = await begin_run()
    await interrupted_by_another_process(started)
    drain(started.channel)
    assert await started.recorder.complete_run(completion()) is None
    run = await load_run(started.run_id)
    assert (run.run_status, run.error_code, run.assistant_message_id, run.citations_json) == (ChatAnswerRunStatus.FAILED, "answer_interrupted", None, [])
    assert [message.author_role for message in await messages_of(started.conversation_id)] == [MessageAuthorRole.USER]
    assert len(await audit_rows_of(started.run_id)) == 1  # the interruption's; the loser wrote no second one
    assert drain(started.channel) == []


async def test_failing_a_run_that_already_completed_changes_nothing_and_publishes_nothing() -> None:
    started = await begin_run()
    message_id = await started.recorder.complete_run(completion())
    drain(started.channel)
    assert await started.recorder.fail_run(AskKeiganErrorCatalogue.describe("ai_unavailable")) is False
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.error_code, run.assistant_message_id) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED, None, message_id)
    assert len(await audit_rows_of(started.run_id)) == 1 and drain(started.channel) == []


async def test_a_stop_that_arrives_after_the_run_completed_does_not_turn_it_into_a_cancelled_run() -> None:
    started = await begin_run()
    await started.recorder.complete_run(completion())
    drain(started.channel)
    assert await started.recorder.cancel_run(AskKeiganErrorCatalogue.describe("cancelled")) is False
    assert (await load_run(started.run_id)).run_status == ChatAnswerRunStatus.COMPLETED and drain(started.channel) == []


async def test_a_run_that_was_stopped_is_not_completed_by_an_engine_that_finished_a_moment_later() -> None:
    started = await begin_run()
    assert await started.recorder.cancel_run(AskKeiganErrorCatalogue.describe("cancelled")) is True
    drain(started.channel)
    assert await started.recorder.complete_run(completion()) is None
    run = await load_run(started.run_id)
    assert (run.run_status, run.stop_reason, run.assistant_message_id) == (ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, None)
    assert len(await audit_rows_of(started.run_id)) == 1 and drain(started.channel) == []


async def test_a_running_step_of_a_run_that_someone_else_ended_is_left_as_that_end_left_it() -> None:
    started = await begin_run()
    await started.recorder.start_model_turn(1)
    await started.recorder.complete_run(completion())
    (step,) = await load_steps(started.run_id)
    await started.recorder.fail_run(AskKeiganErrorCatalogue.describe("ai_unavailable"))
    assert (await load_steps(started.run_id))[0].step_status == step.step_status


async def test_an_interruption_spares_a_run_that_made_progress_after_the_moment_it_was_judged_silent() -> None:
    started = await begin_run()
    progress_at = (await load_run(started.run_id)).last_progress_at
    judged_silent_since = progress_at - timedelta(seconds=1)  # the reader saw an older progress time than the run has now
    other_process = TraceRecorder.for_interrupted_run(started.run_id, progress_at)
    assert await other_process.interrupt_run(INTERRUPTED, only_if_silent_since=judged_silent_since) is False
    assert (await load_run(started.run_id)).run_status == ChatAnswerRunStatus.RUNNING and await audit_rows_of(started.run_id) == []
    assert await other_process.interrupt_run(INTERRUPTED, only_if_silent_since=progress_at) is True


async def test_touching_the_progress_moves_it_forward_while_the_run_runs_and_says_when_it_does_not() -> None:
    started = await begin_run()
    before = (await load_run(started.run_id)).last_progress_at
    assert await started.recorder.touch_progress() is True
    assert (await load_run(started.run_id)).last_progress_at > before
    await started.recorder.complete_run(completion())
    ended_progress = (await load_run(started.run_id)).last_progress_at
    assert await started.recorder.touch_progress() is False
    assert (await load_run(started.run_id)).last_progress_at == ended_progress  # an ended run is never touched again


async def test_a_stop_request_is_stored_once_and_refused_for_a_run_that_ended() -> None:
    started = await begin_run()
    assert await TraceRecorder.store_cancel_request(started.run_id) is True
    first_request = (await load_run(started.run_id)).cancel_requested_at
    assert first_request is not None and await TraceRecorder.store_cancel_request(started.run_id) is True
    assert (await load_run(started.run_id)).cancel_requested_at == first_request  # asking again changes nothing
    await started.recorder.cancel_run(AskKeiganErrorCatalogue.describe("cancelled"))
    assert await TraceRecorder.store_cancel_request(started.run_id) is False


async def test_follow_ups_and_citation_titles_are_masked_before_they_are_stored_or_published() -> None:
    started = await begin_run()
    message_id = await started.recorder.complete_run(completion(
        follow_ups=("Did ops.lead@keigan.local approve it?",), citations=(AnswerCitation(code="E1", title="Mail from rui.reader@keigan.local", evidence_code="E1"),),
    ))
    run = await load_run(started.run_id)
    async with open_session() as session:
        stored_message = await session.get(ConversationMessage, message_id)
    final = drain(started.channel)[-1]
    everything = json.dumps([run.follow_up_questions_json, run.citations_json, stored_message.message_payload_json, final.data])
    assert "keigan.local" not in everything and "<EMAIL_1>" in run.follow_up_questions_json[0] and "<EMAIL_2>" in run.citations_json[0]["title"]


# ── The trust flags of an output are their own fields, computed from the whole output (frontend contract) ───────────────────────
class ListOutput(BaseModel):
    summary: str
    items: list[str]
    item_count: int
    total_count: int
    is_truncated: bool
    records: list[RecordReference] = []


class QueryOutput(BaseModel):
    summary: str
    is_simulated: bool
    rows: list[str]
    records: list[RecordReference] = []


async def finished_event_of(started: Started, outcome: ToolOutcome) -> AnswerEvent:
    await run_one_tool_call(started, outcome)
    return [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]


async def test_a_list_output_publishes_its_total_and_truncation_as_their_own_fields() -> None:
    started = await begin_run()
    output = ListOutput(summary="25 changes", items=["a", "b"], item_count=2, total_count=25, is_truncated=True)
    event = await finished_event_of(started, succeeded(output))
    assert (event.data["isSimulated"], event.data["totalCount"], event.data["isTruncated"], event.data["itemCount"]) == (None, 25, True, 2)


async def test_a_simulated_output_publishes_isSimulated() -> None:
    started = await begin_run()
    event = await finished_event_of(started, succeeded(QueryOutput(summary="3 errors", is_simulated=True, rows=["x"])))
    assert (event.data["isSimulated"], event.data["totalCount"], event.data["isTruncated"]) == (True, None, None)


async def test_an_output_with_none_of_these_notions_publishes_null_not_absent() -> None:
    started = await begin_run()
    event = await finished_event_of(started, succeeded(SampleOutput(summary="s", detail="d")))
    assert {"isSimulated", "totalCount", "isTruncated"} <= set(event.data) and (event.data["isSimulated"], event.data["totalCount"], event.data["isTruncated"]) == (None, None, None)


async def test_the_flags_survive_a_preview_that_is_cut_because_they_come_from_the_whole_output(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ask_keigan_tool_output_preview_characters", 200)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_model_characters", 500)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_stored_characters", 5000)
    started = await begin_run()
    output = ListOutput(summary="many", items=["x" * 40] * 20, item_count=20, total_count=61, is_truncated=True)
    event = await finished_event_of(started, succeeded(output))
    assert isinstance(event.data["outputPreview"], str)  # the preview is text here, so the flags could not be read from it
    assert (event.data["totalCount"], event.data["isTruncated"]) == (61, True)


async def test_the_flags_of_an_output_cut_for_storage_are_kept_beside_the_cut_text(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ask_keigan_tool_output_preview_characters", 200)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_model_characters", 500)
    monkeypatch.setattr(settings, "ask_keigan_tool_output_stored_characters", 1000)
    started = await begin_run()
    output = ListOutput(summary="huge", items=["y" * 100] * 30, item_count=30, total_count=90, is_truncated=True)
    event = await finished_event_of(started, succeeded(output))
    stored = (await load_steps(started.run_id))[-1].output_json
    assert TRUNCATED_OUTPUT_KEY in stored and (stored["total_count"], stored["is_truncated"]) == (90, True) and "is_simulated" not in stored
    assert (event.data["totalCount"], event.data["isTruncated"]) == (90, True)


async def test_a_skipped_or_failed_call_has_no_flags() -> None:
    started = await begin_run()
    turn = await started.recorder.start_model_turn(1)
    await started.recorder.record_skipped_tool_call(parent=turn, request_id="c3", tool=EVIDENCE_TOOL, requested_arguments={}, target=TARGET, bound_argument_names=(), reason=SkipReason.TOOL_LIMIT_REACHED)
    finished = [event for event in drain(started.channel) if event.name is AnswerEventName.TOOL_FINISHED][0]
    assert (finished.data["isSimulated"], finished.data["totalCount"], finished.data["isTruncated"]) == (None, None, None)


# ── The parameters of a failure are stored, so a reload words the same message ─────────────────────────────────────────────────────
async def test_a_failed_run_stores_the_parameters_of_its_error_and_publishes_them() -> None:
    started = await begin_run()
    failure = AskKeiganErrorCatalogue.describe("internal_error", {"stepDescription": "running \"Checked recent changes\""})
    await started.recorder.fail_run(failure)
    assert (await load_run(started.run_id)).error_parameters_json == dict(failure.parameters) and failure.parameters["stepDescription"] == "running \"Checked recent changes\""
    (final,) = drain(started.channel)
    assert final.data["error"]["parameters"] == dict(failure.parameters)


async def test_a_run_that_did_not_fail_has_no_error_parameters() -> None:
    started = await begin_run()
    await started.recorder.complete_run(completion())
    assert (await load_run(started.run_id)).error_parameters_json is None

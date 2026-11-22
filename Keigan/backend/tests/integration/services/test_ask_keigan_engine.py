"""keigan/services/ask_keigan_engine.py: one question answered by a model that calls read-only tools, with a trace a person can check (spec 23, 4.8 to 4.10, AC-10, 14 to 19, 42, 44)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER, fixed_answer
from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import ModelTier
from keigan.ai.model_capabilities import resolve_model_capabilities
from keigan.ai.operating_notes_prompt import OPERATING_NOTES_TITLE
from keigan.config.database_config import open_session
from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import LlmProviderName, get_settings
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationTimelineEvent
from keigan.entities.platform_entities import AuditEvent
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus
from keigan.exceptions.keigan_exceptions import AgentToolsUnsupportedException, LlmRateLimitedException, LlmTimeoutException, TokenBudgetExceededException
from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_engine import AskKeiganEngine
from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName
from keigan.services.ask_keigan_interruption import RunInterruption
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry
from keigan.services.ask_keigan_scopes import ScopeProfile
from keigan.services.ask_keigan_transcript import ConversationTurn
from keigan.utils.string_table import translate
from keigan.utils.time_utils import utc_now
from support.ask_keigan_runs import Finished, ScriptedGateway, Turn, ask, profile_for, request_for, user
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")

ADMIN = user("keigan.admin@keigan.local", "KEIGAN_admin", is_admin=True)
INVESTIGATION_TOOL_NAMES = {"get_evidence", "get_investigation_timeline", "search_knowledge", "query_logs", "list_recent_changes", "find_runbooks", "get_topology", "get_slo_status"}
NOTES = "Claims submission is the revenue path. Page ops.lead@keigan.local first."
FIRST_EVENT_AT = datetime(2026, 1, 5, 9, 0)
OUTSIDE_SCOPE = fixed_answer("outside_scope", "en")


@dataclass(frozen=True)
class Seeded:
    investigation_id: str
    application_id: str


@pytest.fixture(scope="module")
async def seeded(seed_context) -> Seeded:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        await session.execute(update(Application).where(Application.application_id == application_id).values(operating_notes_text=NOTES))
        incident = Incident(application_id=application_id, external_incident_number="INC0099100", incident_title="Claims API errors")
        session.add(incident)
        await session.flush()
        investigation = Investigation(application_id=application_id, incident_id=incident.incident_id, executive_summary="Pool exhaustion on claims-api.")
        session.add(investigation)
        await session.flush()
        session.add_all([
            InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log_analytics", evidence_category="error_pattern", evidence_title="Error spike on claims-api",
                evidence_summary="Errors rose from 2 to 312 per minute. Reported by rui.reader@keigan.local.", matched_record_count=312, signal_strength="high",
            ),
            InvestigationTimelineEvent(investigation_id=investigation.investigation_id, event_occurred_at=FIRST_EVENT_AT, event_type="alert_fired", event_title="Error rate alert fired", event_source="keigan"),
            InvestigationTimelineEvent(investigation_id=investigation.investigation_id, event_occurred_at=FIRST_EVENT_AT + timedelta(minutes=10), event_type="deployment", event_title="Release 41 deployed", event_source="azure_activity_log"),
        ])
        return Seeded(investigation.investigation_id, application_id)


async def run_with(seeded: Seeded, question: str, gateway: ScriptedGateway | None = None, **options) -> Finished:
    current_user = options.pop("current_user", ADMIN)
    return await ask(await profile_for(current_user, seeded.investigation_id), question, current_user=current_user, gateway=gateway, **options)


def answer_turn(text: str, **options) -> Turn:
    return Turn(text=text, **options)


def evidence_call(code: str = "E1", request_id: str = "call_1"):
    return request_for("get_evidence", {"evidence_code": code}, request_id)


# ── The whole loop with the offline planner ───────────────────────────────────────────────────────────────────────────────────
async def test_a_two_tool_question_runs_both_tools_in_order_and_answers_with_citations_to_each(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Show me evidence E1 and what the timeline says")
    assert finished.outcome.status is ChatAnswerRunStatus.COMPLETED and finished.outcome.stop_reason is ChatAnswerStopReason.ANSWERED
    assert [(step.step_kind, step.tool_name, step.citation_code, step.step_status) for step in finished.steps] == [
        (ChatRunStepKind.MODEL_TURN, None, None, ChatRunStepStatus.SUCCEEDED), (ChatRunStepKind.TOOL_CALL, "get_evidence", "T1", ChatRunStepStatus.SUCCEEDED),
        (ChatRunStepKind.MODEL_TURN, None, None, ChatRunStepStatus.SUCCEEDED), (ChatRunStepKind.TOOL_CALL, "get_investigation_timeline", "T2", ChatRunStepStatus.SUCCEEDED),
        (ChatRunStepKind.MODEL_TURN, None, None, ChatRunStepStatus.SUCCEEDED),
    ]
    assert [step.sequence_number for step in finished.steps] == [1, 2, 3, 4, 5]
    assert finished.tool_steps[0].parent_run_step_id == finished.steps[0].run_step_id and finished.tool_steps[1].parent_run_step_id == finished.steps[2].run_step_id
    (answer,) = finished.assistant_messages
    assert "[T1]" in answer.message_text and "[T2]" in answer.message_text and "[E1]" in answer.message_text and FOLLOW_UP_MARKER not in answer.message_text
    assert answer.message_payload_json["answerRunId"] == finished.run.answer_run_id and answer.message_payload_json["isUnverified"] is False and answer.message_payload_json["isRefusal"] is False
    assert [citation["code"] for citation in answer.message_payload_json["citations"]] == ["T1", "T2", "E1"]
    assert answer.message_payload_json["citations"][0]["runStepId"] == finished.tool_steps[0].run_step_id
    assert len(answer.message_payload_json["followUps"]) == 3
    run = finished.run
    assert (run.run_status, run.stop_reason, run.assistant_message_id, run.tool_call_count, run.model_turn_count, run.is_unverified) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED, answer.message_id, 2, 3, False)
    assert run.tool_calling_mode == "scripted_mock" and run.completed_at is not None


async def test_the_events_come_in_the_order_of_the_protocol_with_consecutive_numbers_and_one_final_event(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Show me evidence E1 and what the timeline says")
    assert [event.sequence for event in finished.events] == list(range(1, len(finished.events) + 1))
    names = finished.names()
    assert names[0] is AnswerEventName.ANSWER_STARTED and names[-1] is AnswerEventName.ANSWER_COMPLETED
    assert [name for name in names if name in (AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED)] == [
        AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED, AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED,
    ]
    assert sum(event.is_final for event in finished.events) == 1
    started = finished.of(AnswerEventName.ANSWER_STARTED)[0].data
    assert started["scope"] == "investigation" and started["maximumToolCalls"] == get_settings().ask_keigan_max_tool_calls_investigation
    assert {tool["name"] for tool in started["offeredTools"]} == INVESTIGATION_TOOL_NAMES
    tool_started = finished.of(AnswerEventName.TOOL_STARTED)[0].data
    assert tool_started["citationCode"] == "T1" and tool_started["target"]["applicationName"] and tool_started["arguments"]["investigation_id"] == seeded.investigation_id
    assert tool_started["boundArgumentNames"] == ["investigation_id"]  # the screen shows these as set by the investigation, not chosen by the model
    step_events = [event for event in finished.events if "runStepId" in event.data]
    assert all(event.data["sequenceNumber"] == next(step.sequence_number for step in finished.steps if step.run_step_id == event.data["runStepId"]) for event in step_events)
    texts = [event.data["text"] for event in finished.of(AnswerEventName.ANSWER_TEXT)]
    assert texts and all(text.strip() for text in texts) and not any(FOLLOW_UP_MARKER in text for text in texts)


async def test_the_final_event_carries_the_answer_the_totals_and_the_stop_reason(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Show me evidence E1")
    final = finished.of(AnswerEventName.ANSWER_COMPLETED)[0].data
    assert final["answer"]["messageId"] == finished.assistant_messages[0].message_id and final["answer"]["markdown"] == finished.assistant_messages[0].message_text
    assert final["stopReason"] == "answered" and final["toolCallCount"] == 1
    assert final["inputTokenCount"] == finished.run.total_input_token_count > 0


async def test_a_question_that_is_not_about_keigans_data_is_a_refusal_with_no_tool_and_no_unverified_warning(seeded: Seeded) -> None:
    finished = await run_with(seeded, "What is the capital of France?")
    (answer,) = finished.assistant_messages
    assert answer.message_text == OUTSIDE_SCOPE and answer.message_payload_json["isRefusal"] is True and answer.message_payload_json["isUnverified"] is False
    assert finished.tool_steps == [] and finished.run.tool_call_count == 0


async def test_a_failed_tool_is_reported_as_not_checked_never_as_empty_and_its_citation_is_not_available(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Show me evidence E99")
    (failed_step,) = finished.tool_steps
    assert (failed_step.step_status, failed_step.outcome_code) == (ChatRunStepStatus.FAILED, "not_found")
    (answer,) = finished.assistant_messages
    assert "could not check get_evidence" in answer.message_text and "[T1]" not in answer.message_text
    assert answer.message_payload_json["citations"] == [] and answer.message_payload_json["isUnverified"] is True
    tool_finished = finished.of(AnswerEventName.TOOL_FINISHED)[0].data
    assert tool_finished["status"] == "failed" and tool_finished["outcomeCode"] == "not_found" and "was not found" in tool_finished["outcomeMessage"]


async def test_a_failed_tool_of_a_japanese_speaker_is_worded_in_japanese_in_the_card_the_trace_and_the_sources(seeded: Seeded) -> None:
    japanese_admin = replace(ADMIN, preferred_locale="ja")
    set_correlation_id("corr-ja")
    finished = await run_with(seeded, "Show me evidence E99", ScriptedGateway([Turn(requests=(evidence_call("E99"),)), Turn(text="E99 could not be checked.")]), current_user=japanese_admin)
    (failed_step,) = finished.tool_steps
    label = translate("ja", "ask_keigan_tools.get_evidence.label")
    expected = AskKeiganErrorCatalogue.describe(
        "tool_failed_not_found", {"toolLabel": label, "recordKind": translate("ja", "ask_keigan_tools.record_kinds.evidence_item")}, "ja",
    ).detail
    assert failed_step.outcome_message == expected and "evidence item" not in expected
    tool_finished = finished.of(AnswerEventName.TOOL_FINISHED)[0].data
    assert tool_finished["outcomeMessage"] == expected
    assert label in finished.of(AnswerEventName.TOOL_FINISHED)[0].data["outcomeMessage"]


async def test_the_audit_row_names_what_the_run_read_without_any_content(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Show me evidence E1")
    async with open_session() as session:
        audit = (await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == finished.run.answer_run_id))).one()
    assert (audit.action_name, audit.actor_user_principal_name, audit.application_id) == ("chat.answer", ADMIN.user_principal_name, seeded.application_id)
    assert audit.action_details_json["toolNames"] == ["get_evidence"] and audit.action_details_json["stopReason"] == "answered" and audit.action_details_json["toolCallCount"] == 1
    assert "312" not in json.dumps(audit.action_details_json)


# ── What the model is given and what is stored (masking, spotlighting) ───────────────────────────────────────────────────────
async def test_the_model_gets_the_context_notes_history_and_question_as_untrusted_data_and_the_rules_with_the_effective_limit(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_investigation", 4)
    gateway = ScriptedGateway([answer_turn("Nothing to add.")])
    finished = await run_with(seeded, "Why did it fail? Mail rui.reader@keigan.local", gateway, history=(ConversationTurn("user", "Earlier question"), ConversationTurn("assistant", "Earlier answer")))
    call = gateway.calls[0]
    sections = [entry.section for entry in call["transcript"]]
    assert [section.title for section in sections] == ["Investigation context", OPERATING_NOTES_TITLE, "Conversation so far", "Question"]
    assert all(section.is_untrusted for section in sections)
    assert "<EMAIL_2>" in sections[1].content and "ops.lead@keigan.local" not in sections[1].content  # the notes are masked with the run's masker
    assert sections[2].content == "user: Earlier question\nassistant: Earlier answer"
    assert sections[3].content == "Why did it fail? Mail <EMAIL_1>"  # the question was masked before it was stored; the placeholders agree across the run
    assert call["model_tier"] is ModelTier.DEEP and call["allow_tool_requests"] is True and call["feature_name"] == "ask_keigan_investigation"
    assert "Use at most 4 tool calls" in call["system_prompt"] and finished.prepared_system_prompt == call["system_prompt"]
    assert call["usage_context"].application_id == seeded.application_id and call["usage_context"].investigation_id == seeded.investigation_id
    assert call["usage_context"].conversation_id == finished.conversation_id and call["usage_context"].requested_by_user_principal_name == ADMIN.user_principal_name
    assert {tool.name for tool in gateway.offered_tools} == INVESTIGATION_TOOL_NAMES
    evidence_schema = next(tool for tool in gateway.offered_tools if tool.name == "get_evidence").parameters_schema
    assert "investigation_id" not in evidence_schema["properties"]  # bound by the scope: the model never chooses it


async def test_the_run_stores_what_is_needed_to_reproduce_it(seeded: Seeded) -> None:
    gateway = ScriptedGateway([answer_turn("Done.")])
    finished = await run_with(seeded, "Hello?", gateway)
    run = finished.run
    assert (run.prompt_key, run.prompt_version, run.model_tier, run.provider_name, run.conversation_scope, run.investigation_id) == ("ask_keigan_investigation", "1", "deep", "mock", "investigation", seeded.investigation_id)
    assert re.fullmatch(r"[0-9a-f]{64}", run.system_prompt_sha256) and re.fullmatch(r"[0-9a-f]{64}", run.tool_catalog_sha256)
    assert {tool["name"] for tool in run.offered_tools_json} == INVESTIGATION_TOOL_NAMES
    assert run.limits_json["maximumToolCalls"] == get_settings().ask_keigan_max_tool_calls_investigation and run.limits_json["answerTokenBudget"] == get_settings().ask_keigan_answer_token_budget
    assert run.scope_snapshot_json["boundArguments"] == {"application_code": "CLMJP", "investigation_id": seeded.investigation_id}
    assert (run.total_input_token_count, run.total_output_token_count, run.model_name, run.tool_calling_mode) == (100, 20, "scripted-model", "native")


async def test_the_stored_model_view_is_what_the_model_received(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn("Errors rose [T1].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (tool_step,) = finished.tool_steps
    (result_entry,) = gateway.tool_results_seen_in_call(1)
    received = re.fullmatch(r'<untrusted_data source="tool:get_evidence:T1" boundary="(kg-[0-9a-f]+)"[^>]*>\n(.*)\n</untrusted_data boundary="\1">', result_entry.tool_result_text, re.DOTALL)
    assert received and received.group(2) == tool_step.model_view_text
    import hashlib

    assert tool_step.model_view_sha256 == hashlib.sha256(tool_step.model_view_text.encode()).hexdigest()
    assert (result_entry.tool_request_id, result_entry.tool_name) == ("call_1", "get_evidence")


async def test_nothing_unmasked_reaches_storage_events_or_the_model(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(text="Looking at the evidence.", requests=(evidence_call(),)), answer_turn("It was reported by <EMAIL_1> [T1].")])
    finished = await run_with(seeded, "Show me evidence E1 and mail rui.reader@keigan.local", gateway)
    raw_address = "rui.reader@keigan.local"
    transcripts = json.dumps([[str(entry) for entry in call["transcript"]] for call in gateway.calls])
    stored = json.dumps([[step.model_text, step.output_json, step.model_view_text, step.requested_arguments_json, step.effective_arguments_json, step.outcome_message] for step in finished.steps]
                        + [[message.message_text, message.message_payload_json] for message in finished.messages])
    published = json.dumps([event.data for event in finished.events])
    for label, text in (("transcripts", transcripts), ("stored", stored), ("published", published)):
        assert raw_address not in text, label
    assert "<EMAIL_" in stored


async def test_the_model_is_told_the_text_of_a_tool_result_only_inside_an_untrusted_block(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn("Done [T1].")])
    await run_with(seeded, "Show me evidence E1", gateway)
    (result_entry,) = gateway.tool_results_seen_in_call(1)
    assert result_entry.tool_result_text.startswith("<untrusted_data ") and result_entry.tool_result_text.endswith(">")


# ── Citations, follow-ups, trust ─────────────────────────────────────────────────────────────────────────────────────────────
async def test_only_real_citations_survive_in_events_and_storage(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn("Errors rose [T1][T2][T9]. Evidence [E1] and [E77] agree.\n\nSecond paragraph [T3].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (answer,) = finished.assistant_messages
    assert answer.message_text == "Errors rose [T1]. Evidence [E1] and  agree.\n\nSecond paragraph ."
    streamed = " ".join(event.data["text"] for event in finished.of(AnswerEventName.ANSWER_TEXT) if event.data["turnNumber"] == 2)
    assert "[T2]" not in streamed and "[T9]" not in streamed and "[E77]" not in streamed and "[T3]" not in streamed and "[T1]" in streamed
    assert [citation["code"] for citation in answer.message_payload_json["citations"]] == ["T1", "E1"]


async def test_a_citation_of_a_tool_call_that_failed_is_stripped(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(evidence_call("E99"),)), answer_turn("The evidence says things [T1].")])
    finished = await run_with(seeded, "Show me evidence E99", gateway)
    (answer,) = finished.assistant_messages
    assert answer.message_text == "The evidence says things ." and answer.message_payload_json["isUnverified"] is True


async def test_follow_ups_are_split_and_limited_and_the_marker_never_appears(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_follow_up_question_limit", 2)
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn(f"Errors rose [T1].\n\n{FOLLOW_UP_MARKER}\nWhich alerts fired?\nWhat changed?\nWho owns it?")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (answer,) = finished.assistant_messages
    assert answer.message_text == "Errors rose [T1]." and answer.message_payload_json["followUps"] == ["Which alerts fired?", "What changed?"]
    assert finished.run.follow_up_questions_json == ["Which alerts fired?", "What changed?"]
    assert FOLLOW_UP_MARKER not in json.dumps([event.data for event in finished.events])


async def test_an_answer_that_cites_nothing_after_a_tool_call_is_flagged_unverified(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn("Errors rose sharply.")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert finished.assistant_messages[0].message_payload_json["isUnverified"] is True and finished.run.is_unverified is True
    assert finished.of(AnswerEventName.ANSWER_COMPLETED)[0].data["answer"]["isUnverified"] is True


async def test_an_answer_that_cites_evidence_of_the_investigation_without_any_tool_call_is_still_unverified(seeded: Seeded) -> None:
    gateway = ScriptedGateway([answer_turn("The spike is evidence [E1].")])
    finished = await run_with(seeded, "What is the evidence?", gateway)
    assert finished.assistant_messages[0].message_text == "The spike is evidence [E1]." and finished.run.is_unverified is True


async def test_a_note_before_a_tool_call_is_a_note_in_the_trace_and_not_part_of_the_answer(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(text="Checking the evidence first.\n\nThen I will answer.", requests=(evidence_call(),)), answer_turn("Errors rose [T1].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (note,) = finished.of(AnswerEventName.TURN_NOTE)
    assert note.data["turnNumber"] == 1 and note.data["text"] == "Checking the evidence first.\n\nThen I will answer." and note.data["runStepId"] == finished.steps[0].run_step_id
    assert finished.names().index(AnswerEventName.TURN_NOTE) < finished.names().index(AnswerEventName.TOOL_STARTED)
    assert finished.steps[0].model_text == "Checking the evidence first.\n\nThen I will answer." and finished.steps[0].turn_finish == "tool_requests"
    assert "Checking the evidence first" not in finished.assistant_messages[0].message_text


async def test_a_reply_that_stopped_for_length_is_taken_as_the_answer_and_its_tool_requests_are_ignored(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(text="Half an answer", requests=(evidence_call(),), finish="length")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert finished.tool_steps == [] and finished.assistant_messages[0].message_text == "Half an answer"


# ── Limits ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_the_tool_limit_ends_with_an_answer_and_the_request_over_the_limit_is_recorded_as_skipped(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_investigation", 2)
    requests = (evidence_call("E1", "c1"), request_for("get_investigation_timeline", {}, "c2"), evidence_call("E1", "c3"))
    gateway = ScriptedGateway([Turn(requests=requests), answer_turn("Both checks agree [T1][T2].")])
    finished = await run_with(seeded, "Check everything", gateway)
    assert [step.step_status for step in finished.tool_steps] == [ChatRunStepStatus.SUCCEEDED, ChatRunStepStatus.SUCCEEDED, ChatRunStepStatus.SKIPPED]
    assert (finished.tool_steps[2].outcome_code, finished.tool_steps[2].citation_code) == ("tool_limit_reached", None)
    assert gateway.calls[0]["allow_tool_requests"] is True and gateway.calls[1]["allow_tool_requests"] is False  # the next turn is the last one
    assert finished.outcome.stop_reason is ChatAnswerStopReason.TOOL_LIMIT_REACHED and finished.run.stop_reason == ChatAnswerStopReason.TOOL_LIMIT_REACHED
    assert finished.assistant_messages[0].message_text == "Both checks agree [T1] [T2]." and finished.run.tool_call_count == 2
    skipped_result = gateway.tool_results_seen_in_call(1)[2].tool_result_text
    assert skipped_result.startswith("get_evidence skipped (tool_limit_reached)")  # the model is told, and the planner reads this prefix
    assert finished.of(AnswerEventName.ANSWER_COMPLETED)[0].data["stopReason"] == "tool_limit_reached"


async def test_a_model_that_keeps_asking_for_tools_on_the_last_turn_gets_the_deterministic_limit_answer(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_investigation", 1)
    gateway = ScriptedGateway([Turn(requests=(evidence_call("E1", "c1"),)), Turn(requests=(evidence_call("E1", "c2"),))])
    finished = await run_with(seeded, "Check evidence", gateway)
    assert finished.outcome.stop_reason is ChatAnswerStopReason.TOOL_LIMIT_REACHED
    (answer,) = finished.assistant_messages
    assert answer.message_text.startswith("I stopped at the limit of 1 tool calls before I could write a full answer.")
    assert "- E1: Error spike on claims-api (high signal, 312 matching records) [T1]" in answer.message_text
    assert [step.step_status for step in finished.tool_steps] == [ChatRunStepStatus.SUCCEEDED, ChatRunStepStatus.SKIPPED]
    assert [citation["code"] for citation in answer.message_payload_json["citations"]] == ["T1"]


async def test_requests_beyond_the_parallel_limit_are_skipped_and_the_model_is_told(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_parallel_tool_calls", 1)
    gateway = ScriptedGateway([Turn(requests=(evidence_call("E1", "c1"), request_for("get_investigation_timeline", {}, "c2"))), answer_turn("Done [T1].")])
    finished = await run_with(seeded, "Check things", gateway)
    assert [step.step_status for step in finished.tool_steps] == [ChatRunStepStatus.SUCCEEDED, ChatRunStepStatus.SKIPPED] and finished.tool_steps[1].outcome_code == "parallel_limit_reached"
    assert gateway.tool_results_seen_in_call(1)[1].tool_result_text.startswith("get_investigation_timeline skipped (parallel_limit_reached)")
    assert finished.outcome.stop_reason is ChatAnswerStopReason.ANSWERED and finished.run.tool_call_count == 1


async def test_at_85_percent_of_the_token_budget_the_next_turn_is_the_last_one(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_answer_token_budget", 5000)
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),), input_tokens=4200, output_tokens=50), answer_turn("Errors rose [T1].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert [call["allow_tool_requests"] for call in gateway.calls] == [True, False]
    assert finished.outcome.stop_reason is ChatAnswerStopReason.TOKEN_BUDGET_REACHED and finished.run.stop_reason == ChatAnswerStopReason.TOKEN_BUDGET_REACHED


async def test_just_below_85_percent_of_the_token_budget_the_loop_goes_on(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_answer_token_budget", 5000)
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),), input_tokens=4200, output_tokens=49), answer_turn("Errors rose [T1].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert [call["allow_tool_requests"] for call in gateway.calls] == [True, True] and finished.outcome.stop_reason is ChatAnswerStopReason.ANSWERED


async def test_there_is_no_wall_clock_limit_on_an_answer(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["now"])

    async def jump_an_hour() -> None:
        clock["now"] += 3600

    gateway = ScriptedGateway([Turn(requests=(evidence_call(),), before=jump_an_hour), Turn(text="Errors rose [T1].", before=jump_an_hour)])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert finished.outcome.status is ChatAnswerRunStatus.COMPLETED and finished.run.duration_milliseconds >= 2 * 3600 * 1000


# ── Tool refusals, unknown tools, access ─────────────────────────────────────────────────────────────────────────────────────
async def test_a_refused_call_is_traced_told_to_the_model_and_counts_as_a_tool_call(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(request_for("get_evidence", {"evidence_code": "R1"}),)), Turn(requests=(evidence_call("E1", "c2"),)), answer_turn("Errors rose [T2].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    refused, succeeded = finished.tool_steps
    assert (refused.step_status, refused.outcome_code, refused.citation_code) == (ChatRunStepStatus.REFUSED, "invalid_arguments", "T1")
    assert succeeded.citation_code == "T2" and finished.run.tool_call_count == 2
    told = gateway.tool_results_seen_in_call(1)[0].tool_result_text
    assert told.startswith("get_evidence refused (invalid_arguments)") and "evidence_code" in told
    assert [citation["code"] for citation in finished.assistant_messages[0].message_payload_json["citations"]] == ["T2"]
    assert finished.of(AnswerEventName.TOOL_FINISHED)[0].data["status"] == "refused"


async def test_a_tool_the_model_was_not_offered_is_refused_and_never_run(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(request_for("list_incidents", {"statuses": []}),)), answer_turn("I could not look that up.")])
    finished = await run_with(seeded, "List incidents", gateway)
    (step,) = finished.tool_steps
    assert (step.step_status, step.outcome_code, step.tool_name, step.citation_code) == (ChatRunStepStatus.REFUSED, "tool_not_available", "list_incidents", "T1")
    assert gateway.tool_results_seen_in_call(1)[0].tool_result_text.startswith("list_incidents refused (tool_not_available)")
    started = finished.of(AnswerEventName.TOOL_STARTED)[0].data
    assert started["tool"]["name"] == "list_incidents" and started["tool"]["source"] == "unknown"


async def test_arguments_that_were_not_valid_json_are_refused_with_the_reason(seeded: Seeded) -> None:
    from keigan.ai.llm_gateway import AgentToolRequest

    broken = AgentToolRequest(request_id="c1", tool_name="get_evidence", arguments=None, arguments_problem="The arguments were not valid JSON.")
    gateway = ScriptedGateway([Turn(requests=(broken,)), answer_turn("Sorry.")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (step,) = finished.tool_steps
    assert (step.step_status, step.outcome_code) == (ChatRunStepStatus.REFUSED, "invalid_arguments") and "not valid JSON" in step.outcome_message


async def test_a_call_that_names_another_investigation_is_pinned_to_the_one_of_the_scope(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(requests=(request_for("get_evidence", {"evidence_code": "E1", "investigation_id": str(uuid.uuid4())}),)), answer_turn("Errors rose [T1].")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (step,) = finished.tool_steps
    assert step.step_status == ChatRunStepStatus.SUCCEEDED and step.effective_arguments_json["investigation_id"] == seeded.investigation_id
    assert step.requested_arguments_json["investigation_id"] != seeded.investigation_id


async def test_access_removed_between_two_calls_of_one_answer_stops_the_answer_and_keeps_the_first_result() -> None:
    scoped = await create_scoped_application()
    async with open_session() as session:
        investigation = Investigation(application_id=scoped.application_id, executive_summary="Scoped investigation.")
        session.add(investigation)
        await session.flush()
        session.add(InvestigationEvidence(investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log_analytics", evidence_category="error_pattern", evidence_title="Scoped evidence", signal_strength="low"))
        investigation_id = investigation.investigation_id
    reader = user("scoped.reader@keigan.local", f"{scoped.application_code}_reader")

    async def remove_the_readers_access() -> None:
        async with open_session() as session:
            await session.execute(update(Application).where(Application.application_id == scoped.application_id).values(reader_group_name="someone_else_reader"))

    profile = await profile_for(reader, investigation_id)
    reader.application_roles_by_application_id = None
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), Turn(requests=(request_for("get_investigation_timeline", {}),), before=remove_the_readers_access)])
    set_correlation_id("corr-access-lost")
    finished = await ask(profile, "Show me evidence E1 and the timeline", current_user=reader, gateway=gateway)
    assert [step.step_status for step in finished.tool_steps] == [ChatRunStepStatus.SUCCEEDED, ChatRunStepStatus.REFUSED]
    assert finished.tool_steps[1].outcome_code == "access_denied"
    assert (finished.run.run_status, finished.run.error_code, finished.run.stop_reason) == (ChatAnswerRunStatus.FAILED, "access_lost_mid_run", ChatAnswerStopReason.FAILED)
    assert finished.assistant_messages == [] and finished.question_message.message_payload_json == {"answerRunId": finished.run.answer_run_id}
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert error["errorCode"] == "access_lost_mid_run" and error["detail"].startswith("Your access to that application changed while Keigan was answering")
    assert scoped.application_code not in error["detail"] and error["isRetryable"] is False


async def test_a_person_with_no_readable_application_gets_the_fixed_answer_and_no_model_call(seeded: Seeded) -> None:
    profile = await profile_for(ADMIN, seeded.investigation_id)
    empty_profile = ScopeProfile(**{**profile.__dict__, "readable_applications": (), "offered_tools": (), "bound_arguments": {}})
    gateway = ScriptedGateway([])
    finished = await ask(empty_profile, "What is the SLO status?", current_user=ADMIN, gateway=gateway)
    assert gateway.calls == []
    (answer,) = finished.assistant_messages
    assert answer.message_text == fixed_answer("no_access", "en") and answer.message_payload_json["isRefusal"] is True and answer.message_payload_json["isUnverified"] is False
    assert finished.run.run_status == ChatAnswerRunStatus.COMPLETED and finished.steps == []
    assert finished.names() == [AnswerEventName.ANSWER_STARTED, AnswerEventName.ANSWER_COMPLETED]


async def test_the_fixed_answer_is_written_in_the_persons_language(seeded: Seeded) -> None:
    profile = await profile_for(ADMIN, seeded.investigation_id)
    empty_profile = ScopeProfile(**{**profile.__dict__, "readable_applications": (), "offered_tools": (), "bound_arguments": {}})
    japanese_admin = replace(ADMIN, preferred_locale="ja")
    finished = await ask(empty_profile, "?", current_user=japanese_admin, gateway=ScriptedGateway([]))
    assert finished.assistant_messages[0].message_text == fixed_answer("no_access", "ja")


# ── Cancellation ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_stopping_between_two_steps_ends_the_run_cancelled_without_an_answer(seeded: Seeded) -> None:
    flag = CancellationFlag()
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),), before=lambda: _request(flag))])

    finished = await run_with(seeded, "Show me evidence E1", gateway, flag=flag)
    assert finished.outcome.status is ChatAnswerRunStatus.CANCELLED and finished.outcome.stop_reason is ChatAnswerStopReason.CANCELLED_BY_USER
    assert finished.assistant_messages == [] and (finished.run.run_status, finished.run.stop_reason, finished.run.error_code) == (ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, "cancelled")
    assert all(step.step_status in (ChatRunStepStatus.CANCELLED, ChatRunStepStatus.SUCCEEDED) for step in finished.steps)
    final = finished.of(AnswerEventName.ANSWER_FAILED)[0].data
    assert final["stopReason"] == "cancelled_by_user" and final["error"]["errorCode"] == "cancelled" and finished.names()[-1] is AnswerEventName.ANSWER_FAILED
    assert finished.question_message.message_payload_json == {"answerRunId": finished.run.answer_run_id}


async def _request(flag: CancellationFlag) -> None:
    flag.request()


async def test_stopping_during_a_tool_call_cancels_that_call_at_once(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.ai.tool_registry import tool_registry

    started_running = asyncio.Event()

    async def never_finishes(*arguments, **keyword_arguments):
        started_running.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(tool_registry, "execute_by_name", never_finishes)
    flag = CancellationFlag()
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),))])

    def stop_when_the_tool_starts(event: AnswerEvent, run_flag: CancellationFlag) -> None:
        if event.name is AnswerEventName.TOOL_STARTED:
            run_flag.request()

    finished = await asyncio.wait_for(run_with(seeded, "Show me evidence E1", gateway, flag=flag, on_event=stop_when_the_tool_starts), timeout=10)
    assert finished.run.run_status == ChatAnswerRunStatus.CANCELLED
    (tool_step,) = finished.tool_steps
    assert tool_step.step_status == ChatRunStepStatus.CANCELLED and tool_step.completed_at is not None
    assert finished.assistant_messages == []


async def test_a_stop_request_stored_in_the_run_row_by_another_pod_ends_the_run_at_the_next_step(seeded: Seeded) -> None:
    async def store_the_stop_request() -> None:
        async with open_session() as session:
            from keigan.entities.incident_entities import ChatAnswerRun

            run = (await session.scalars(select(ChatAnswerRun).where(ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING).order_by(ChatAnswerRun.started_at.desc()))).first()
            run.cancel_requested_at = utc_now()

    gateway = ScriptedGateway([Turn(requests=(evidence_call(),), before=store_the_stop_request)])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert finished.run.run_status == ChatAnswerRunStatus.CANCELLED and finished.assistant_messages == []


# ── Failures say what failed ─────────────────────────────────────────────────────────────────────────────────────────────────
async def test_a_model_that_times_out_ends_the_run_with_the_timeout_message_and_keeps_finished_steps(seeded: Seeded) -> None:
    set_correlation_id("corr-timeout")
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), LlmTimeoutException("provider says: connect to llm-prod.internal.example failed")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    assert (finished.run.run_status, finished.run.error_code, finished.run.stop_reason) == (ChatAnswerRunStatus.FAILED, "ai_timeout", ChatAnswerStopReason.FAILED)
    assert finished.tool_steps[0].step_status == ChatRunStepStatus.SUCCEEDED  # the finished steps stay in the trace
    assert finished.steps[-1].step_status == ChatRunStepStatus.CANCELLED  # the model turn that never ended
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert error["errorCode"] == "ai_timeout" and "(deep)" in error["detail"] and f"{get_settings().llm_request_timeout_seconds} seconds" in error["detail"]
    assert error["detail"].endswith("Reference corr-timeout.") and error["isRetryable"] is True and error["correlationId"] == "corr-timeout"
    assert "llm-prod" not in json.dumps(error)


async def test_an_exhausted_token_budget_is_reported_as_such(seeded: Seeded) -> None:
    gateway = ScriptedGateway([TokenBudgetExceededException("The daily AI token budget is used up.")])
    finished = await run_with(seeded, "Hello?", gateway)
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert (finished.run.error_code, error["errorCode"], error["isRetryable"]) == ("token_budget_exceeded", "token_budget_exceeded", False) and "daily AI budget" in error["detail"]


async def test_an_exhausted_application_budget_names_the_application_and_a_personal_one_says_your_account(seeded: Seeded) -> None:
    application_name = (await profile_for(ADMIN, seeded.investigation_id)).readable_applications[0].name
    application_budget = ScriptedGateway([TokenBudgetExceededException("used up", application_id=seeded.application_id)])
    finished = await run_with(seeded, "Hello?", application_budget)
    assert f"for {application_name} is used up" in finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]["detail"]
    personal_budget = ScriptedGateway([TokenBudgetExceededException("used up")])
    finished = await run_with(seeded, "Hello?", personal_budget)
    assert "for your account is used up" in finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]["detail"]


async def test_a_rate_limited_model_tells_the_person_how_long_to_wait(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Hello?", ScriptedGateway([LlmRateLimitedException("busy", retry_after_seconds=17)]))
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert error["errorCode"] == "ai_rate_limited" and "in 17 seconds" in error["detail"] and error["parameters"]["retryAfterSeconds"] == 17


async def test_a_model_that_cannot_use_tools_fails_the_run_with_the_tools_message(seeded: Seeded) -> None:
    gateway = ScriptedGateway([AgentToolsUnsupportedException("raw")])
    finished = await run_with(seeded, "Hello?", gateway)
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert (error["errorCode"], error["isRetryable"]) == ("ai_tools_unsupported", False) and "cannot use tools" in error["detail"] and "(deep)" in error["detail"]


async def test_two_protocol_errors_fail_the_run_instead_of_guessing(seeded: Seeded) -> None:
    gateway = ScriptedGateway([Turn(finish="protocol_error")])
    finished = await run_with(seeded, "Hello?", gateway)
    assert finished.run.error_code == "ai_tool_protocol_failed" and finished.assistant_messages == []


async def test_an_empty_model_answer_is_reported_as_unusable_not_shown_as_an_empty_answer(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Hello?", ScriptedGateway([answer_turn("   ")]))
    assert finished.run.error_code == "ai_output_invalid" and finished.assistant_messages == []


async def test_an_unclassified_failure_names_its_step_logs_the_stack_and_carries_the_reference(seeded: Seeded, caplog: pytest.LogCaptureFixture) -> None:
    set_correlation_id("corr-unclassified")
    gateway = ScriptedGateway([RuntimeError("secret internal detail with host db-prod.internal.example")])
    with caplog.at_level(logging.ERROR):
        finished = await run_with(seeded, "Hello?", gateway)
    error = finished.of(AnswerEventName.ANSWER_FAILED)[0].data["error"]
    assert error["errorCode"] == "internal_error" and error["detail"] == "Keigan hit an unexpected error while asking the AI model. Reference corr-unclassified. It has been logged."
    assert "db-prod" not in json.dumps(error) and finished.run.error_code == "internal_error"
    logged = [record for record in caplog.records if record.levelno >= logging.ERROR and record.exc_info]
    assert logged and "asking the AI model" in logged[0].getMessage() and logged[0].exc_info[0] is RuntimeError


async def test_the_channel_is_closed_after_the_final_event_so_a_reader_always_stops(seeded: Seeded) -> None:
    finished = await run_with(seeded, "Hello?", ScriptedGateway([RuntimeError("boom")]))
    assert finished.events[-1].is_final and sum(event.is_final for event in finished.events) == 1


# ── Before the run starts ────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_a_model_that_cannot_use_tools_is_refused_before_the_run_is_created_with_the_message_naming_the_tier(seeded: Seeded) -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock", json.dumps({"providers": {"mock": [{"model": "*", "tool_calling": "none"}]}}))
    engine = AskKeiganEngine(ScriptedGateway([], capabilities=capabilities))
    with pytest.raises(AgentToolsUnsupportedException, match=r"\(deep\)"):
        engine.prepare(await profile_for(ADMIN, seeded.investigation_id))


async def test_a_model_whose_context_window_cannot_hold_the_prompt_is_refused_before_the_run_is_created(seeded: Seeded) -> None:
    from keigan.exceptions.keigan_exceptions import LlmRequestRejectedException

    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock", json.dumps({"providers": {"mock": [{"model": "*", "max_context_tokens": 500}]}}))
    engine = AskKeiganEngine(ScriptedGateway([], capabilities=capabilities))
    with pytest.raises(LlmRequestRejectedException):
        engine.prepare(await profile_for(ADMIN, seeded.investigation_id))


async def test_the_prepared_run_describes_the_scope_prompt_and_tools_it_will_use(seeded: Seeded) -> None:
    prepared = AskKeiganEngine(ScriptedGateway([])).prepare(await profile_for(ADMIN, seeded.investigation_id))
    assert prepared.setup.prompt_key == "ask_keigan_investigation" and prepared.setup.model_tier == "deep" and prepared.setup.engine_version
    assert {spec.name for spec in prepared.tool_specs} == INVESTIGATION_TOOL_NAMES
    assert "application_code" not in next(spec for spec in prepared.tool_specs if spec.name == "search_knowledge").parameters_schema["properties"]  # bound by the scope


async def test_a_log_query_publishes_the_query_it_wrote_between_the_start_and_the_end_of_its_card(seeded: Seeded) -> None:
    finished = await run_with(seeded, "How many failed requests did claims-api have in the last 24 hours?")
    names = finished.names()
    assert names.index(AnswerEventName.TOOL_STARTED) < names.index(AnswerEventName.TOOL_PROGRESS) < names.index(AnswerEventName.TOOL_FINISHED)
    progress = finished.of(AnswerEventName.TOOL_PROGRESS)[0].data
    assert progress["stage"] == "query_generated" and progress["detail"]["queryText"] and progress["runStepId"] == finished.tool_steps[0].run_step_id
    assert re.fullmatch(r"\d+ failed requests on claims-api in the last 24 hours \[T1\]\.", finished.assistant_messages[0].message_text)  # the simulator's count changes with the clock
    audit_actions = [row.action_name for row in await _audit_rows_of_the_actor()]
    assert "ai.query.execute" in audit_actions  # the one write a tool may make: the audit row of the query


async def _audit_rows_of_the_actor() -> list[AuditEvent]:
    async with open_session() as session:
        return list((await session.scalars(select(AuditEvent).where(AuditEvent.actor_user_principal_name == ADMIN.user_principal_name))).all())


async def test_a_tool_that_hangs_fails_only_its_own_step_and_the_answer_still_completes(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.investigation_service import InvestigationService

    async def hang(*arguments, **keyword_arguments):
        await asyncio.sleep(30)

    monkeypatch.setattr(InvestigationService, "get_evidence_detail", hang)
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_timeout_seconds", 0.05)
    gateway = ScriptedGateway([Turn(requests=(evidence_call(),)), answer_turn("I could not open the evidence in time.")])
    finished = await run_with(seeded, "Show me evidence E1", gateway)
    (step,) = finished.tool_steps
    assert (step.step_status, step.outcome_code) == (ChatRunStepStatus.FAILED, "timeout")
    assert finished.run.run_status == ChatAnswerRunStatus.COMPLETED and finished.run.is_unverified is True
    assert gateway.tool_results_seen_in_call(1)[0].tool_result_text.startswith("get_evidence failed (timeout)")


# ── A run ended by someone else is never overwritten (H1) ────────────────────────────────────────────────────────────────────
async def audit_count_of(answer_run_id: str) -> int:
    async with open_session() as session:
        return len((await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == answer_run_id))).all())


async def test_a_run_that_another_process_interrupted_while_the_model_worked_is_not_overwritten_when_the_engine_finishes(seeded: Seeded, caplog: pytest.LogCaptureFixture) -> None:
    run_ids: list[str] = []

    def remember_run(event: AnswerEvent, _flag: CancellationFlag) -> None:
        if event.name is AnswerEventName.ANSWER_STARTED:
            run_ids.append(event.data["answerRunId"])

    async def interrupted_by_another_pod_meanwhile() -> None:
        assert await RunInterruption(AnswerRunRegistry()).interrupt(run_ids[0]) is True

    gateway = ScriptedGateway([Turn(text="Errors rose [E1].", before=interrupted_by_another_pod_meanwhile)])
    with caplog.at_level(logging.INFO, logger="keigan.services.ask_keigan_trace"):
        finished = await run_with(seeded, "What is E1?", gateway, on_event=remember_run)
    assert finished.outcome.was_ended_elsewhere is True and finished.outcome.assistant_message_id is None
    assert (finished.run.run_status, finished.run.error_code, finished.run.assistant_message_id) == (ChatAnswerRunStatus.FAILED, "answer_interrupted", None)
    assert finished.assistant_messages == [] and await audit_count_of(finished.run.answer_run_id) == 1
    assert AnswerEventName.ANSWER_COMPLETED not in finished.names() and AnswerEventName.ANSWER_FAILED not in finished.names()  # the loser publishes no final event
    assert any(record.levelno == logging.INFO and finished.run.answer_run_id in record.getMessage() for record in caplog.records)


async def test_an_engine_that_failed_after_another_process_ended_the_run_leaves_that_end_alone(seeded: Seeded) -> None:
    run_ids: list[str] = []

    def remember_run(event: AnswerEvent, _flag: CancellationFlag) -> None:
        if event.name is AnswerEventName.ANSWER_STARTED:
            run_ids.append(event.data["answerRunId"])

    async def interrupt_then_fail() -> None:
        assert await RunInterruption(AnswerRunRegistry()).interrupt(run_ids[0]) is True
        raise LlmTimeoutException("slow")

    finished = await run_with(seeded, "What is E1?", ScriptedGateway([Turn(text="x", before=interrupt_then_fail)]), on_event=remember_run)
    assert finished.outcome.was_ended_elsewhere is True
    assert (finished.run.run_status, finished.run.error_code) == (ChatAnswerRunStatus.FAILED, "answer_interrupted") and await audit_count_of(finished.run.answer_run_id) == 1


async def test_a_live_answer_refreshes_its_progress_while_the_model_works_and_stops_when_it_ends(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.ask_keigan_trace import TraceRecorder

    monkeypatch.setattr(get_settings(), "ask_keigan_progress_heartbeat_seconds", 0.001)
    beats = 0
    two_beats = asyncio.Event()
    original_touch = TraceRecorder.touch_progress

    async def counted_touch(recorder: TraceRecorder) -> bool:
        nonlocal beats
        beats += 1
        if beats >= 2:
            two_beats.set()
        return await original_touch(recorder)

    monkeypatch.setattr(TraceRecorder, "touch_progress", counted_touch)

    async def work_until_two_beats() -> None:
        await asyncio.wait_for(two_beats.wait(), timeout=10)  # the model is "slow": the answer cannot go on before the engine beat twice meanwhile

    finished = await run_with(seeded, "What is E1?", ScriptedGateway([Turn(text="Errors rose [E1].", before=work_until_two_beats)]))
    assert finished.outcome.status is ChatAnswerRunStatus.COMPLETED and beats >= 2
    beats_at_the_end = beats
    await asyncio.sleep(0.05)
    assert beats == beats_at_the_end  # the heartbeat does not outlive the answer

"""keigan/services/ask_keigan_service.py: starting, following, reading and stopping Ask Keigan answers (spec 23, 4.4.1, 7.5; AC-6, 26, 27)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from keigan.ai.ask_keigan_answer_format import HISTORY_SECTION_TITLE
from keigan.ai.llm_gateway import ModelTier
from keigan.ai.model_capabilities import resolve_model_capabilities
from keigan.config.database_config import open_session
from keigan.config.logging_config import set_correlation_id
from keigan.config.settings import LlmProviderName, get_settings
from keigan.dtos.ask_keigan_dtos import AnswerRequest
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.platform_entities import AuditEvent, LlmUsageRecord
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepStatus, ConversationScope, MessageAuthorRole
from keigan.exceptions.keigan_exceptions import (
    AgentToolsUnsupportedException, AnswerInProgressException, AnswerNotRunningException, DuplicateRequestException, ForbiddenException, LlmTimeoutException, NotFoundException,
    RateLimitedException,
)
from keigan.services.ask_keigan_engine import AskKeiganEngine
from keigan.services.ask_keigan_events import AnswerEventName
from keigan.services.ask_keigan_interruption import RunInterruption
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry
from keigan.services.ask_keigan_run_snapshot import AnswerRunSnapshotBuilder
from keigan.services.ask_keigan_service import AskKeiganService, StartedAnswer
from keigan.services.ask_keigan_trace import TRUNCATED_OUTPUT_KEY
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import utc_now
from support.ask_keigan_conversations import SeededInvestigation, open_global_chat, open_investigation_chat, open_teams_conversation, running_runs_of, runs_of, seed_investigation, stored_run
from support.ask_keigan_runs import ScriptedGateway, Turn, request_for, user
from support.chat_answer_runs import OWNER as OWNER_OF_STORED_RUNS, store_answer_run

pytestmark = pytest.mark.usefixtures("seed_context")

CLMJP_READER = user("service.reader@keigan.local", "CLMJP_reader")
OTHER_READER = user("service.other@keigan.local", "CLMJP_reader")
NO_ACCESS = user("noa.noaccess@keigan.local")
EVIDENCE_E2 = request_for("get_evidence", {"evidence_code": "E2"})


@dataclass
class Setup:
    investigation: SeededInvestigation
    conversation_id: str
    registry: AnswerRunRegistry


@pytest.fixture(autouse=True)
def generous_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-minute budget is shared by the whole test process, so tests that are not about it must not spend it."""
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 10_000)


@pytest.fixture
async def setup(seed_context) -> Setup:
    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    return Setup(investigation, await open_investigation_chat(CLMJP_READER, investigation.investigation_id), AnswerRunRegistry())


def question(text: str = "Show me evidence E2", client_request_id: uuid.UUID | None = None) -> AnswerRequest:
    return AnswerRequest(message_text=text, client_request_id=client_request_id or uuid.uuid4())


async def start(setup: Setup, gateway: ScriptedGateway | None, current_user=CLMJP_READER, request: AnswerRequest | None = None) -> StartedAnswer:
    """``gateway`` None: the engine uses the configured model (the offline mock provider in tests)."""
    async with open_session() as session:
        return await AskKeiganService(session, setup.registry, AskKeiganEngine(gateway) if gateway else AskKeiganEngine()).start(current_user, setup.conversation_id, request or question())


async def finish(setup: Setup, started: StartedAnswer) -> None:
    live_run = setup.registry.get(started.answer_run_id)
    if live_run and live_run.task:
        await asyncio.wait_for(live_run.task, timeout=10)


async def ask_and_finish(setup: Setup, gateway: ScriptedGateway | None, **options) -> StartedAnswer:
    started = await start(setup, gateway, **options)
    await finish(setup, started)
    return started


def blocked_turn(release: asyncio.Event, **options) -> Turn:
    async def wait_for_release() -> None:
        await release.wait()

    return Turn(before=wait_for_release, **options)


async def read_snapshot(setup: Setup, answer_run_id: str, current_user=CLMJP_READER):
    async with open_session() as session:
        return await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).snapshot(current_user, answer_run_id)


async def cancel(setup: Setup, answer_run_id: str, current_user=CLMJP_READER):
    async with open_session() as session:
        return await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).cancel(current_user, answer_run_id)


def answer_after_evidence() -> list[Turn]:
    return [Turn(requests=(EVIDENCE_E2,)), Turn(text="Release 41 was deployed before the spike [T1].")]


# ── Starting an answer ────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_an_answer_runs_to_the_end_in_the_background_and_streams_its_events(setup: Setup) -> None:
    started = await start(setup, ScriptedGateway(answer_after_evidence()))
    frames = [frame async for frame in AskKeiganService.stream(started.channel)]
    names = [frame.split("\n")[1].removeprefix("event: ") for frame in frames]
    assert names == [AnswerEventName.ANSWER_STARTED, AnswerEventName.TOOL_STARTED, AnswerEventName.TOOL_FINISHED, AnswerEventName.ANSWER_TEXT, AnswerEventName.ANSWER_COMPLETED]
    assert [frame.split("\n")[0] for frame in frames] == [f"id: {number}" for number in range(1, 6)]
    run = await stored_run(started.answer_run_id)
    assert run.run_status == ChatAnswerRunStatus.COMPLETED and run.stop_reason == ChatAnswerStopReason.ANSWERED
    assert setup.registry.get(started.answer_run_id) is None


async def test_the_question_is_stored_masked_before_the_run_starts_and_the_run_keeps_the_request_id(setup: Setup) -> None:
    request = question("Mail rui.reader@keigan.local what E2 means")
    started = await ask_and_finish(setup, ScriptedGateway([Turn(text="E2 is the release [E2].")]), request=request)
    run = await stored_run(started.answer_run_id)
    async with open_session() as session:
        stored_question = await session.get(ConversationMessage, run.user_message_id)
    assert "rui.reader@keigan.local" not in stored_question.message_text and "<EMAIL_1>" in stored_question.message_text
    assert stored_question.author_role == MessageAuthorRole.USER and stored_question.author_user_principal_name == CLMJP_READER.user_principal_name
    assert run.client_request_id == str(request.client_request_id) and run.requested_by_user_principal_name == CLMJP_READER.user_principal_name


async def test_the_question_is_linked_to_its_run_from_the_start_so_a_reload_during_the_answer_shows_it(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    async with open_session() as session:
        stored_question = await session.get(ConversationMessage, (await stored_run(started.answer_run_id)).user_message_id)
    assert stored_question.message_payload_json == {"answerRunId": started.answer_run_id}
    release.set()
    await finish(setup, started)


async def test_the_earlier_exchange_is_given_to_the_model_as_history(setup: Setup) -> None:
    await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]), request=question("What is E1?"))
    gateway = ScriptedGateway([Turn(text="E2 is the release [E2].")])
    await ask_and_finish(setup, gateway, request=question("And E2?"))
    history_section = next(entry.section for entry in gateway.calls[0]["transcript"] if entry.section and entry.section.title == HISTORY_SECTION_TITLE)
    assert "user: What is E1?" in history_section.content and "assistant: E1 is the error spike [E1]." in history_section.content


async def test_a_failed_answer_links_the_run_to_the_question_so_a_reload_shows_it(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway([LlmTimeoutException("slow")]))
    run = await stored_run(started.answer_run_id)
    async with open_session() as session:
        stored_question = await session.get(ConversationMessage, run.user_message_id)
    assert run.run_status == ChatAnswerRunStatus.FAILED and run.error_code == "ai_timeout"
    assert stored_question.message_payload_json == {"answerRunId": started.answer_run_id}


# ── Idempotency and one running answer per conversation ───────────────────────────────────────────────────────────────────────
async def test_the_same_request_id_returns_the_existing_run_instead_of_asking_twice(setup: Setup) -> None:
    request = question()
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]), request=request)
    gateway = ScriptedGateway([])
    with pytest.raises(DuplicateRequestException) as repeated:
        await start(setup, gateway, request=request)
    assert repeated.value.answer_run_id == first.answer_run_id and repeated.value.extra == {"answerRunId": first.answer_run_id}
    assert gateway.calls == [] and len(await runs_of(setup.conversation_id)) == 1


async def test_a_second_question_while_one_is_running_is_refused_with_the_running_run(setup: Setup) -> None:
    release = asyncio.Event()
    first = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    with pytest.raises(AnswerInProgressException) as busy:
        await start(setup, ScriptedGateway([]))
    assert busy.value.answer_run_id == first.answer_run_id and busy.value.status_code == 409
    assert "still answering your previous question" in busy.value.detail
    release.set()
    await finish(setup, first)
    await ask_and_finish(setup, ScriptedGateway([Turn(text="E2 is the release [E2].")]))  # the conversation is free again once the run ends
    assert len(await runs_of(setup.conversation_id)) == 2


async def test_a_run_still_running_in_another_pod_also_blocks_a_new_question(setup: Setup) -> None:
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:  # as if another pod were still working on it: running, recently active, nothing in this process's registry
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == first.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    with pytest.raises(AnswerInProgressException) as busy:
        await start(setup, ScriptedGateway([]))
    assert busy.value.answer_run_id == first.answer_run_id


async def test_a_silent_run_from_a_restarted_pod_is_ended_and_does_not_block_a_new_question(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    old = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == old.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now() - timedelta(minutes=10)))
    fresh = await ask_and_finish(setup, ScriptedGateway([Turn(text="E2 is the release [E2].")]))
    assert (await stored_run(old.answer_run_id)).error_code == "answer_interrupted"
    assert (await stored_run(fresh.answer_run_id)).run_status == ChatAnswerRunStatus.COMPLETED


# ── The Teams incident chat: the same service, an investigation profile that may withhold a tool, the outcome awaited by the caller ──
async def test_a_teams_conversation_is_answered_with_the_investigation_profile_without_the_tools_the_caller_withholds(setup: Setup) -> None:
    conversation_id = await open_teams_conversation(CLMJP_READER, setup.investigation.investigation_id)
    gateway = ScriptedGateway([Turn(text="Pool exhaustion [E1].")])
    async with open_session() as session:
        started = await AskKeiganService(session, setup.registry, AskKeiganEngine(gateway)).start(CLMJP_READER, conversation_id, question(), withheld_tool_names=frozenset({"query_logs"}))
    outcome = await asyncio.wait_for(started.task, timeout=10)
    run = await stored_run(started.answer_run_id)
    assert outcome.status is ChatAnswerRunStatus.COMPLETED and outcome.assistant_message_id == run.assistant_message_id
    assert "query_logs" not in {tool.name for tool in gateway.offered_tools} and "get_evidence" in {tool.name for tool in gateway.offered_tools}
    assert run.scope_snapshot_json["withheldTools"] == ["query_logs"] and run.conversation_scope == ConversationScope.INVESTIGATION and run.investigation_id == setup.investigation.investigation_id


async def test_a_teams_conversation_is_refused_when_its_owner_can_no_longer_read_the_application(setup: Setup) -> None:
    conversation_id = await open_teams_conversation(CLMJP_READER, setup.investigation.investigation_id)
    gateway = ScriptedGateway([])
    async with open_session() as session:
        with pytest.raises(ForbiddenException):
            await AskKeiganService(session, setup.registry, AskKeiganEngine(gateway)).start(user(CLMJP_READER.user_principal_name), conversation_id, question())
    assert gateway.calls == [] and await runs_of(conversation_id) == []


# ── Rate limit, access and unsupported models ─────────────────────────────────────────────────────────────────────────────────
async def test_the_chat_rate_limit_applies_and_names_the_wait(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 1)
    fast_reader = user("fast.reader@keigan.local", "CLMJP_reader")
    conversation_id = await open_investigation_chat(fast_reader, setup.investigation.investigation_id)
    setup = replace(setup, conversation_id=conversation_id)
    await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]), current_user=fast_reader)
    set_correlation_id("corr-rate")
    gateway = ScriptedGateway([])
    with pytest.raises(RateLimitedException) as limited:
        await start(setup, gateway, current_user=fast_reader)
    assert limited.value.detail == "You are sending questions too quickly. Try again in a few seconds. Reference corr-rate."
    assert gateway.calls == [] and len(await runs_of(conversation_id)) == 1


async def test_someone_else_cannot_ask_in_my_conversation(setup: Setup) -> None:
    gateway = ScriptedGateway([])
    with pytest.raises(ForbiddenException):
        await start(setup, gateway, current_user=OTHER_READER)
    assert gateway.calls == [] and await runs_of(setup.conversation_id) == []


async def test_an_unknown_conversation_is_not_found(setup: Setup) -> None:
    async with open_session() as session:
        with pytest.raises(NotFoundException):
            await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).start(CLMJP_READER, str(uuid.uuid4()), question())


async def test_a_person_whose_access_was_removed_is_refused_before_anything_is_stored_or_asked(setup: Setup) -> None:
    async with open_session() as session:
        usage_before = await session.scalar(select(func.count()).select_from(LlmUsageRecord))
    gateway = ScriptedGateway([])
    with pytest.raises(ForbiddenException):
        await start(setup, gateway, current_user=user(CLMJP_READER.user_principal_name))  # the same person, no longer in the CLMJP reader group
    async with open_session() as session:
        usage_after = await session.scalar(select(func.count()).select_from(LlmUsageRecord))
        question_count = await session.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == setup.conversation_id))
    assert gateway.calls == [] and usage_after == usage_before and question_count == 0 and await runs_of(setup.conversation_id) == []


async def test_a_person_with_no_application_cannot_open_an_investigation_chat_so_no_model_is_called(setup: Setup) -> None:
    gateway = ScriptedGateway([])
    with pytest.raises(ForbiddenException):
        await start(setup, gateway, current_user=NO_ACCESS)
    assert gateway.calls == []


async def test_a_model_that_cannot_use_tools_is_refused_before_a_question_or_a_run_is_stored(setup: Setup) -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock", json.dumps({"providers": {"mock": [{"model": "*", "tool_calling": "none"}]}}))
    gateway = ScriptedGateway([], capabilities=capabilities)
    with pytest.raises(AgentToolsUnsupportedException, match=rf"\({ModelTier.DEEP.value}\)"):
        await start(setup, gateway)
    async with open_session() as session:
        question_count = await session.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == setup.conversation_id))
    assert gateway.calls == [] and question_count == 0 and setup.registry.live_runs() == []


async def test_a_refused_start_frees_the_conversation_for_the_next_question(setup: Setup) -> None:
    with pytest.raises(ForbiddenException):
        await start(setup, ScriptedGateway([]), current_user=user(CLMJP_READER.user_principal_name))
    await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    assert setup.registry.live_runs() == []


# ── Stopping an answer ────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_stop_ends_a_running_answer_as_cancelled_without_an_answer_message(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="never shown")]))
    response = await cancel(setup, started.answer_run_id)
    assert response.cancel_requested is True and response.answer_run_id == started.answer_run_id
    await finish(setup, started)
    run = await stored_run(started.answer_run_id)
    assert (run.run_status, run.stop_reason, run.error_code) == (ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, "cancelled")
    assert run.cancel_requested_at is not None and run.assistant_message_id is None


async def test_stopping_twice_is_harmless_and_keeps_the_first_request_time(setup: Setup) -> None:
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:  # a run of another pod, which has not yet noticed the first request
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == first.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    await cancel(setup, first.answer_run_id)
    first_request_time = (await stored_run(first.answer_run_id)).cancel_requested_at
    assert first_request_time is not None
    assert (await cancel(setup, first.answer_run_id)).cancel_requested is True
    assert (await stored_run(first.answer_run_id)).cancel_requested_at == first_request_time


async def test_stopping_an_answer_that_already_finished_says_so(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    with pytest.raises(AnswerNotRunningException) as finished:
        await cancel(setup, started.answer_run_id)
    assert finished.value.status_code == 409 and finished.value.error_code == "answer_not_running" and finished.value.answer_run_id == started.answer_run_id


async def test_only_the_owner_can_stop_an_answer(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    with pytest.raises(ForbiddenException):
        await cancel(setup, started.answer_run_id, current_user=OTHER_READER)
    assert not setup.registry.get(started.answer_run_id).cancellation_flag.is_requested
    release.set()
    await finish(setup, started)


async def test_a_stop_request_for_a_run_in_another_pod_is_stored_for_that_pod_to_see(setup: Setup) -> None:
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == first.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    await cancel(setup, first.answer_run_id)
    assert (await stored_run(first.answer_run_id)).cancel_requested_at is not None


# ── The snapshot ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_the_snapshot_of_a_finished_run_has_its_steps_answer_and_citations(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert (snapshot.status, snapshot.stop_reason, snapshot.scope, snapshot.tool_call_count, snapshot.maximum_tool_calls) == ("completed", "answered", "investigation", 1, 6)
    assert [(step.kind, step.status) for step in snapshot.steps] == [("model_turn", "succeeded"), ("tool_call", "succeeded"), ("model_turn", "succeeded")]
    tool = snapshot.steps[1].tool
    assert (tool.name, tool.label, tool.citation_code, tool.bound_argument_names) == ("get_evidence", "Opened evidence", "T1", ["investigation_id"])
    assert tool.arguments["evidence_code"] == "E2" and tool.target.application_name == "Claims Processing (JP)" and tool.is_redacted is False
    assert tool.summary and tool.output_preview["summary"] == tool.summary and tool.output_character_count > 0
    assert snapshot.answer.markdown == "Release 41 was deployed before the spike [T1]." and [citation.code for citation in snapshot.answer.citations] == ["T1"]
    assert snapshot.answer.citations[0].run_step_id == snapshot.steps[1].run_step_id
    assert snapshot.error is None


async def test_the_snapshot_of_a_running_run_shows_the_steps_so_far_and_no_answer(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([Turn(requests=(EVIDENCE_E2,)), blocked_turn(release, text="Release 41 was deployed before the spike [T1].")]))
    for _ in range(100):  # the first tool finishes while the second model turn is held back
        snapshot = await read_snapshot(setup, started.answer_run_id)
        if any(step.tool and step.status == "succeeded" for step in snapshot.steps):
            break
        await asyncio.sleep(0.05)
    assert snapshot.status == "running" and snapshot.answer is None and snapshot.error is None and snapshot.stop_reason is None
    assert snapshot.last_sequence >= 3
    release.set()
    await finish(setup, started)


async def test_the_snapshot_of_a_failed_run_carries_the_catalogue_error_with_its_retry_flag(setup: Setup) -> None:
    set_correlation_id("corr-failed")
    started = await ask_and_finish(setup, ScriptedGateway([LlmTimeoutException("slow")]))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert snapshot.status == "failed" and snapshot.stop_reason == "failed" and snapshot.answer is None
    assert (snapshot.error.error_code, snapshot.error.is_retryable, snapshot.error.correlation_id) == ("ai_timeout", True, "corr-failed")
    assert "did not answer" in snapshot.error.detail and "Reference corr-failed." in snapshot.error.detail


async def test_the_snapshot_of_a_stopped_run_says_cancelled_and_is_not_retryable(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="never shown")]))
    await cancel(setup, started.answer_run_id)
    await finish(setup, started)
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert (snapshot.status, snapshot.stop_reason, snapshot.error.error_code, snapshot.error.is_retryable) == ("cancelled", "cancelled_by_user", "cancelled", False)


async def test_only_the_owner_reads_a_snapshot_and_an_unknown_run_is_not_found(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    with pytest.raises(ForbiddenException):
        await read_snapshot(setup, started.answer_run_id, current_user=OTHER_READER)
    with pytest.raises(NotFoundException):
        await read_snapshot(setup, str(uuid.uuid4()))


# ── Stale runs ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def make_running(answer_run_id: str, silent_for: timedelta) -> None:
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == answer_run_id).values(
            run_status=ChatAnswerRunStatus.RUNNING, completed_at=None, last_progress_at=utc_now() - silent_for))
        await session.execute(update(ChatRunStep).where(ChatRunStep.answer_run_id == answer_run_id, ChatRunStep.sequence_number == 1).values(step_status=ChatRunStepStatus.RUNNING))


async def test_a_stale_run_is_marked_interrupted_and_that_is_stored(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    await make_running(started.answer_run_id, timedelta(minutes=5))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert (snapshot.status, snapshot.stop_reason, snapshot.error.error_code, snapshot.error.is_retryable) == ("failed", "failed", "answer_interrupted", True)
    assert "interrupted" in snapshot.error.detail and snapshot.steps[0].status == "cancelled"
    stored = await stored_run(started.answer_run_id)
    assert stored.run_status == ChatAnswerRunStatus.FAILED and stored.error_code == "answer_interrupted" and stored.completed_at is not None


async def test_a_slow_run_that_is_still_writing_steps_is_left_alone(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    await make_running(started.answer_run_id, timedelta(seconds=20))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert snapshot.status == "running" and snapshot.error is None
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.RUNNING


async def test_a_silent_run_that_this_process_is_still_working_on_is_not_interrupted(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == started.answer_run_id).values(last_progress_at=utc_now() - timedelta(minutes=30)))
    assert (await read_snapshot(setup, started.answer_run_id)).status == "running"
    release.set()
    await finish(setup, started)
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.COMPLETED


async def test_a_stopped_stale_run_cannot_be_stopped_again(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    await make_running(started.answer_run_id, timedelta(minutes=5))
    with pytest.raises(AnswerNotRunningException):
        await cancel(setup, started.answer_run_id)


# ── Graceful shutdown ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_shutdown_cuts_the_live_tasks_and_ends_their_runs_as_interrupted(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([Turn(requests=(EVIDENCE_E2,)), blocked_turn(release, text="never")]))
    for _ in range(100):  # wait until the tool has run, so a finished step is kept
        if any(step.status == "succeeded" and step.tool for step in (await read_snapshot(setup, started.answer_run_id)).steps):
            break
        await asyncio.sleep(0.05)
    assert await RunInterruption(setup.registry).interrupt_live_runs() == [started.answer_run_id]
    run = await stored_run(started.answer_run_id)
    assert (run.run_status, run.stop_reason, run.error_code) == (ChatAnswerRunStatus.FAILED, ChatAnswerStopReason.FAILED, "answer_interrupted")
    assert setup.registry.live_runs() == []
    snapshot = await read_snapshot(setup, started.answer_run_id)
    assert [step.status for step in snapshot.steps][:2] == ["succeeded", "succeeded"] and snapshot.steps[-1].status == "cancelled"
    assert snapshot.error.error_code == "answer_interrupted"
    async with open_session() as session:
        stored_question = await session.get(ConversationMessage, run.user_message_id)
    assert stored_question.message_payload_json == {"answerRunId": started.answer_run_id}


async def test_shutdown_with_nothing_running_does_nothing(setup: Setup) -> None:
    assert await RunInterruption(setup.registry).interrupt_live_runs() == []


async def test_a_run_that_already_ended_is_not_interrupted_twice(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    assert await RunInterruption(setup.registry).interrupt(started.answer_run_id) is False
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.COMPLETED


# ── The full output of one step ───────────────────────────────────────────────────────────────────────────────────────────────
async def test_the_full_output_of_a_tool_call_is_returned_to_the_owner(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    tool_step = snapshot.steps[1]
    async with open_session() as session:
        output = await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).step_output(CLMJP_READER, started.answer_run_id, tool_step.run_step_id)
        stored = await session.get(ChatRunStep, tool_step.run_step_id)
    assert output.run_step_id == tool_step.run_step_id and output.output == stored.output_json and output.output["evidence_code"] == "E2"
    assert output.output_character_count == stored.output_character_count and output.output_is_truncated is False
    assert output.model_view_text == stored.model_view_text and output.model_view_sha256 == stored.model_view_sha256 and len(output.model_view_sha256) == 64


async def test_a_step_output_is_for_the_owner_of_a_readable_tool_call_of_that_run_only(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    snapshot = await read_snapshot(setup, started.answer_run_id)
    model_turn_id, tool_step_id = snapshot.steps[0].run_step_id, snapshot.steps[1].run_step_id
    other_run = await ask_and_finish(replace(setup), ScriptedGateway(answer_after_evidence()), request=question("Again, E2"))

    async def read_output(current_user, answer_run_id: str, run_step_id: str):
        async with open_session() as session:
            return await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).step_output(current_user, answer_run_id, run_step_id)

    with pytest.raises(ForbiddenException):
        await read_output(OTHER_READER, started.answer_run_id, tool_step_id)
    with pytest.raises(NotFoundException):
        await read_output(CLMJP_READER, started.answer_run_id, model_turn_id)  # a model turn has no stored tool output
    with pytest.raises(NotFoundException):
        await read_output(CLMJP_READER, other_run.answer_run_id, tool_step_id)  # the step belongs to another run
    with pytest.raises(ForbiddenException):
        await read_output(user(CLMJP_READER.user_principal_name), started.answer_run_id, tool_step_id)  # access to the application was removed


# ── A person who lost access to the application no longer reads its answers (H2) ───────────────────────────────────────────────
LOST_ACCESS = user(CLMJP_READER.user_principal_name)  # the same person, no longer in the CLMJP reader group


async def test_a_person_who_lost_access_to_the_application_cannot_read_the_snapshot_of_an_earlier_answer(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway([Turn(requests=(EVIDENCE_E2,), text="Checking release 41 evidence."), Turn(text="Release 41 was deployed before the spike [T1].")]))
    assert (await read_snapshot(setup, started.answer_run_id)).answer is not None  # the owner could read it while the access lasted
    with pytest.raises(ForbiddenException) as refused:
        await read_snapshot(setup, started.answer_run_id, current_user=LOST_ACCESS)
    shown_to_the_person = f"{refused.value.detail} {refused.value}"
    assert "Release 41" not in shown_to_the_person and "Checking release" not in shown_to_the_person and "Opened evidence" not in shown_to_the_person


async def test_a_person_who_lost_access_cannot_read_a_step_output_either(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    tool_step_id = (await read_snapshot(setup, started.answer_run_id)).steps[1].run_step_id
    async with open_session() as session:
        with pytest.raises(ForbiddenException):
            await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).step_output(LOST_ACCESS, started.answer_run_id, tool_step_id)


async def test_a_person_who_lost_access_may_still_stop_their_own_running_answer(setup: Setup) -> None:
    # Stopping reveals nothing (the reply is the run id and "stop requested") and ends a run that reads data the person may no longer see: it is allowed on ownership alone.
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="never shown")]))
    response = await cancel(setup, started.answer_run_id, current_user=LOST_ACCESS)
    assert response.cancel_requested is True
    await finish(setup, started)
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.CANCELLED


async def test_a_person_who_lost_access_still_cannot_stop_someone_elses_answer(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    with pytest.raises(ForbiddenException):
        await cancel(setup, started.answer_run_id, current_user=user(OTHER_READER.user_principal_name))
    release.set()
    await finish(setup, started)


# ── Redaction of a step on an application the reader lost (a global answer can read several applications) ───────────────────────
async def test_in_a_global_answer_a_step_on_a_lost_application_is_redacted(setup: Setup, seed_context) -> None:
    clmjp_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        stored = await store_answer_run(session, conversation_scope=ConversationScope.KEIGAN_AI_CHAT)
        await session.execute(update(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id, ChatRunStep.sequence_number == 2).values(application_id=clmjp_id))
        run = await session.get(ChatAnswerRun, stored.answer_run_id)
    async with open_session() as session:
        snapshot = await AnswerRunSnapshotBuilder(session, setup.registry).build(run, user("someone@keigan.local"))
    tool = snapshot.steps[1].tool
    assert tool.is_redacted is True and tool.arguments == {} and tool.output_preview is None and tool.summary is None
    assert tool.target.application_id is None and tool.target.application_name is None and tool.target.records == []
    assert (tool.name, tool.citation_code, tool.label) == ("get_slo_status", "T1", "Checked SLO status")


async def test_the_full_output_of_a_step_on_a_lost_application_is_refused_in_a_global_answer(setup: Setup, seed_context) -> None:
    clmjp_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        stored = await store_answer_run(session, conversation_scope=ConversationScope.KEIGAN_AI_CHAT)
        tool_step = (await session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id, ChatRunStep.sequence_number == 2))).one()
        tool_step.application_id = clmjp_id
        tool_step_id = tool_step.run_step_id
    owner = user(OWNER_OF_STORED_RUNS)  # no group: the application is not readable
    async with open_session() as session:
        with pytest.raises(ForbiddenException, match="no longer have access"):
            await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).step_output(owner, stored.answer_run_id, tool_step_id)


# ── A long silence is not a dead run (H1) ─────────────────────────────────────────────────────────────────────────────────────
async def test_a_slow_model_turn_is_kept_alive_by_the_heartbeat_so_another_pod_does_not_interrupt_it(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.ask_keigan_trace import TraceRecorder

    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    monkeypatch.setattr(get_settings(), "ask_keigan_progress_heartbeat_seconds", 0.001)
    beat_after_the_silence = asyncio.Event()
    silence_was_made = asyncio.Event()
    original_touch = TraceRecorder.touch_progress

    async def touch_and_report(recorder: TraceRecorder) -> bool:
        still_running = await original_touch(recorder)
        if silence_was_made.is_set():
            beat_after_the_silence.set()
        return still_running

    monkeypatch.setattr(TraceRecorder, "touch_progress", touch_and_report)
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    async with open_session() as session:  # the turn has been silent for ten minutes, as a slow model with retries can be
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == started.answer_run_id).values(last_progress_at=utc_now() - timedelta(minutes=10)))
    silence_was_made.set()
    await asyncio.wait_for(beat_after_the_silence.wait(), timeout=10)
    another_pod = AnswerRunRegistry()  # it does not know the run, so only the stored progress tells it whether the run is alive
    snapshot = await read_snapshot(Setup(setup.investigation, setup.conversation_id, another_pod), started.answer_run_id)
    assert snapshot.status == "running" and snapshot.error is None
    release.set()
    await finish(setup, started)
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.COMPLETED


async def test_a_run_another_pod_interrupted_stays_interrupted_when_the_slow_answer_finishes(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    assert await RunInterruption(AnswerRunRegistry()).interrupt(started.answer_run_id) is True
    release.set()
    frames = [frame async for frame in AskKeiganService.stream(started.channel)]
    await finish(setup, started)
    run = await stored_run(started.answer_run_id)
    assert (run.run_status, run.error_code, run.assistant_message_id) == (ChatAnswerRunStatus.FAILED, "answer_interrupted", None)
    assert not any("event: answer.completed" in frame for frame in frames)
    async with open_session() as session:
        assistant_messages = (await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == setup.conversation_id, ConversationMessage.author_role == MessageAuthorRole.ASSISTANT))).all()
        audit_rows = (await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == started.answer_run_id))).all()
    assert assistant_messages == [] and len(audit_rows) == 1
    await ask_and_finish(setup, ScriptedGateway([Turn(text="E2 is the release [E2].")]))  # and the conversation is free for exactly one new answer


# ── Stopping: the request is stored before the flag is set, and a lost race is reported ────────────────────────────────────────
async def test_the_stop_request_is_stored_before_the_in_process_flag_is_set(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.ask_keigan_trace import TraceRecorder

    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="never shown")]))
    flag = setup.registry.get(started.answer_run_id).cancellation_flag
    flag_state_when_stored: list[bool] = []
    original_store = TraceRecorder.store_cancel_request

    async def observe_store(answer_run_id: str) -> bool:
        flag_state_when_stored.append(flag.is_requested)
        stored = await original_store(answer_run_id)
        flag_state_when_stored.append(flag.is_requested)
        return stored

    monkeypatch.setattr(TraceRecorder, "store_cancel_request", staticmethod(observe_store))
    await cancel(setup, started.answer_run_id)
    assert flag_state_when_stored == [False, False] and flag.is_requested is True
    assert (await stored_run(started.answer_run_id)).cancel_requested_at is not None
    await finish(setup, started)


async def test_stopping_a_run_that_ended_between_the_check_and_the_write_says_it_is_not_running(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.ask_keigan_trace import TraceRecorder

    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    original_store = TraceRecorder.store_cancel_request

    async def store_after_the_run_ended(answer_run_id: str) -> bool:
        release.set()
        await finish(setup, started)
        return await original_store(answer_run_id)

    monkeypatch.setattr(TraceRecorder, "store_cancel_request", staticmethod(store_after_the_run_ended))
    with pytest.raises(AnswerNotRunningException):
        await cancel(setup, started.answer_run_id)
    assert (await stored_run(started.answer_run_id)).run_status == ChatAnswerRunStatus.COMPLETED


# ── Two pods racing: the database decides, and the answer is the specific one (M4) ───────────────────────────────────────────────
def skip_the_first_check(original):
    """``original`` with its first call passing without looking (the other pod had not written yet when this one checked); later calls are the real check."""
    calls = 0

    async def checked_from_the_second_call(service: AskKeiganService, *arguments, **keyword_arguments) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            await original(service, *arguments, **keyword_arguments)

    return checked_from_the_second_call


async def question_count(conversation_id: str) -> int:
    async with open_session() as session:
        return await session.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))


async def test_the_same_request_id_arriving_at_two_pods_at_once_is_a_duplicate_request_not_a_server_error(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    request = question()
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]), request=request)
    questions_before = await question_count(setup.conversation_id)
    monkeypatch.setattr(AskKeiganService, "_ensure_not_a_repeat", skip_the_first_check(AskKeiganService._ensure_not_a_repeat))
    gateway = ScriptedGateway([])
    with pytest.raises(DuplicateRequestException) as repeated:
        await start(setup, gateway, request=request)
    assert repeated.value.answer_run_id == first.answer_run_id and repeated.value.status_code == 409
    assert gateway.calls == [] and await question_count(setup.conversation_id) == questions_before and setup.registry.live_runs() == []


async def test_two_pods_starting_an_answer_in_one_conversation_at_once_leave_one_run_and_the_other_gets_answer_in_progress(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:  # the other pod's run, written after this pod's check and still beating
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == first.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    questions_before = await question_count(setup.conversation_id)
    monkeypatch.setattr(AskKeiganService, "_ensure_no_other_pod_is_answering", skip_the_first_check(AskKeiganService._ensure_no_other_pod_is_answering))
    with pytest.raises(AnswerInProgressException) as busy:
        await start(setup, ScriptedGateway([]))
    assert busy.value.answer_run_id == first.answer_run_id and busy.value.status_code == 409
    assert await question_count(setup.conversation_id) == questions_before and len(await running_runs_of(setup.conversation_id)) == 1 and setup.registry.live_runs() == []


# ── Deleting a conversation stops its running answer first (M7) ─────────────────────────────────────────────────────────────────
async def delete_conversation(setup: Setup, current_user=CLMJP_READER) -> None:
    async with open_session() as session:
        await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).delete_conversation(current_user, setup.conversation_id)


async def test_deleting_a_conversation_stops_its_running_answer_and_only_then_removes_it(setup: Setup, caplog: pytest.LogCaptureFixture) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="never shown")]))
    task = setup.registry.get(started.answer_run_id).task
    with caplog.at_level(logging.WARNING):
        await delete_conversation(setup)
    assert task.done() and task.exception() is None and setup.registry.live_runs() == []
    async with open_session() as session:
        assert await session.get(Conversation, setup.conversation_id) is None
        assert await session.get(ChatAnswerRun, started.answer_run_id) is None
        audit = (await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == started.answer_run_id))).one()
    assert audit.action_details_json["stopReason"] == "cancelled_by_user"  # the audit row of the stopped run outlives the conversation
    assert not any("marked interrupted" in record.getMessage() or "unexpected error" in record.getMessage() for record in caplog.records)


async def test_deleting_a_conversation_whose_answer_runs_in_another_pod_asks_that_pod_to_stop_and_refuses_for_now(setup: Setup) -> None:
    first = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == first.answer_run_id).values(run_status=ChatAnswerRunStatus.RUNNING, last_progress_at=utc_now()))
    with pytest.raises(AnswerInProgressException) as busy:
        await delete_conversation(setup)
    assert busy.value.answer_run_id == first.answer_run_id
    assert (await stored_run(first.answer_run_id)).cancel_requested_at is not None  # the other pod stops at its next step; the person deletes again
    async with open_session() as session:
        assert await session.get(Conversation, setup.conversation_id) is not None


async def test_deleting_a_conversation_whose_answer_went_silent_ends_that_run_and_deletes(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_stale_run_seconds", 60)
    old = await ask_and_finish(setup, ScriptedGateway([Turn(text="E1 is the error spike [E1].")]))
    await make_running(old.answer_run_id, timedelta(minutes=10))
    await delete_conversation(setup)
    async with open_session() as session:
        assert await session.get(Conversation, setup.conversation_id) is None


async def test_only_the_owner_can_delete_a_conversation_and_nothing_is_stopped_for_anyone_else(setup: Setup) -> None:
    release = asyncio.Event()
    started = await start(setup, ScriptedGateway([blocked_turn(release, text="Done [E1].")]))
    with pytest.raises(ForbiddenException):
        await delete_conversation(setup, current_user=OTHER_READER)
    assert not setup.registry.get(started.answer_run_id).cancellation_flag.is_requested
    release.set()
    await finish(setup, started)


async def test_deleting_a_conversation_with_no_running_answer_removes_it_with_its_runs(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    await delete_conversation(setup)
    async with open_session() as session:
        assert await session.get(Conversation, setup.conversation_id) is None and await session.get(ChatAnswerRun, started.answer_run_id) is None


# ── The snapshot carries the trust flags and the error parameters of the stored run (frontend contract) ───────────────────────────
async def stored_global_run_with_tool_output(output_json: dict, **step_values) -> str:
    async with open_session() as session:
        stored = await store_answer_run(session, conversation_scope=ConversationScope.KEIGAN_AI_CHAT)
        await session.execute(update(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id, ChatRunStep.sequence_number == 2).values(output_json=output_json, **step_values))
    return stored.answer_run_id


async def snapshot_of_stored_run(setup: Setup, answer_run_id: str):
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, answer_run_id)
        return await AnswerRunSnapshotBuilder(session, setup.registry).build(run, user(OWNER_OF_STORED_RUNS))


async def test_the_snapshot_reads_the_trust_flags_from_the_whole_stored_output_not_from_the_preview(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_output_preview_characters", 200)
    output = {"summary": "many changes", "is_simulated": True, "total_count": 61, "is_truncated": True, "items": ["z" * 50] * 20}
    snapshot = await snapshot_of_stored_run(setup, await stored_global_run_with_tool_output(output, output_character_count=1100))
    tool = snapshot.steps[1].tool
    assert isinstance(tool.output_preview, str)  # long: the preview is the first characters of the text
    assert (tool.is_simulated, tool.total_count, tool.is_truncated) == (True, 61, True)


async def test_the_snapshot_reads_the_trust_flags_kept_beside_an_output_that_was_cut_for_storage(setup: Setup) -> None:
    cut_output = {TRUNCATED_OUTPUT_KEY: '{"summary":"huge","items":["y' + "y" * 300, "total_count": 90, "is_truncated": True}
    snapshot = await snapshot_of_stored_run(setup, await stored_global_run_with_tool_output(cut_output, output_is_truncated=True, output_character_count=70_000))
    tool = snapshot.steps[1].tool
    assert (tool.is_simulated, tool.total_count, tool.is_truncated, tool.output_is_truncated) == (None, 90, True, True)


async def test_a_tool_with_none_of_these_notions_has_null_flags_in_the_snapshot(setup: Setup) -> None:
    snapshot = await snapshot_of_stored_run(setup, await stored_global_run_with_tool_output({"summary": "4 SLOs", "items": []}))
    tool = snapshot.steps[1].tool
    assert (tool.is_simulated, tool.total_count, tool.is_truncated) == (None, None, None)
    assert {"isSimulated", "totalCount", "isTruncated"} <= set(tool.model_dump(by_alias=True))


async def test_a_reload_words_a_failed_run_from_the_parameters_stored_with_it(setup: Setup) -> None:
    answer_run_id = await stored_global_run_with_tool_output({"summary": "x"})
    async with open_session() as session:
        await session.execute(update(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == answer_run_id).values(
            run_status=ChatAnswerRunStatus.FAILED, stop_reason=ChatAnswerStopReason.FAILED, error_code="internal_error", completed_at=utc_now(),
            error_parameters_json={"stepDescription": "running \"Checked recent changes\"", "reference": "corr-9"}, correlation_id="corr-9",
        ))
    error = (await snapshot_of_stored_run(setup, answer_run_id)).error
    assert 'while running "Checked recent changes"' in error.detail and "corr-9" in error.detail
    assert error.parameters == {"stepDescription": "running \"Checked recent changes\"", "reference": "corr-9"}


# ── The global scope: the Keigan AI chat page answers through the same engine ──────────────────────────────────────────────────
RUI = user("rui.global@keigan.local", "CLMJP_reader", "PAYAU_reader")
RUI_WITHOUT_PAYAU = user(RUI.user_principal_name, "CLMJP_reader")  # the same person after losing one application
RUI_WITHOUT_CLMJP = user(RUI.user_principal_name, "PAYAU_reader")
LOST_EVERYTHING = user(RUI.user_principal_name)
SLO_QUESTION = "How are the SLOs doing?"


def slo_status_of(application_code: str, request_id: str):
    return request_for("get_slo_status", {"application_codes": [application_code]}, request_id)


async def in_a_global_chat(setup: Setup, current_user=RUI, application_ids: tuple[str, ...] = ()) -> Setup:
    return replace(setup, conversation_id=await open_global_chat(current_user, application_ids))


async def test_a_global_answer_runs_end_to_end_with_the_mock_provider(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_global", 3)
    chat = await in_a_global_chat(setup)
    started = await ask_and_finish(chat, None, current_user=RUI, request=question(SLO_QUESTION))
    run = await stored_run(started.answer_run_id)
    assert (run.run_status, run.stop_reason, run.conversation_scope, run.investigation_id, run.prompt_key) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED, "keigan_ai_chat", None, "ask_keigan_global")
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=RUI)
    assert (snapshot.scope, snapshot.maximum_tool_calls, snapshot.tool_call_count) == ("global", 3, 1)
    (tool_step,) = [step for step in snapshot.steps if step.tool]
    assert (tool_step.tool.name, tool_step.tool.citation_code, tool_step.status, tool_step.tool.bound_argument_names) == ("get_slo_status", "T1", "succeeded", [])
    assert "[T1]" in snapshot.answer.markdown and snapshot.answer.is_refusal is False


async def test_a_new_global_conversation_is_titled_by_its_first_question_only(setup: Setup) -> None:
    chat = await in_a_global_chat(setup)
    long_question = "Which of my applications had the most failed requests over the last week, and what changed just before the worst day began?"
    await ask_and_finish(chat, ScriptedGateway([Turn(text="Nothing to look up.")]), current_user=RUI, request=question(long_question))
    await ask_and_finish(chat, ScriptedGateway([Turn(text="Still nothing.")]), current_user=RUI, request=question("And yesterday?"))
    async with open_session() as session:
        title = (await session.get(Conversation, chat.conversation_id)).conversation_title
    assert title == truncate_text(long_question, 60) and len(title) == 60


async def test_a_global_answer_is_told_its_applications_and_chooses_its_own_arguments(setup: Setup) -> None:
    chat = await in_a_global_chat(setup)
    gateway = ScriptedGateway([Turn(requests=(slo_status_of("PAYAU", "call_1"),)), Turn(text="PAYAU has SLOs [T1].")])
    started = await ask_and_finish(chat, gateway, current_user=RUI, request=question(SLO_QUESTION))
    system_prompt = gateway.calls[0]["system_prompt"]
    assert "CLMJP — " in system_prompt and "PAYAU — " in system_prompt and "CHAD — " not in system_prompt and "Today's date is" in system_prompt
    assert {tool.name for tool in gateway.offered_tools} >= {"query_logs", "list_recent_changes", "search_knowledge", "get_slo_status"}
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=RUI)
    tool = next(step.tool for step in snapshot.steps if step.tool)
    assert tool.arguments == {"application_codes": ["PAYAU"]} and tool.bound_argument_names == []


async def test_a_global_conversation_scoped_to_one_application_offers_only_that_application(setup: Setup, seed_context) -> None:
    chat = await in_a_global_chat(setup, application_ids=(seed_context.application_ids_by_code["CLMJP"],))
    gateway = ScriptedGateway([Turn(text="Nothing to look up.")])
    await ask_and_finish(chat, gateway, current_user=RUI, request=question("Is there a runbook?"))
    runbooks = next(tool for tool in gateway.offered_tools if tool.name == "find_runbooks")
    assert runbooks.parameters_schema["properties"]["application_code"]["enum"] == ["CLMJP"]


async def test_a_global_answer_cannot_read_an_application_the_person_cannot(setup: Setup) -> None:
    chat = await in_a_global_chat(setup)
    gateway = ScriptedGateway([Turn(requests=(request_for("find_runbooks", {"application_code": "CHAD", "symptoms": "timeouts"}),)), Turn(text="I could not check that.")])
    started = await ask_and_finish(chat, gateway, current_user=RUI, request=question("Is there a runbook for CHAD timeouts?"))
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=RUI)
    step = next(step for step in snapshot.steps if step.tool)
    assert (step.status, step.tool.outcome_code, step.tool.output_preview) == ("refused", "access_denied", None)
    assert (await stored_run(started.answer_run_id)).used_application_ids_json == []


async def test_a_person_with_no_application_gets_the_fixed_answer_and_no_model_is_called(setup: Setup) -> None:
    async with open_session() as session:
        usage_before = await session.scalar(select(func.count()).select_from(LlmUsageRecord))
    chat = await in_a_global_chat(setup, NO_ACCESS)
    gateway = ScriptedGateway([])
    started = await ask_and_finish(chat, gateway, current_user=NO_ACCESS, request=question(SLO_QUESTION))
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=NO_ACCESS)
    async with open_session() as session:
        usage_after = await session.scalar(select(func.count()).select_from(LlmUsageRecord))
    assert gateway.calls == [] and usage_after == usage_before
    assert snapshot.status == "completed" and snapshot.answer.is_refusal is True and "don't have access to any applications" in snapshot.answer.markdown


async def test_an_investigation_conversation_is_still_answered_with_the_investigation_scope(setup: Setup) -> None:
    started = await ask_and_finish(setup, ScriptedGateway(answer_after_evidence()))
    run = await stored_run(started.answer_run_id)
    assert (run.conversation_scope, run.prompt_key, run.scope_snapshot_json["scope"]) == ("investigation", "ask_keigan_investigation", "investigation")


async def test_a_global_conversation_of_someone_else_is_refused(setup: Setup) -> None:
    chat = await in_a_global_chat(setup, RUI)
    gateway = ScriptedGateway([])
    with pytest.raises(ForbiddenException):
        await start(chat, gateway, current_user=user("someone.else@keigan.local", "CLMJP_reader", "PAYAU_reader"))
    assert gateway.calls == []


# ── The access gap: an answer that used an application the person has since lost ────────────────────────────────────────────────
async def answered_across_two_applications(setup: Setup) -> tuple[Setup, StartedAnswer]:
    chat = await in_a_global_chat(setup)
    gateway = ScriptedGateway([
        Turn(requests=(slo_status_of("CLMJP", "call_1"), slo_status_of("PAYAU", "call_2")), text="Checking both applications."),
        Turn(text="CLMJP and PAYAU both have SLOs [T1] [T2]."),
    ])
    return chat, await ask_and_finish(chat, gateway, current_user=RUI, request=question(SLO_QUESTION))


async def read_step_output(setup: Setup, current_user, answer_run_id: str, run_step_id: str):
    async with open_session() as session:
        return await AskKeiganService(session, setup.registry, AskKeiganEngine(ScriptedGateway([]))).step_output(current_user, answer_run_id, run_step_id)


async def test_a_global_answer_records_every_application_its_tools_read(setup: Setup, seed_context) -> None:
    _, started = await answered_across_two_applications(setup)
    expected = sorted([seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]])
    assert (await stored_run(started.answer_run_id)).used_application_ids_json == expected


async def test_the_person_who_still_reads_both_applications_reads_the_answer_and_its_steps(setup: Setup) -> None:
    chat, started = await answered_across_two_applications(setup)
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=RUI)
    assert snapshot.answer.markdown == "CLMJP and PAYAU both have SLOs [T1] [T2]." and [step.tool.is_redacted for step in snapshot.steps if step.tool] == [False, False]
    assert (await read_step_output(chat, RUI, started.answer_run_id, next(step.run_step_id for step in snapshot.steps if step.tool))).output["summary"]


@pytest.mark.parametrize("person_after_the_loss", [RUI_WITHOUT_PAYAU, RUI_WITHOUT_CLMJP, LOST_EVERYTHING], ids=["lost PAYAU", "lost CLMJP", "lost both"])
async def test_a_person_who_lost_any_application_the_answer_used_cannot_read_its_snapshot(setup: Setup, person_after_the_loss) -> None:
    chat, started = await answered_across_two_applications(setup)
    with pytest.raises(ForbiddenException) as refused:
        await read_snapshot(chat, started.answer_run_id, current_user=person_after_the_loss)
    shown_to_the_person = f"{refused.value.detail} {refused.value}"
    assert "SLO" not in shown_to_the_person and "Checking both" not in shown_to_the_person and "Checked SLO status" not in shown_to_the_person


@pytest.mark.parametrize("person_after_the_loss", [RUI_WITHOUT_PAYAU, RUI_WITHOUT_CLMJP], ids=["lost PAYAU", "lost CLMJP"])
async def test_a_person_who_lost_one_of_two_applications_cannot_read_any_step_output_of_the_answer(setup: Setup, person_after_the_loss) -> None:
    chat, started = await answered_across_two_applications(setup)
    snapshot = await read_snapshot(chat, started.answer_run_id, current_user=RUI)
    for step in (step for step in snapshot.steps if step.tool):  # also the step on the application the person can still read: the answer joins them
        with pytest.raises(ForbiddenException):
            await read_step_output(chat, person_after_the_loss, started.answer_run_id, step.run_step_id)


async def test_losing_an_application_an_answer_did_not_use_does_not_hide_it(setup: Setup) -> None:
    chat = await in_a_global_chat(setup)
    started = await ask_and_finish(chat, ScriptedGateway([Turn(requests=(slo_status_of("CLMJP", "call_1"),)), Turn(text="CLMJP has SLOs [T1].")]), current_user=RUI, request=question(SLO_QUESTION))
    assert (await read_snapshot(chat, started.answer_run_id, current_user=RUI_WITHOUT_PAYAU)).answer.markdown == "CLMJP has SLOs [T1]."


async def test_the_answers_the_person_lost_are_not_sent_to_the_model_as_history_of_their_next_question(setup: Setup) -> None:
    chat, _ = await answered_across_two_applications(setup)
    gateway = ScriptedGateway([Turn(text="Nothing to look up.")])
    await ask_and_finish(chat, gateway, current_user=RUI_WITHOUT_PAYAU, request=question("And the runbooks?"))
    history = next(entry.section.content for entry in gateway.calls[0]["transcript"] if entry.section and entry.section.title == HISTORY_SECTION_TITLE)
    assert "How are the SLOs doing?" in history and "CLMJP and PAYAU both have SLOs" not in history

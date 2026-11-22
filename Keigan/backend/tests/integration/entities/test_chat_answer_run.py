"""keigan/entities/incident_entities.py ChatAnswerRun and ChatRunStep: what one Ask Keigan answer stores, and how it is removed (spec 23, section 6)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities import status_values as values
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from support.chat_answer_runs import store_answer_run


def test_the_run_and_step_value_sets_are_the_ones_the_spec_names() -> None:
    assert [member.value for member in values.ChatAnswerRunStatus] == ["running", "completed", "failed", "cancelled"]
    assert [member.value for member in values.ChatAnswerStopReason] == ["answered", "tool_limit_reached", "token_budget_reached", "cancelled_by_user", "failed"]
    assert [member.value for member in values.ChatRunStepKind] == ["model_turn", "tool_call"]
    assert [member.value for member in values.ChatRunStepStatus] == ["running", "succeeded", "failed", "refused", "skipped", "cancelled"]
    assert [member.value for member in values.ToolCallingMode] == ["native", "prompted_json", "scripted_mock"]


async def test_a_new_run_starts_with_empty_counters_and_nothing_cited(seed_context: object) -> None:
    async with open_session() as session:
        stored = await store_answer_run(session)
        run = await session.get(ChatAnswerRun, stored.answer_run_id)
        assert run is not None
        assert (run.total_input_token_count, run.total_output_token_count, run.model_turn_count, run.tool_call_count) == (0, 0, 0, 0)
        assert run.token_counts_estimated is False and run.is_unverified is False
        assert run.citations_json == [] and run.follow_up_questions_json == []
        assert run.started_at is not None and run.last_progress_at is not None
        assert run.stop_reason is None and run.completed_at is None and run.assistant_message_id is None


async def test_one_client_request_id_starts_only_one_run_per_conversation(seed_context: object) -> None:
    with pytest.raises(IntegrityError, match="client_request_id"):
        async with open_session() as session:
            first = await store_answer_run(session, client_request_id="request-7")
            await store_answer_run(session, conversation_id=first.conversation_id, client_request_id="request-7")


async def test_the_same_client_request_id_is_allowed_in_another_conversation(seed_context: object) -> None:
    async with open_session() as session:
        await store_answer_run(session, client_request_id="shared-request")
        await store_answer_run(session, client_request_id="shared-request")


async def test_two_steps_of_one_run_cannot_share_a_sequence_number(seed_context: object) -> None:
    with pytest.raises(IntegrityError, match="sequence_number"):
        async with open_session() as session:
            stored = await store_answer_run(session)
            session.add(ChatRunStep(answer_run_id=stored.answer_run_id, sequence_number=2, step_kind=values.ChatRunStepKind.MODEL_TURN, step_status=values.ChatRunStepStatus.RUNNING))
            await session.flush()


async def test_a_step_keeps_the_application_it_was_about_without_a_foreign_key(seed_context: object) -> None:
    async with open_session() as session:
        stored = await store_answer_run(session)
        call = ChatRunStep(
            answer_run_id=stored.answer_run_id, sequence_number=3, step_kind=values.ChatRunStepKind.TOOL_CALL, step_status=values.ChatRunStepStatus.SUCCEEDED,
            application_id="an-application-id-that-is-not-a-row",
        )
        session.add(call)
        await session.flush()
        assert call.application_id == "an-application-id-that-is-not-a-row"


async def test_a_message_that_a_run_points_to_cannot_be_deleted_before_the_run(seed_context: object) -> None:
    with pytest.raises(IntegrityError):
        async with open_session() as session:
            stored = await store_answer_run(session)
            message = await session.get(ConversationMessage, stored.user_message_id)
            await session.delete(message)
            await session.flush()


async def test_deleting_a_conversation_removes_its_runs_and_steps(seed_context: object) -> None:
    async with open_session() as session:
        stored = await store_answer_run(session)
        conversation = await session.get(Conversation, stored.conversation_id)
        await session.delete(conversation)
        await session.flush()
        assert await session.scalar(select(func.count()).select_from(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == stored.answer_run_id)) == 0
        assert await session.scalar(select(func.count()).select_from(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id)) == 0

"""keigan/services/ask_keigan_run_registry.py: the answers running in this process, one per conversation, removed when they end (spec 23, 7.5)."""

from __future__ import annotations

import asyncio

import pytest

from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_events import RunEventChannel
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry, ConversationBusyError, LiveAnswerRun


def live_run(run_id: str, conversation_id: str = "conversation-1") -> LiveAnswerRun:
    return LiveAnswerRun(answer_run_id=run_id, conversation_id=conversation_id, channel=RunEventChannel(run_id, maximum_queued_events=100), cancellation_flag=CancellationFlag())


def test_a_registered_run_is_found_by_its_id_until_it_is_released() -> None:
    registry = AnswerRunRegistry()
    run = live_run("run-1")
    registry.register(run)
    assert registry.get("run-1") is run
    registry.release("run-1")
    assert registry.get("run-1") is None


def test_a_conversation_holds_one_live_run_and_the_second_is_told_which() -> None:
    registry = AnswerRunRegistry()
    registry.register(live_run("run-1"))
    with pytest.raises(ConversationBusyError) as busy:
        registry.register(live_run("run-2"))
    assert busy.value.running_answer_run_id == "run-1"
    assert registry.get("run-2") is None


def test_another_conversation_can_run_at_the_same_time() -> None:
    registry = AnswerRunRegistry()
    registry.register(live_run("run-1", "conversation-1"))
    registry.register(live_run("run-2", "conversation-2"))
    assert {run.answer_run_id for run in registry.live_runs()} == {"run-1", "run-2"}


def test_registering_the_same_run_twice_is_refused_and_keeps_the_first() -> None:
    registry = AnswerRunRegistry()
    first = live_run("run-1")
    registry.register(first)
    with pytest.raises(ValueError, match="run-1"):
        registry.register(live_run("run-1", "conversation-2"))
    assert registry.get("run-1") is first


def test_releasing_twice_or_an_unknown_run_is_harmless() -> None:
    registry = AnswerRunRegistry()
    registry.register(live_run("run-1"))
    registry.release("run-1")
    registry.release("run-1")
    registry.release("never-registered")
    registry.register(live_run("run-3"))  # the conversation is free again


def test_a_stop_request_sets_the_flag_of_a_live_run_only() -> None:
    registry = AnswerRunRegistry()
    run = live_run("run-1")
    registry.register(run)
    assert registry.request_cancellation("run-1") is True
    assert run.cancellation_flag.is_requested
    assert registry.request_cancellation("run-elsewhere") is False


async def test_cancelling_everything_stops_the_tasks_and_names_the_runs_that_were_cut() -> None:
    registry = AnswerRunRegistry()
    never_finishes = asyncio.Event()
    run = live_run("run-1")
    run.task = asyncio.create_task(never_finishes.wait())
    registry.register(run)
    finished = live_run("run-2", "conversation-2")
    finished.task = asyncio.create_task(asyncio.sleep(0))
    registry.register(finished)
    await finished.task
    assert await registry.cancel_all(grace_seconds=5) == ["run-1"]
    assert run.task.cancelled()


async def test_a_run_whose_task_is_not_attached_yet_is_not_reported_as_cut() -> None:
    registry = AnswerRunRegistry()
    registry.register(live_run("run-1"))
    assert await registry.cancel_all(grace_seconds=1) == []

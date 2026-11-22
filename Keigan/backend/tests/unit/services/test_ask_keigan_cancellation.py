"""keigan/services/ask_keigan_cancellation.py: a stop request ends an answer between steps and inside a running step (spec 23, 7.5)."""

from __future__ import annotations

import asyncio

import pytest

from keigan.services.ask_keigan_cancellation import AnswerCancelledError, CancellationFlag, RunCancellationGuard


def guard_with(flag: CancellationFlag, database_says_stop: bool = False) -> RunCancellationGuard:
    async def stop_requested_in_database() -> bool:
        return database_says_stop

    return RunCancellationGuard(flag, stop_requested_in_database)


async def test_nothing_is_raised_when_nobody_asked_to_stop() -> None:
    await guard_with(CancellationFlag()).raise_if_requested()


async def test_the_in_process_flag_stops_the_answer() -> None:
    flag = CancellationFlag()
    flag.request()
    with pytest.raises(AnswerCancelledError):
        await guard_with(flag).raise_if_requested()


async def test_a_request_stored_by_another_pod_stops_the_answer() -> None:
    with pytest.raises(AnswerCancelledError):
        await guard_with(CancellationFlag(), database_says_stop=True).raise_if_requested()


async def test_a_step_that_finishes_before_any_stop_request_returns_its_result() -> None:
    async def step() -> str:
        return "done"

    assert await guard_with(CancellationFlag()).run(step()) == "done"


async def test_a_stop_request_during_a_step_cancels_the_step_and_ends_the_answer() -> None:
    flag, step_was_cancelled, step_started = CancellationFlag(), asyncio.Event(), asyncio.Event()

    async def slow_step() -> str:
        step_started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            step_was_cancelled.set()
            raise
        return "never"

    running = asyncio.create_task(guard_with(flag).run(slow_step()))
    await step_started.wait()
    flag.request()
    with pytest.raises(AnswerCancelledError):
        await asyncio.wait_for(running, timeout=1)
    assert step_was_cancelled.is_set()


async def test_a_stop_request_that_arrived_before_the_step_prevents_it_from_starting() -> None:
    flag, started = CancellationFlag(), False

    async def step() -> None:
        nonlocal started
        started = True

    flag.request()
    with pytest.raises(AnswerCancelledError):
        await guard_with(flag).run(step())
    assert started is False


async def test_a_failure_of_the_step_is_not_hidden_by_the_guard() -> None:
    async def failing_step() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await guard_with(CancellationFlag()).run(failing_step())


async def test_cancelling_the_whole_task_is_still_a_cancellation_of_the_task() -> None:
    async def slow_step() -> None:
        await asyncio.sleep(30)

    running = asyncio.create_task(guard_with(CancellationFlag()).run(slow_step()))
    await asyncio.sleep(0)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

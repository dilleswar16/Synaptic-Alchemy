"""keigan/services/ask_keigan_heartbeat.py: a live answer refreshes its progress on a timer while it works, and never after it ended (spec 23, 7.5; H1)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy.exc import OperationalError

from keigan.services.ask_keigan_heartbeat import RunHeartbeat

INTERVAL_SECONDS = 0.001  # only the number of beats matters, never how long they take: the tests wait for beats, not for time
WAIT_SECONDS = 5


class Beats:
    """A scripted ``beat``: counts calls, can run out (the run ended), can fail, and wakes a test when a call count is reached."""

    def __init__(self, *, still_running_for: int | None = None, failures: int = 0):
        self.calls = 0
        self._still_running_for = still_running_for
        self._failures = failures
        self._reached: dict[int, asyncio.Event] = {}

    async def __call__(self) -> bool:
        self.calls += 1
        if self.calls in self._reached:
            self._reached[self.calls].set()
        if self.calls <= self._failures:
            raise OperationalError("UPDATE", {}, Exception("database is locked"))
        return self._still_running_for is None or self.calls < self._still_running_for

    async def reached(self, call_count: int) -> None:
        event = self._reached.setdefault(call_count, asyncio.Event())
        if self.calls >= call_count:
            event.set()
        await asyncio.wait_for(event.wait(), WAIT_SECONDS)


async def test_it_beats_repeatedly_while_the_work_is_in_flight() -> None:
    beats = Beats()
    async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-1").running():
        await beats.reached(3)
    assert beats.calls >= 3


async def test_it_stops_beating_when_the_work_ends() -> None:
    beats = Beats()
    async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-1").running():
        await beats.reached(1)
    calls_at_the_end = beats.calls
    await asyncio.sleep(0)  # let a stray task run, if there were one
    await asyncio.sleep(0)
    assert beats.calls == calls_at_the_end


async def test_it_stops_when_the_work_raises_and_the_error_reaches_the_caller() -> None:
    beats = Beats()
    with pytest.raises(ValueError, match="model failed"):
        async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-1").running():
            await beats.reached(1)
            raise ValueError("model failed")
    calls_at_the_end = beats.calls
    await asyncio.sleep(0)
    assert beats.calls == calls_at_the_end


async def test_it_stops_for_good_when_the_run_is_no_longer_running(caplog: pytest.LogCaptureFixture) -> None:
    beats = Beats(still_running_for=2)  # the second beat finds the run ended by someone else
    with caplog.at_level(logging.INFO, logger="keigan.services.ask_keigan_heartbeat"):
        async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-1").running():
            await beats.reached(2)
            for _ in range(5):
                await asyncio.sleep(0)
    assert beats.calls == 2
    assert any("run-1" in record.getMessage() and record.levelno == logging.INFO for record in caplog.records)


async def test_a_failed_beat_is_logged_with_the_run_and_the_next_beat_still_happens(caplog: pytest.LogCaptureFixture) -> None:
    beats = Beats(failures=1)
    with caplog.at_level(logging.WARNING, logger="keigan.services.ask_keigan_heartbeat"):
        async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-9").running():
            await beats.reached(2)
    warning = next(record for record in caplog.records if record.levelno == logging.WARNING)
    assert "run-9" in warning.getMessage() and warning.exc_info is not None


async def test_an_unexpected_error_in_a_beat_is_logged_not_lost(caplog: pytest.LogCaptureFixture) -> None:
    async def broken_beat() -> bool:
        raise RuntimeError("not a database error")

    heartbeat = RunHeartbeat(broken_beat, INTERVAL_SECONDS, "run-7")
    with caplog.at_level(logging.ERROR, logger="keigan.services.ask_keigan_heartbeat"):
        async with heartbeat.running():
            for _ in range(50):
                await asyncio.sleep(0.001)
                if caplog.records:
                    break
    assert any("run-7" in record.getMessage() and record.exc_info is not None for record in caplog.records)


async def test_cancelling_the_task_that_holds_the_heartbeat_is_not_swallowed() -> None:
    beats = Beats()

    async def work() -> None:
        async with RunHeartbeat(beats, INTERVAL_SECONDS, "run-1").running():
            await asyncio.sleep(WAIT_SECONDS)

    task = asyncio.create_task(work())
    await beats.reached(1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

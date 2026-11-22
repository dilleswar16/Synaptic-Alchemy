"""keigan/services/ask_keigan_events.py: the in-process channel that carries one answer's events to the stream reader (spec 23, 7.3)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName, RunEventChannel

RUN_ID = "run-1"


async def collect(channel: RunEventChannel) -> list[AnswerEvent]:
    return [event async for event in channel.events()]


async def test_events_are_numbered_from_one_without_gaps_and_carry_the_envelope_of_the_protocol() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "Hello"})
    channel.publish(AnswerEventName.TURN_NOTE, {"turnNumber": 1, "runStepId": "s1", "text": "Checking"})
    channel.close()
    first, second = await collect(channel)
    assert (first.sequence, second.sequence) == (1, 2)
    assert first.name is AnswerEventName.ANSWER_TEXT
    assert first.data["eventVersion"] == 1 and first.data["sequence"] == 1 and first.data["answerRunId"] == RUN_ID
    assert first.data["turnNumber"] == 1 and first.data["text"] == "Hello"
    assert datetime.fromisoformat(str(first.data["emittedAt"])).tzinfo is not None
    assert channel.last_sequence == 2


async def test_a_reader_that_is_already_waiting_gets_the_next_event_and_the_end() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    reader = asyncio.create_task(collect(channel))
    await asyncio.sleep(0)
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "x"})
    await asyncio.sleep(0)
    assert not reader.done()
    channel.close()
    assert [event.sequence for event in await asyncio.wait_for(reader, timeout=1)] == [1]


async def test_the_final_events_are_the_completed_and_the_failed_one() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "x"})
    channel.publish(AnswerEventName.ANSWER_COMPLETED, {})
    channel.publish(AnswerEventName.ANSWER_FAILED, {})
    channel.close()
    assert [event.is_final for event in await collect(channel)] == [False, True, True]


async def test_nothing_is_accepted_after_the_channel_was_closed_and_closing_twice_is_harmless() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    channel.close()
    channel.close()
    assert channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "late"}) is False
    assert await collect(channel) == []
    assert channel.is_open is False and channel.was_dropped is False


async def test_a_reader_that_falls_behind_loses_the_stream_but_never_blocks_the_run() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=2)
    assert channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "a"}) is True
    assert channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "b"}) is True
    assert channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "c"}) is False  # full: the stream is dropped, the stored trace stays
    assert channel.was_dropped is True and channel.is_open is False
    assert channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "d"}) is False
    assert await asyncio.wait_for(collect(channel), timeout=1) == []  # the backlog is gone: the browser reads the snapshot instead of a stream with a hole


async def test_the_default_queue_size_comes_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "ask_keigan_event_queue_size", 100)
    channel = RunEventChannel(RUN_ID)
    accepted = [channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": str(number)}) for number in range(101)]
    assert accepted.count(True) == 100 and accepted[-1] is False

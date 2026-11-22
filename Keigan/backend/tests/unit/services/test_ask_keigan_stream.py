"""keigan/services/ask_keigan_stream.py: the events of one answer as server-sent frames, with keep-alive comments while the run is quiet (spec 23, 7.3 and 7.4)."""

from __future__ import annotations

import asyncio
import json

from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName, RunEventChannel
from keigan.services.ask_keigan_stream import KEEP_ALIVE_FRAME, event_frames, format_event_frame

RUN_ID = "run-1"


def test_a_frame_has_the_sequence_as_id_the_event_name_and_the_json_data() -> None:
    event = AnswerEvent(AnswerEventName.ANSWER_TEXT, 1, {"eventVersion": 1, "sequence": 1, "answerRunId": RUN_ID, "text": "Pool exhausted – 日本語"})
    frame = format_event_frame(event)
    assert frame.startswith("id: 1\nevent: answer.text\ndata: ") and frame.endswith("\n\n")
    data_line = frame.split("data: ", 1)[1].rstrip("\n")
    assert "\n" not in data_line
    assert json.loads(data_line)["text"] == "Pool exhausted – 日本語"
    assert json.loads(data_line)["sequence"] == 1


async def test_every_event_becomes_a_frame_in_order_and_the_stream_ends_when_the_channel_closes() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "One"})
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "Two"})
    channel.close()
    frames = [frame async for frame in event_frames(channel, heartbeat_seconds=5)]
    assert [frame.split("\n", 1)[0] for frame in frames] == ["id: 1", "id: 2"]


async def test_a_quiet_run_gets_keep_alive_comments_and_the_late_event_still_arrives() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    received: list[str] = []

    async def read() -> None:
        async for frame in event_frames(channel, heartbeat_seconds=0.05):
            received.append(frame)

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.2)
    channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": "Late"})
    channel.close()
    await asyncio.wait_for(reader, timeout=2)
    assert received.count(KEEP_ALIVE_FRAME) >= 2
    assert received[-1].startswith("id: 1\nevent: answer.text")
    assert KEEP_ALIVE_FRAME.startswith(":") and KEEP_ALIVE_FRAME.endswith("\n\n")


async def test_a_dropped_channel_ends_the_stream_without_a_final_event() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=100)
    for number in range(101):
        channel.publish(AnswerEventName.ANSWER_TEXT, {"turnNumber": 1, "text": str(number)})
    assert channel.was_dropped
    assert [frame async for frame in event_frames(channel, heartbeat_seconds=5)] == []


async def test_closing_the_stream_early_leaves_no_task_waiting_on_the_channel() -> None:
    channel = RunEventChannel(RUN_ID, maximum_queued_events=10)
    tasks_before = asyncio.all_tasks()
    frames = event_frames(channel, heartbeat_seconds=0.05)
    assert await anext(frames) == KEEP_ALIVE_FRAME
    await frames.aclose()
    await asyncio.sleep(0)
    assert asyncio.all_tasks() <= tasks_before | {asyncio.current_task()}

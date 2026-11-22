"""The events of one Ask Keigan answer and the in-process channel that carries them to the stream reader (spec 23, section 7.3, version 1).

One answer run publishes its events here as they happen; the stream endpoint (``AskKeiganService``) reads them and writes server-sent frames.
Publishing never waits: a reader that stops reading (a closed browser tab) must not stall the run, so a full queue drops the stream instead.
The browser then finds the finished answer in the stored trace.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import JsonValue

from keigan.config.settings import get_settings
from keigan.utils.time_utils import utc_now

EVENT_VERSION = 1


class AnswerEventName(StrEnum):
    ANSWER_STARTED = "answer.started"
    ANSWER_TEXT = "answer.text"
    TURN_NOTE = "turn.note"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_FINISHED = "tool.finished"
    ANSWER_COMPLETED = "answer.completed"
    ANSWER_FAILED = "answer.failed"


FINAL_EVENT_NAMES = frozenset({AnswerEventName.ANSWER_COMPLETED, AnswerEventName.ANSWER_FAILED})


@dataclass(frozen=True)
class AnswerEvent:
    """``data`` is the frame's JSON object: ``eventVersion``, ``sequence``, ``answerRunId``, ``emittedAt`` and the fields of the event (camelCase)."""

    name: AnswerEventName
    sequence: int
    data: Mapping[str, JsonValue]

    @property
    def is_final(self) -> bool:
        return self.name in FINAL_EVENT_NAMES


class _EndOfEvents:
    """Put on the queue by ``close`` so a waiting reader wakes up and stops."""


_END_OF_EVENTS = _EndOfEvents()


class RunEventChannel:
    def __init__(self, answer_run_id: str, maximum_queued_events: int | None = None):
        self.answer_run_id = answer_run_id
        self._maximum_queued_events = maximum_queued_events or get_settings().ask_keigan_event_queue_size
        self._queue: asyncio.Queue[AnswerEvent | _EndOfEvents] = asyncio.Queue(self._maximum_queued_events + 1)  # one slot is always free for the end marker
        self._last_sequence = 0
        self._is_open = True
        self._was_dropped = False

    @property
    def last_sequence(self) -> int:
        return self._last_sequence

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def was_dropped(self) -> bool:
        """True when the queue was full and the stream was cut: a reader must recover from the stored trace."""
        return self._was_dropped

    def publish(self, name: AnswerEventName, fields: Mapping[str, JsonValue]) -> bool:
        """Queue one event with the next sequence number. False (and nothing queued) when the channel is closed or the queue is full."""
        if not self._is_open:
            return False
        if self._queue.qsize() >= self._maximum_queued_events:
            self._drop_stream()
            return False
        sequence = self._last_sequence + 1
        envelope: dict[str, JsonValue] = {"eventVersion": EVENT_VERSION, "sequence": sequence, "answerRunId": self.answer_run_id, "emittedAt": utc_now().isoformat(), **fields}
        self._queue.put_nowait(AnswerEvent(name, sequence, envelope))
        self._last_sequence = sequence
        return True

    def close(self) -> None:
        """No more events will come; a reader receives what is queued and then stops."""
        if self._is_open:
            self._is_open = False
            self._queue.put_nowait(_END_OF_EVENTS)

    async def events(self) -> AsyncIterator[AnswerEvent]:
        while True:
            queued_item = await self._queue.get()
            if isinstance(queued_item, _EndOfEvents):
                return
            yield queued_item

    def _drop_stream(self) -> None:
        self._is_open = False
        self._was_dropped = True
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(_END_OF_EVENTS)

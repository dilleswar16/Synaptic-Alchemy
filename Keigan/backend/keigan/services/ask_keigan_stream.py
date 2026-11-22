"""The events of one Ask Keigan answer as server-sent frames (spec 23, 7.3 and 7.4).

A frame is ``id: <sequence>``, ``event: <name>`` and ``data: <json>``. While the run is quiet a ``: keep-alive`` comment goes out every heartbeat so proxies and
load balancers do not close an idle connection. The stream ends when the channel ends; a channel that dropped its stream (the reader was too slow) ends it
without a final event, and the browser then reads the finished answer from the stored trace.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress

from keigan.services.ask_keigan_events import AnswerEvent, RunEventChannel

KEEP_ALIVE_FRAME = ": keep-alive\n\n"

logger = logging.getLogger(__name__)


def format_event_frame(event: AnswerEvent) -> str:
    event_data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.sequence}\nevent: {event.name.value}\ndata: {event_data}\n\n"


async def event_frames(channel: RunEventChannel, heartbeat_seconds: float) -> AsyncIterator[str]:
    """One frame per event; a keep-alive comment whenever ``heartbeat_seconds`` pass without one. The run is never affected by the reader stopping."""
    events = channel.events()
    next_event: asyncio.Future[AnswerEvent] | None = None
    try:
        while True:
            if next_event is None:
                next_event = asyncio.ensure_future(anext(events))
            await asyncio.wait({next_event}, timeout=heartbeat_seconds)
            if not next_event.done():
                yield KEEP_ALIVE_FRAME
                continue
            finished_read, next_event = next_event, None
            if isinstance(finished_read.exception(), StopAsyncIteration):
                break
            yield format_event_frame(finished_read.result())
    finally:
        if next_event is not None:
            next_event.cancel()
            with suppress(asyncio.CancelledError):
                await next_event
        await events.aclose()
        if channel.was_dropped:
            logger.warning("The event stream of answer run %s was dropped because its reader was too slow; the browser recovers the answer from the stored trace.", channel.answer_run_id)

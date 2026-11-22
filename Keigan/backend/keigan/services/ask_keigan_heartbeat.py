"""The progress heartbeat of a live Ask Keigan answer (spec 23, 7.5).

A model turn or a tool call can legitimately say nothing to the database for minutes (provider timeouts and retries add up), so ``last_progress_at`` cannot depend on
the engine writing a step. While the answer is in flight this timer refreshes it every ``ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS``. The longest silence of a live
run is therefore one beat, whatever the model and tool time-outs are, and the settings validator keeps ``ASK_KEIGAN_STALE_RUN_SECONDS`` several beats longer.
A process that died stops beating, which is exactly what the stale limit detects.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class RunHeartbeat:
    def __init__(self, beat: Callable[[], Awaitable[bool]], interval_seconds: float, answer_run_id: str):
        """``beat`` refreshes the run's progress and returns False when the run is no longer running (someone else ended it): there is nothing left to refresh."""
        self._beat = beat
        self._interval_seconds = interval_seconds
        self._answer_run_id = answer_run_id

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """Beat for as long as the ``async with`` body runs; the beating task is gone when it ends, however it ends."""
        beating_task = asyncio.create_task(self._beat_until_the_run_ends())
        beating_task.add_done_callback(self._log_unexpected_end)
        try:
            yield
        finally:
            beating_task.cancel()
            await asyncio.wait({beating_task})  # not ``await beating_task``: this must not swallow a cancellation of the caller

    def _log_unexpected_end(self, beating_task: asyncio.Task[None]) -> None:
        if not beating_task.cancelled() and beating_task.exception() is not None:
            logger.error("The heartbeat of answer run %s stopped with an unexpected error.", self._answer_run_id, exc_info=beating_task.exception())

    async def _beat_until_the_run_ends(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                if not await self._beat():
                    logger.info("Answer run %s is no longer running; its heartbeat stopped.", self._answer_run_id)
                    return
            except SQLAlchemyError:
                logger.warning("The heartbeat of answer run %s could not be stored; it will try again.", self._answer_run_id, exc_info=True)

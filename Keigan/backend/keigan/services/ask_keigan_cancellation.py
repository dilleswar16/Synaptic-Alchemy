"""Stopping an answer (spec 23, 7.5): an in-process flag, a stop request stored in the run row for another pod, and a way to end a running step at once.

The flag is owned by the run registry of this pod and set by the cancel endpoint; the stored request (``cancel_requested_at``) reaches runs that live
in another pod. The engine checks both between steps and races every model turn and tool call against the flag, so Stop does not wait for a long call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from typing import Any, TypeVar

StepResult = TypeVar("StepResult")


class AnswerCancelledError(Exception):
    """The person stopped the answer."""


class CancellationFlag:
    def __init__(self) -> None:
        self._requested = asyncio.Event()

    @property
    def is_requested(self) -> bool:
        return self._requested.is_set()

    def request(self) -> None:
        self._requested.set()

    async def wait_until_requested(self) -> None:
        await self._requested.wait()


class RunCancellationGuard:
    def __init__(self, flag: CancellationFlag, stop_requested_in_database: Callable[[], Awaitable[bool]]):
        self._flag = flag
        self._stop_requested_in_database = stop_requested_in_database

    async def raise_if_requested(self) -> None:
        """Between steps: the flag first (free), then the run row."""
        if self._flag.is_requested or await self._stop_requested_in_database():
            raise AnswerCancelledError

    async def run(self, step: Coroutine[Any, Any, StepResult]) -> StepResult:
        """The result of ``step``, or ``AnswerCancelledError`` (after cancelling ``step``) when the flag is set before it finishes."""
        if self._flag.is_requested:
            step.close()
            raise AnswerCancelledError
        step_task = asyncio.ensure_future(step)
        flag_task = asyncio.ensure_future(self._flag.wait_until_requested())
        try:
            finished_tasks, _ = await asyncio.wait({step_task, flag_task}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:  # the whole answer task was cancelled: take the step down with it
            step_task.cancel()
            raise
        finally:
            flag_task.cancel()
        if step_task not in finished_tasks:
            step_task.cancel()
            with suppress(asyncio.CancelledError):
                await step_task
            raise AnswerCancelledError
        return step_task.result()

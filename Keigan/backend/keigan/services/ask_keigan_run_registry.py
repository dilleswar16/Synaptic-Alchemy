"""The Ask Keigan answers running in this process (spec 23, 7.5).

An answer is a detached task: it outlives the HTTP request that started it. The registry is what lets another request find it (to read its events or to
stop it), keeps one running answer per conversation, and lets a shutting-down process cut its tasks cleanly. It knows only this process: an answer running in
another pod is found through its stored run row (``cancel_requested_at``, ``last_progress_at``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_engine import AnswerOutcome
from keigan.services.ask_keigan_events import RunEventChannel


class ConversationBusyError(Exception):
    """The conversation already has a live answer; ``running_answer_run_id`` is its run."""

    def __init__(self, running_answer_run_id: str):
        super().__init__(f"Answer run {running_answer_run_id} is still running in this conversation.")
        self.running_answer_run_id = running_answer_run_id


@dataclass
class LiveAnswerRun:
    answer_run_id: str
    conversation_id: str
    channel: RunEventChannel
    cancellation_flag: CancellationFlag
    task: asyncio.Task[AnswerOutcome] | None = None  # set right after the task is created; a run is registered before its first write


class AnswerRunRegistry:
    def __init__(self) -> None:
        self._runs_by_id: dict[str, LiveAnswerRun] = {}

    def register(self, live_run: LiveAnswerRun) -> None:
        """Raises ``ValueError`` for a run id that is registered already and ``ConversationBusyError`` when the conversation has another live run."""
        if live_run.answer_run_id in self._runs_by_id:
            raise ValueError(f"Answer run {live_run.answer_run_id} is already registered.")
        busy_with = next((run for run in self._runs_by_id.values() if run.conversation_id == live_run.conversation_id), None)
        if busy_with is not None:
            raise ConversationBusyError(busy_with.answer_run_id)
        self._runs_by_id[live_run.answer_run_id] = live_run

    def get(self, answer_run_id: str) -> LiveAnswerRun | None:
        return self._runs_by_id.get(answer_run_id)

    def release(self, answer_run_id: str) -> None:
        """Forget a run that ended. Safe to call more than once."""
        self._runs_by_id.pop(answer_run_id, None)

    def live_runs(self) -> list[LiveAnswerRun]:
        return list(self._runs_by_id.values())

    def request_cancellation(self, answer_run_id: str) -> bool:
        """Set the stop flag of a run that lives in this process. False when it does not (it may live in another pod)."""
        live_run = self._runs_by_id.get(answer_run_id)
        if live_run is None:
            return False
        live_run.cancellation_flag.request()
        return True

    async def cancel_all(self, grace_seconds: float) -> list[str]:
        """Cancel every unfinished task and wait up to ``grace_seconds`` for them to end. Returns the ids of the runs that were cut short (their rows still say ``running``)."""
        unfinished_tasks = {run.answer_run_id: run.task for run in self._runs_by_id.values() if run.task is not None and not run.task.done()}
        for task in unfinished_tasks.values():
            task.cancel()
        if unfinished_tasks:
            await asyncio.wait(unfinished_tasks.values(), timeout=grace_seconds)
        return list(unfinished_tasks)

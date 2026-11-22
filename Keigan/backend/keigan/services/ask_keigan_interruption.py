"""Ends Ask Keigan answer runs whose engine is gone (spec 23, 7.5 and 4.10 ``answer_interrupted``).

Two things leave a run row ``running`` with nothing working on it: a pod that restarted, and a pod that is shutting down (its tasks are cancelled, which the
engine does not treat as a failure of the answer). Both end the run the same way: ``failed`` with the catalogue code ``answer_interrupted``, running steps
``cancelled`` and the question linked to the run, so the screen shows what was finished and offers to ask again. A run counts as interrupted by silence:
``last_progress_at`` older than ``ASK_KEIGAN_STALE_RUN_SECONDS`` and no live task in this process. A live run beats every ``ASK_KEIGAN_PROGRESS_HEARTBEAT_SECONDS``,
so silence means a dead process, not a slow model. Ending a run is a conditional write at the moment of ending (never decided from an earlier read): a run that
ended by itself, or beat once more, in the meantime is left as it is.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import ChatAnswerRun
from keigan.entities.status_values import ChatAnswerRunStatus
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry
from keigan.services.ask_keigan_trace import TraceRecorder
from keigan.utils.time_utils import ensure_utc, utc_now

INTERRUPTED_ERROR_CODE = "answer_interrupted"

logger = logging.getLogger(__name__)


class RunInterruption:
    def __init__(self, registry: AnswerRunRegistry):
        self.registry = registry

    def is_stale(self, run: ChatAnswerRun) -> bool:
        """Running, silent for longer than the stale limit, and not being worked on by this process."""
        if run.run_status != ChatAnswerRunStatus.RUNNING or self.registry.get(run.answer_run_id) is not None:
            return False
        silence = utc_now() - (ensure_utc(run.last_progress_at) or utc_now())
        return silence > timedelta(seconds=get_settings().ask_keigan_stale_run_seconds)

    async def interrupt_if_stale(self, run: ChatAnswerRun) -> bool:
        """End ``run`` as interrupted when it is stale. True when it was ended (the caller must reload the row)."""
        return self.is_stale(run) and await self.interrupt(run.answer_run_id, only_if_silent=True)

    async def interrupt(self, answer_run_id: str, *, only_if_silent: bool = False) -> bool:
        """End a run that is still ``running`` as interrupted. False when this call did not end it: it ended by itself in the meantime, or (``only_if_silent``) it beat again
        since it was judged stale. ``only_if_silent`` is for a run another process may still be working on; a run this process just cut off is ended without that check."""
        async with open_session() as session:
            run = await session.get(ChatAnswerRun, answer_run_id)
            if run is None or run.run_status != ChatAnswerRunStatus.RUNNING:
                return False
            started_at, correlation_id = run.started_at, run.correlation_id
        silent_since = utc_now() - timedelta(seconds=get_settings().ask_keigan_stale_run_seconds) if only_if_silent else None
        failure = AskKeiganErrorCatalogue.describe(INTERRUPTED_ERROR_CODE, {"reference": correlation_id})
        was_ended_here = await TraceRecorder.for_interrupted_run(answer_run_id, started_at).interrupt_run(failure, only_if_silent_since=silent_since)
        if was_ended_here:
            logger.warning("Answer run %s was marked interrupted: nothing was working on it.", answer_run_id)
        else:
            logger.info("Answer run %s was not marked interrupted: it ended or made progress while this was decided.", answer_run_id)
        return was_ended_here

    async def interrupt_live_runs(self) -> list[str]:
        """Shutdown: cancel the answer tasks of this process, then end their runs as interrupted. Returns the ids of the runs that were cut short."""
        cut_run_ids = await self.registry.cancel_all(get_settings().ask_keigan_shutdown_grace_seconds)
        for answer_run_id in cut_run_ids:
            try:
                await self.interrupt(answer_run_id)
            except Exception:  # noqa: BLE001 — shutdown must go on with the other runs and the workers; the run is ended as stale when it is next read
                logger.exception("Answer run %s could not be marked interrupted while shutting down.", answer_run_id)
        return cut_run_ids

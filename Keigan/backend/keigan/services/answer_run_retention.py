"""Removal of stored Ask Keigan answer runs and their steps.

A run points at its question and answer messages with NO ACTION foreign keys (SQL Server allows one cascade path per table), so everything that deletes
conversation messages deletes the runs first, steps before runs. Nothing expires by default: :func:`purge_expired_answer_runs` only runs when
ASK_KEIGAN_TRACE_RETENTION_DAYS is set, removes the traces of global conversations, and leaves the conversations and their messages in place.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep
from keigan.entities.status_values import ConversationScope

logger = logging.getLogger(__name__)


class AnswerRunsRemoved(NamedTuple):
    runs: int
    steps: int


async def delete_answer_runs(session: AsyncSession, run_condition: ColumnElement[bool]) -> AnswerRunsRemoved:
    """Delete the runs that match ``run_condition`` (a condition on :class:`ChatAnswerRun`) with their steps. The caller commits."""
    matching_run_ids = select(ChatAnswerRun.answer_run_id).where(run_condition)
    removed_steps = (await session.execute(delete(ChatRunStep).where(ChatRunStep.answer_run_id.in_(matching_run_ids)))).rowcount or 0
    removed_runs = (await session.execute(delete(ChatAnswerRun).where(run_condition))).rowcount or 0
    return AnswerRunsRemoved(runs=removed_runs, steps=removed_steps)


async def purge_expired_answer_runs(session: AsyncSession, cutoff: datetime, batch_size: int) -> dict[str, int]:
    """Remove runs of global conversations that started before ``cutoff``, in batches of ``batch_size`` that each commit. Returns row counts per kind."""
    removed = {"chatAnswerRuns": 0, "chatRunSteps": 0}
    expired_run_ids = (
        select(ChatAnswerRun.answer_run_id)
        .where(ChatAnswerRun.started_at < cutoff, ChatAnswerRun.conversation_scope == ConversationScope.KEIGAN_AI_CHAT)
        .order_by(ChatAnswerRun.started_at)
        .limit(batch_size)
    )
    while run_ids := list((await session.scalars(expired_run_ids)).all()):
        batch_removed = await delete_answer_runs(session, ChatAnswerRun.answer_run_id.in_(run_ids))
        removed["chatAnswerRuns"] += batch_removed.runs
        removed["chatRunSteps"] += batch_removed.steps
        await session.commit()
    logger.info("Answer run retention removed %s", removed)
    return removed

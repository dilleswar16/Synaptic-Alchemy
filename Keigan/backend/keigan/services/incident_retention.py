"""Retention of incidents and investigations: removes expired ones together with everything that hangs off them.

Deletes run in batches and commit after each batch, so a large backlog never holds one long transaction (lock escalation on SQL Server,
transaction log growth). Children are deleted before parents, in an order that is valid with or without ON DELETE CASCADE: the
``investigation.incident_id`` foreign key is NO ACTION on SQL Server, and several tables link to incidents only by a plain id column.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.alert_entities import AlertGroup
from keigan.entities.incident_entities import (
    ChatAnswerRun, Conversation, ConversationMessage, Incident, IncidentCommunication, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, PostmortemReport,
)
from keigan.entities.notification_entities import NotificationDelivery, TeamsIncidentChat
from keigan.entities.status_values import IncidentStatus, InvestigationStatus
from keigan.services.answer_run_retention import delete_answer_runs

logger = logging.getLogger(__name__)

FINISHED_INCIDENT_STATUSES = (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
ACTIVE_INVESTIGATION_STATUSES = (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)


def _expired_incident_ids(cutoff: datetime, batch_size: int) -> Any:
    """Finished incidents opened before the cutoff, unless one of their investigations is still queued or running."""
    has_active_investigation = select(Investigation.incident_id).where(Investigation.incident_id.is_not(None), Investigation.investigation_status.in_(ACTIVE_INVESTIGATION_STATUSES))
    return (
        select(Incident.incident_id)
        .where(Incident.incident_status.in_(FINISHED_INCIDENT_STATUSES), Incident.opened_at < cutoff, Incident.incident_id.not_in(has_active_investigation))
        .order_by(Incident.opened_at)
        .limit(batch_size)
    )


def _expired_standalone_investigation_ids(cutoff: datetime, batch_size: int) -> Any:
    """Finished investigations that belong to no incident (started from an alert group or by hand) and are older than the cutoff."""
    return (
        select(Investigation.investigation_id)
        .where(Investigation.incident_id.is_(None), Investigation.created_at < cutoff, Investigation.investigation_status.not_in(ACTIVE_INVESTIGATION_STATUSES))
        .order_by(Investigation.created_at)
        .limit(batch_size)
    )


async def _count_deleted(session: AsyncSession, statement: Any) -> int:
    return (await session.execute(statement)).rowcount or 0


async def _delete_answer_runs(session: AsyncSession, run_condition: ColumnElement[bool], removed: dict[str, int]) -> None:
    """Answer runs point at conversation messages with NO ACTION keys, so they go before the messages."""
    answer_runs_removed = await delete_answer_runs(session, run_condition)
    removed["chatAnswerRuns"] += answer_runs_removed.runs
    removed["chatRunSteps"] += answer_runs_removed.steps


async def _delete_investigations(session: AsyncSession, investigation_ids: list[str], removed: dict[str, int]) -> None:
    """Delete investigations and everything keyed by them. The caller deletes the owning incident afterwards."""
    conversation_ids = select(Conversation.conversation_id).where(Conversation.investigation_id.in_(investigation_ids))
    await _delete_answer_runs(session, or_(ChatAnswerRun.conversation_id.in_(conversation_ids), ChatAnswerRun.investigation_id.in_(investigation_ids)), removed)
    removed["conversationMessages"] += await _count_deleted(session, delete(ConversationMessage).where(ConversationMessage.conversation_id.in_(conversation_ids)))
    removed["conversations"] += await _count_deleted(session, delete(Conversation).where(Conversation.investigation_id.in_(investigation_ids)))
    removed["investigationTimelineEvents"] += await _count_deleted(session, delete(InvestigationTimelineEvent).where(InvestigationTimelineEvent.investigation_id.in_(investigation_ids)))
    removed["incidentCommunications"] += await _count_deleted(session, delete(IncidentCommunication).where(IncidentCommunication.investigation_id.in_(investigation_ids)))
    removed["postmortems"] += await _count_deleted(session, delete(PostmortemReport).where(PostmortemReport.investigation_id.in_(investigation_ids)))
    removed["notificationDeliveries"] += await _count_deleted(session, delete(NotificationDelivery).where(NotificationDelivery.investigation_id.in_(investigation_ids)))
    removed["hypotheses"] += await _count_deleted(session, delete(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id.in_(investigation_ids)))
    removed["evidence"] += await _count_deleted(session, delete(InvestigationEvidence).where(InvestigationEvidence.investigation_id.in_(investigation_ids)))
    await session.execute(update(AlertGroup).where(AlertGroup.investigation_id.in_(investigation_ids)).values(investigation_id=None))
    removed["investigations"] += await _count_deleted(session, delete(Investigation).where(Investigation.investigation_id.in_(investigation_ids)))


async def _delete_incident_batch(session: AsyncSession, incident_ids: list[str], removed: dict[str, int]) -> None:
    investigation_ids = list((await session.scalars(select(Investigation.investigation_id).where(Investigation.incident_id.in_(incident_ids)))).all())
    if investigation_ids:
        await _delete_investigations(session, investigation_ids, removed)
    conversation_ids = select(Conversation.conversation_id).where(Conversation.incident_id.in_(incident_ids))
    await _delete_answer_runs(session, ChatAnswerRun.conversation_id.in_(conversation_ids), removed)
    removed["conversationMessages"] += await _count_deleted(session, delete(ConversationMessage).where(ConversationMessage.conversation_id.in_(conversation_ids)))
    removed["conversations"] += await _count_deleted(session, delete(Conversation).where(Conversation.incident_id.in_(incident_ids)))
    removed["investigationTimelineEvents"] += await _count_deleted(session, delete(InvestigationTimelineEvent).where(InvestigationTimelineEvent.incident_id.in_(incident_ids)))
    removed["incidentCommunications"] += await _count_deleted(session, delete(IncidentCommunication).where(IncidentCommunication.incident_id.in_(incident_ids)))
    removed["notificationDeliveries"] += await _count_deleted(session, delete(NotificationDelivery).where(NotificationDelivery.incident_id.in_(incident_ids)))
    removed["postmortems"] += await _count_deleted(session, delete(PostmortemReport).where(PostmortemReport.incident_id.in_(incident_ids)))
    removed["teamsIncidentChats"] += await _count_deleted(session, delete(TeamsIncidentChat).where(TeamsIncidentChat.incident_id.in_(incident_ids)))
    await session.execute(update(AlertGroup).where(AlertGroup.incident_id.in_(incident_ids)).values(incident_id=None))
    removed["incidents"] += await _count_deleted(session, delete(Incident).where(Incident.incident_id.in_(incident_ids)))


async def purge_expired_incidents(session: AsyncSession, cutoff: datetime, batch_size: int) -> dict[str, int]:
    """Remove expired incidents and standalone investigations in batches of ``batch_size``, committing after each batch. Returns row counts per kind."""
    removed = dict.fromkeys(
        ("incidents", "investigations", "hypotheses", "evidence", "investigationTimelineEvents", "incidentCommunications", "postmortems", "conversations", "conversationMessages",
         "notificationDeliveries", "teamsIncidentChats", "chatAnswerRuns", "chatRunSteps"), 0,
    )
    while incident_ids := list((await session.scalars(_expired_incident_ids(cutoff, batch_size))).all()):
        await _delete_incident_batch(session, incident_ids, removed)
        await session.commit()
    while investigation_ids := list((await session.scalars(_expired_standalone_investigation_ids(cutoff, batch_size))).all()):
        await _delete_investigations(session, investigation_ids, removed)
        await session.commit()
    logger.info("Incident retention removed %s", removed)
    return removed

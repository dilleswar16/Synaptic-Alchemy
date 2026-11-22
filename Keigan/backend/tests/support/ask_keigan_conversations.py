"""An investigation with evidence and a timeline, and the investigation chat of a reader of its application: the starting point of every Ask Keigan service and HTTP test."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.dtos.chat_dtos import ConversationCreateRequest
from keigan.entities.incident_entities import ChatAnswerRun, Incident, Investigation, InvestigationEvidence, InvestigationTimelineEvent
from keigan.entities.status_values import ChatAnswerRunStatus
from keigan.security.current_user import CurrentUser
from keigan.services.chat_service import ChatService

FIRST_EVENT_AT = datetime(2026, 1, 5, 9, 0)
_incident_counter = itertools.count(100)


@dataclass(frozen=True)
class SeededInvestigation:
    investigation_id: str
    application_id: str


async def seed_investigation(application_id: str) -> SeededInvestigation:
    """A fresh incident and investigation on ``application_id`` with evidence E1 and E2 and two timeline events (the second is the release that preceded E2)."""
    async with open_session() as session:
        incident = Incident(application_id=application_id, external_incident_number=f"INC{next(_incident_counter):07d}", incident_title="Claims API errors")
        session.add(incident)
        await session.flush()
        investigation = Investigation(application_id=application_id, incident_id=incident.incident_id, executive_summary="Pool exhaustion on claims-api.")
        session.add(investigation)
        await session.flush()
        session.add_all([
            InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log_analytics", evidence_category="error_pattern", evidence_title="Error spike on claims-api",
                evidence_summary="Errors rose from 2 to 312 per minute.", matched_record_count=312, signal_strength="high",
            ),
            InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code="E2", evidence_source_kind="azure_activity_log", evidence_category="change_event", evidence_title="Release 41 deployed",
                evidence_summary="Release 41 was deployed ten minutes before the spike.", matched_record_count=1, signal_strength="medium",
            ),
            InvestigationTimelineEvent(investigation_id=investigation.investigation_id, event_occurred_at=FIRST_EVENT_AT, event_type="alert_fired", event_title="Error rate alert fired", event_source="keigan"),
            InvestigationTimelineEvent(
                investigation_id=investigation.investigation_id, event_occurred_at=FIRST_EVENT_AT + timedelta(minutes=10), event_type="deployment", event_title="Release 41 deployed",
                event_source="azure_activity_log",
            ),
        ])
        return SeededInvestigation(investigation.investigation_id, application_id)


async def open_investigation_chat(current_user: CurrentUser, investigation_id: str) -> str:
    """The id of the investigation chat of ``current_user`` (created on first use, as the investigation page does)."""
    async with open_session() as session:
        conversation = await ChatService(session).create_conversation(current_user, ConversationCreateRequest(conversation_scope="investigation", investigation_id=investigation_id))
        return conversation.conversation_id


async def open_global_chat(current_user: CurrentUser, application_ids: tuple[str, ...] = ()) -> str:
    """The id of a new Keigan AI chat conversation of ``current_user`` (the page creates one per conversation), scoped to ``application_ids`` or, when empty, to every application they read."""
    async with open_session() as session:
        conversation = await ChatService(session).create_conversation(current_user, ConversationCreateRequest(conversation_scope="keigan_ai_chat", application_ids=list(application_ids)))
        return conversation.conversation_id


async def stored_run(answer_run_id: str) -> ChatAnswerRun:
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, answer_run_id)
        assert run is not None
        return run


async def runs_of(conversation_id: str) -> list[ChatAnswerRun]:
    async with open_session() as session:
        return list((await session.scalars(select(ChatAnswerRun).where(ChatAnswerRun.conversation_id == conversation_id).order_by(ChatAnswerRun.started_at))).all())


async def running_runs_of(conversation_id: str) -> list[ChatAnswerRun]:
    return [run for run in await runs_of(conversation_id) if run.run_status == ChatAnswerRunStatus.RUNNING]

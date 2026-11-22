"""keigan/services/incident_retention.py and AdministrationService.run_retention_cleanup: expired incidents and investigations are removed (H10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import AlertGroup
from keigan.entities.incident_entities import (
    ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage, Incident, IncidentCommunication, Investigation, InvestigationCoverageGap, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, InvestigationTraceStep, PostmortemReport,
)
from keigan.config.settings import get_settings
from keigan.entities.notification_entities import NotificationDelivery, TeamsIncidentChat
from keigan.entities.status_values import ConversationScope
from keigan.services.administration_service import AdministrationService
from keigan.services.incident_retention import purge_expired_incidents
from support.chat_answer_runs import StoredAnswerRun, store_answer_run

LONG_AGO = datetime.now(UTC) - timedelta(days=500)
RECENT = datetime.now(UTC) - timedelta(days=5)
CUTOFF = datetime.now(UTC) - timedelta(days=395)


@dataclass
class IncidentTree:
    incident_id: str
    investigation_id: str
    alert_group_id: str


async def _create_incident_tree(application_id: str, *, opened_at: datetime, incident_status: str, investigation_status: str = "completed") -> IncidentTree:
    """An incident with everything that hangs off it: investigation, hypothesis, evidence, timeline, communication, postmortem, chat, notification, alert group."""
    async with open_session() as session:
        incident = Incident(application_id=application_id, incident_title="Retention test incident", incident_status=incident_status, opened_at=opened_at)
        session.add(incident)
        await session.flush()
        investigation = Investigation(application_id=application_id, incident_id=incident.incident_id, investigation_status=investigation_status, created_at=opened_at)
        session.add(investigation)
        await session.flush()
        conversation = Conversation(conversation_scope="investigation", investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        alert_group = AlertGroup(application_id=application_id, group_title="Retention group", group_status="resolved", investigation_id=investigation.investigation_id, incident_id=incident.incident_id)
        session.add_all([conversation, alert_group])
        await session.flush()
        session.add_all([
            InvestigationHypothesis(investigation_id=investigation.investigation_id, analysis_perspective="application", hypothesis_title="h"),
            InvestigationEvidence(investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log", evidence_category="errors", evidence_title="e"),
            InvestigationCoverageGap(investigation_id=investigation.investigation_id, gap_kind="service_without_telemetry", service_name="mainframe"),
            InvestigationTraceStep(investigation_id=investigation.investigation_id, sequence_number=1, stage_name="triage", step_kind="inputs", step_status="succeeded"),
            InvestigationTimelineEvent(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, event_type="note", event_title="t"),
            IncidentCommunication(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, communication_type="update", subject_line="s", body_markdown="b"),
            PostmortemReport(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, report_title="p"),
            ConversationMessage(conversation_id=conversation.conversation_id, author_role="user", message_text="hello"),
            NotificationDelivery(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, notification_type="incident", delivery_channel="email", recipient_address="a@example.com"),
            TeamsIncidentChat(incident_id=incident.incident_id, application_id=application_id, teams_chat_identifier="chat", chat_topic="topic"),
        ])
        return IncidentTree(incident.incident_id, investigation.investigation_id, alert_group.alert_group_id)


async def _count_rows_of_tree(tree: IncidentTree) -> dict[str, int]:
    checks = {
        "incident": (Incident, Incident.incident_id == tree.incident_id),
        "investigation": (Investigation, Investigation.investigation_id == tree.investigation_id),
        "hypothesis": (InvestigationHypothesis, InvestigationHypothesis.investigation_id == tree.investigation_id),
        "evidence": (InvestigationEvidence, InvestigationEvidence.investigation_id == tree.investigation_id),
        "coverage_gap": (InvestigationCoverageGap, InvestigationCoverageGap.investigation_id == tree.investigation_id),
        "trace_step": (InvestigationTraceStep, InvestigationTraceStep.investigation_id == tree.investigation_id),
        "timeline": (InvestigationTimelineEvent, InvestigationTimelineEvent.incident_id == tree.incident_id),
        "communication": (IncidentCommunication, IncidentCommunication.incident_id == tree.incident_id),
        "postmortem": (PostmortemReport, PostmortemReport.incident_id == tree.incident_id),
        "conversation": (Conversation, Conversation.incident_id == tree.incident_id),
        "message": (ConversationMessage, ConversationMessage.conversation_id.in_(select(Conversation.conversation_id).where(Conversation.incident_id == tree.incident_id))),
        "notification": (NotificationDelivery, NotificationDelivery.incident_id == tree.incident_id),
        "chat": (TeamsIncidentChat, TeamsIncidentChat.incident_id == tree.incident_id),
    }
    async with open_session() as session:
        return {name: await session.scalar(select(func.count()).select_from(model).where(condition)) or 0 for name, (model, condition) in checks.items()}


async def test_expired_resolved_incident_is_removed_with_everything_attached_to_it(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="resolved")
    async with open_session() as session:
        removed = await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert removed["incidents"] >= 1
    assert set((await _count_rows_of_tree(tree)).values()) == {0}


async def test_alert_group_that_pointed_at_a_removed_incident_loses_the_dangling_links(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="closed")
    async with open_session() as session:
        await purge_expired_incidents(session, CUTOFF, batch_size=500)
    async with open_session() as session:
        group = await session.get(AlertGroup, tree.alert_group_id)
    assert group is not None and group.investigation_id is None and group.incident_id is None


async def test_recent_incident_is_kept_with_all_its_rows(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=RECENT, incident_status="resolved")
    async with open_session() as session:
        await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert set((await _count_rows_of_tree(tree)).values()) == {1}


async def test_old_incident_that_is_still_open_is_kept(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="investigating")
    async with open_session() as session:
        await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert set((await _count_rows_of_tree(tree)).values()) == {1}


async def test_resolved_incident_with_a_running_investigation_is_kept(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="resolved", investigation_status="running")
    async with open_session() as session:
        await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert set((await _count_rows_of_tree(tree)).values()) == {1}


async def test_standalone_expired_investigation_from_an_alert_group_is_removed(seed_context) -> None:
    async with open_session() as session:
        investigation = Investigation(application_id=seed_context.application_ids_by_code["CLMJP"], investigation_trigger="alert_group", investigation_status="completed", created_at=LONG_AGO)
        session.add(investigation)
        await session.flush()
        session.add(InvestigationHypothesis(investigation_id=investigation.investigation_id, analysis_perspective="application", hypothesis_title="h"))
        investigation_id = investigation.investigation_id
    async with open_session() as session:
        removed = await purge_expired_incidents(session, CUTOFF, batch_size=500)
    async with open_session() as session:
        assert await session.get(Investigation, investigation_id) is None
        assert await session.scalar(select(func.count()).select_from(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation_id)) == 0
    assert removed["investigations"] >= 1


async def test_cleanup_works_in_batches_smaller_than_the_number_of_expired_incidents(seed_context) -> None:
    trees = [await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="resolved") for _ in range(5)]
    async with open_session() as session:
        removed = await purge_expired_incidents(session, CUTOFF, batch_size=2)
    assert removed["incidents"] >= 5
    for tree in trees:
        assert set((await _count_rows_of_tree(tree)).values()) == {0}


async def test_retention_cleanup_job_removes_expired_incidents(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="resolved")
    async with open_session() as session:
        removed = await AdministrationService(session).run_retention_cleanup()
    assert removed is not None and removed["incidents"] >= 1
    assert (await _count_rows_of_tree(tree))["incident"] == 0


async def _count_answer_runs_and_steps(stored: StoredAnswerRun) -> tuple[int, int]:
    async with open_session() as session:
        runs = await session.scalar(select(func.count()).select_from(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == stored.answer_run_id))
        steps = await session.scalar(select(func.count()).select_from(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id))
    return runs or 0, steps or 0


async def test_expired_incident_is_removed_together_with_the_answer_runs_of_its_investigation_chat(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=LONG_AGO, incident_status="resolved")
    async with open_session() as session:
        conversation_id = await session.scalar(select(Conversation.conversation_id).where(Conversation.incident_id == tree.incident_id))
        stored = await store_answer_run(session, conversation_id=conversation_id, conversation_scope=ConversationScope.INVESTIGATION, investigation_id=tree.investigation_id)
    async with open_session() as session:
        removed = await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert await _count_answer_runs_and_steps(stored) == (0, 0)
    assert removed["chatAnswerRuns"] >= 1 and removed["chatRunSteps"] >= 2


async def test_a_recent_incident_keeps_the_answer_runs_of_its_chat(seed_context) -> None:
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=RECENT, incident_status="resolved")
    async with open_session() as session:
        conversation_id = await session.scalar(select(Conversation.conversation_id).where(Conversation.incident_id == tree.incident_id))
        stored = await store_answer_run(session, conversation_id=conversation_id, conversation_scope=ConversationScope.INVESTIGATION, investigation_id=tree.investigation_id)
    async with open_session() as session:
        await purge_expired_incidents(session, CUTOFF, batch_size=500)
    assert await _count_answer_runs_and_steps(stored) == (1, 2)


# ── Stored traces of global conversations: nothing expires unless ASK_KEIGAN_TRACE_RETENTION_DAYS is set (D4) ──


async def _global_run_started(days_ago: int) -> StoredAnswerRun:
    async with open_session() as session:
        return await store_answer_run(session, started_at=datetime.now(UTC) - timedelta(days=days_ago))


async def test_by_default_the_retention_cleanup_keeps_every_stored_trace(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_trace_retention_days", None)
    stored = await _global_run_started(days_ago=3000)
    async with open_session() as session:
        removed = await AdministrationService(session).run_retention_cleanup()
    assert removed is not None
    assert await _count_answer_runs_and_steps(stored) == (1, 2)


async def test_with_a_retention_set_only_older_traces_of_global_conversations_are_removed_and_the_conversation_stays(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_trace_retention_days", 90)
    old, recent = await _global_run_started(days_ago=120), await _global_run_started(days_ago=10)
    async with open_session() as session:
        removed = await AdministrationService(session).run_retention_cleanup()
    assert removed is not None and removed["chatAnswerRuns"] >= 1 and removed["chatRunSteps"] >= 2
    assert await _count_answer_runs_and_steps(old) == (0, 0)
    assert await _count_answer_runs_and_steps(recent) == (1, 2)
    async with open_session() as session:
        assert await session.get(Conversation, old.conversation_id) is not None
        assert await session.get(ConversationMessage, old.user_message_id) is not None


async def test_the_trace_retention_leaves_the_runs_of_investigation_conversations_alone(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_trace_retention_days", 90)
    tree = await _create_incident_tree(seed_context.application_ids_by_code["CLMJP"], opened_at=RECENT, incident_status="investigating")
    async with open_session() as session:
        conversation_id = await session.scalar(select(Conversation.conversation_id).where(Conversation.incident_id == tree.incident_id))
        stored = await store_answer_run(
            session, conversation_id=conversation_id, conversation_scope=ConversationScope.INVESTIGATION, investigation_id=tree.investigation_id, started_at=datetime.now(UTC) - timedelta(days=400)
        )
    async with open_session() as session:
        await AdministrationService(session).run_retention_cleanup()
    assert await _count_answer_runs_and_steps(stored) == (1, 2)


async def test_the_trace_retention_works_through_batches(seed_context) -> None:
    from keigan.services.answer_run_retention import purge_expired_answer_runs

    stored_runs = [await _global_run_started(days_ago=200) for _ in range(5)]
    async with open_session() as session:
        removed = await purge_expired_answer_runs(session, datetime.now(UTC) - timedelta(days=90), batch_size=2)
    assert removed["chatAnswerRuns"] >= 5
    assert [await _count_answer_runs_and_steps(stored) for stored in stored_runs] == [(0, 0)] * 5

"""Demo incidents and investigations (step 30): one resolved incident per historical simulation scenario.

For each historical window the REAL evidence collection runs against the simulator for that window; hypotheses, the RCA,
communications and the postmortem then come from the offline mock factories (so the seed is deterministic and needs no API
key). A live scenario is also triggered once so an open incident appears when the app starts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import Incident, IncidentCommunication, Investigation, InvestigationTimelineEvent, PostmortemReport, ServiceNowAssignmentGroup
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.seed.foundation_seed import SeedContext
from keigan.services.communication_service import CommunicationService
from keigan.services.investigation_service import InvestigationService
from keigan.utils.pii_masker import PiiMasker
from keigan.entities.status_values import CommunicationStatus, IncidentSource, IncidentStatus, InvestigationFeedbackVerdict, InvestigationStatus, InvestigationTrigger, PostmortemStatus

SEED_ORDER = 30
SEED_ACTOR = "system:seed"
ADMIN_UPN = "keigan.admin@keigan.local"
logger = logging.getLogger(__name__)


def _parse(timestamp_text: str) -> datetime:
    return datetime.fromisoformat(timestamp_text).astimezone(UTC)


async def seed(session: AsyncSession, seed_context: SeedContext) -> None:
    now = datetime.now(UTC)
    scenario_windows = sorted(seed_context.historical_scenarios, key=lambda window: window["started_at"])
    for index, window in enumerate(scenario_windows):
        try:
            await _seed_historical_incident(session, window, index, is_recent=index >= len(scenario_windows) - 2, now=now)
        except Exception:  # noqa: BLE001 — one scenario must not block the others
            logger.exception("Could not seed the historical incident %s", window.get("external_incident_number"))
            await session.rollback()
    await session.commit()  # the ServiceNow simulator writes through its own session
    await _trigger_live_scenario(session, seed_context)


async def _seed_historical_incident(session: AsyncSession, window: dict[str, Any], index: int, *, is_recent: bool, now: datetime) -> None:
    incident_number = window["external_incident_number"]
    application_id = window["application_id"]
    if await session.scalar(select(Incident.incident_id).where(Incident.application_id == application_id, Incident.external_incident_number == incident_number)):
        return
    scenario = SCENARIO_CATALOG[window["scenario_key"]]
    application = await session.get(Application, application_id)
    primary_service = await session.get(MonitoredService, window["primary_service_ids"][0])
    assert application is not None and primary_service is not None
    started_at, ended_at = _parse(window["started_at"]), _parse(window["ended_at"])
    opened_at = started_at + timedelta(minutes=6)
    assignment_group = await session.scalar(select(ServiceNowAssignmentGroup.group_name).where(ServiceNowAssignmentGroup.application_id == application_id).limit(1))
    masker = PiiMasker()
    incident = Incident(
        application_id=application_id, incident_source=IncidentSource.SERVICENOW, external_incident_number=incident_number, external_system_identifier=f"seed-{incident_number}",
        incident_title=scenario.servicenow_short_description.format(application_name=application.application_name, service_name=primary_service.service_name),
        incident_description=masker.mask_text(scenario.servicenow_description.format(started_at_local=started_at.strftime("%H:%M UTC"))),
        servicenow_priority=scenario.servicenow_priority, servicenow_impact="2", servicenow_urgency="1" if scenario.servicenow_priority in ("1", "2") else "2",
        keigan_priority=f"P{min(int(scenario.servicenow_priority), 4)}", incident_category=scenario.incident_category, incident_status=IncidentStatus.RESOLVED, external_state="resolved",
        assignment_group_name=assignment_group, opened_at=opened_at, detected_by_keigan_at=opened_at + timedelta(minutes=1),
        resolved_at=ended_at, external_last_updated_at=ended_at, created_by_user_principal_name=SEED_ACTOR,
    )
    incident.replace_linked_ids("affected_service_links", window["primary_service_ids"])
    session.add(incident)
    await session.flush()
    window_start = opened_at - timedelta(minutes=60)
    investigation = Investigation(
        application_id=application_id, incident_id=incident.incident_id, investigation_trigger=InvestigationTrigger.INCIDENT, investigation_status=InvestigationStatus.QUEUED, investigation_window_start=window_start,
        investigation_window_end=min(ended_at + timedelta(minutes=5), window_start + timedelta(minutes=240)), requested_by_user_principal_name=SEED_ACTOR, created_by_user_principal_name=SEED_ACTOR,
    )
    session.add(investigation)
    await session.flush()
    investigation_service = InvestigationService(session)
    await investigation_service.run_investigation_offline(investigation.investigation_id)
    await session.refresh(investigation)
    if not investigation.investigation_status.startswith("completed"):
        raise RuntimeError(f"Seeded investigation ended as {investigation.investigation_status}: {investigation.failure_reason}")

    # Historical timestamps so the incident room, timers and timeline look lived-in.
    investigation.created_at, investigation.started_at, investigation.completed_at = opened_at + timedelta(minutes=1), opened_at + timedelta(minutes=1), opened_at + timedelta(minutes=4)
    investigation.user_feedback_verdict = InvestigationFeedbackVerdict.PARTIALLY_CORRECT if index == 3 else InvestigationFeedbackVerdict.CORRECT
    investigation.user_feedback_by_user_principal_name = ADMIN_UPN
    offsets = {"investigation_started": 1, "evidence_collected": 3, "rca_completed": 4, "communications_drafted": 5}
    timeline_events = (await session.scalars(select(InvestigationTimelineEvent).where(InvestigationTimelineEvent.investigation_id == investigation.investigation_id))).all()
    for event in timeline_events:
        if event.event_type in offsets:
            event.event_occurred_at = opened_at + timedelta(minutes=offsets[event.event_type])
    session.add_all(
        [
            InvestigationTimelineEvent(incident_id=incident.incident_id, event_occurred_at=opened_at, event_type="incident_opened", event_title=f"Incident {incident_number} opened in ServiceNow", event_source="servicenow", source_reference=incident_number),
            InvestigationTimelineEvent(incident_id=incident.incident_id, investigation_id=investigation.investigation_id, event_occurred_at=opened_at + timedelta(minutes=20), event_type="chat_fact", event_title="Responder confirmed the proposed fix was applied", event_details_markdown="Captured from the incident chat.", event_source="teams"),
            InvestigationTimelineEvent(incident_id=incident.incident_id, event_occurred_at=ended_at, event_type="incident_resolved", event_title="Incident resolved", event_details_markdown="Service restored after the proposed fix was applied.", event_source="keigan", actor_display_name="Kai Admin"),
        ]
    )

    comms_service = CommunicationService(session)
    await comms_service.generate_communications(investigation.investigation_id, ["resolution_update"], ["en", "ja"], offline_ai=True)
    communications = (await session.scalars(select(IncidentCommunication).where(IncidentCommunication.investigation_id == investigation.investigation_id))).all()
    for communication in communications:
        communication.communication_status = CommunicationStatus.SENT
        communication.approved_by_user_principal_name = ADMIN_UPN
        communication.approved_at = opened_at + timedelta(minutes=6)
        communication.sent_at = ended_at + timedelta(minutes=2) if communication.communication_type == "resolution_update" else opened_at + timedelta(minutes=7)
        communication.created_at = opened_at + timedelta(minutes=5) if communication.communication_type != "resolution_update" else ended_at + timedelta(minutes=1)
    incident.first_update_sent_at = opened_at + timedelta(minutes=7)
    await session.execute(update(InvestigationTimelineEvent).where(InvestigationTimelineEvent.incident_id == incident.incident_id, InvestigationTimelineEvent.event_type == "communications_drafted", InvestigationTimelineEvent.event_occurred_at > ended_at).values(event_occurred_at=ended_at + timedelta(minutes=1)))

    await comms_service.write_postmortem_offline(incident.incident_id)
    postmortem = await session.scalar(select(PostmortemReport).where(PostmortemReport.incident_id == incident.incident_id))
    if postmortem is not None:
        postmortem.created_at = ended_at + timedelta(hours=1)
        if postmortem.report_status == PostmortemStatus.DRAFT and not is_recent:
            postmortem.report_status = PostmortemStatus.FINAL
            postmortem.finalized_by_user_principal_name, postmortem.finalized_at = ADMIN_UPN, min(ended_at + timedelta(days=1), now_utc())
            postmortem.sent_at = postmortem.finalized_at + timedelta(minutes=5)
    await session.flush()


def now_utc() -> datetime:
    return datetime.now(UTC)


async def _trigger_live_scenario(session: AsyncSession, seed_context: SeedContext) -> None:
    """Start one live scenario (guarded and idempotent) so the poller picks up an open incident on the next start."""
    try:
        from keigan.services.simulation_service import SimulationService

        simulation_service = SimulationService(session)
        configuration = await simulation_service.read_configuration()
        if any(not window.get("historical") for window in configuration.get("scenario_windows", [])):
            return
        application_id = seed_context.application_ids_by_code.get("CLMJP")
        if application_id:
            await simulation_service.trigger_scenario(application_id, "database_connection_pool_exhaustion")
    except Exception as trigger_error:  # noqa: BLE001
        logger.warning("The live demo scenario was not started: %s", trigger_error)

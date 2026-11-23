"""Incidents: ServiceNow polling, incident upsert and triage trigger, status sync, ServiceNow incident creation, incident room queries.

Slice S2. Contract methods (used by S3 and the job queue) keep their signatures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import IntegrationMode, get_settings
from keigan.dtos.common_dtos import PagedResult
from keigan.dtos.incident_dtos import ApplicationReference, IncidentDetailDto, IncidentSummaryDto, InvestigationBrief, ResolveIncidentRequest
from keigan.entities.alert_entities import AlertGroup
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import Incident, Investigation, InvestigationTimelineEvent, PostmortemReport, ServiceNowAssignmentGroup
from keigan.entities.platform_entities import PlatformSetting
from keigan.entities.status_values import AlertGroupStatus, IncidentSource, IncidentStatus, InvestigationStatus, Priority
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.integrations.servicenow_client import ServiceNowClient, normalized_state_name, parse_servicenow_timestamp, read_field_display, read_field_value
from keigan.security.current_user import CurrentUser
from keigan.services.alert_group_link_service import AlertGroupLinkService
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.incident_memory_builder import enqueue_memory_refresh_for_incident
from keigan.services.incident_priority_rules import PRIORITY_NAMES, map_servicenow_priority
from keigan.services.investigation_service import InvestigationService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now
from keigan.services.error_budget_policy_service import enqueue_error_budget_evaluation
from keigan.workers.job_queue import JobQueue

ALERT_GROUP_ADOPTION_WINDOW_MINUTES = 60

logger = logging.getLogger(__name__)

FIRST_POLL_LOOKBACK = timedelta(hours=24)
OPEN_STATUSES = (IncidentStatus.NEW, IncidentStatus.INVESTIGATING, IncidentStatus.IDENTIFIED)
RESOLVED_SERVICENOW_STATES = ("resolved",)
CLOSED_SERVICENOW_STATES = ("closed", "canceled")


def priority_label_from_servicenow(servicenow_priority: str | None) -> str | None:
    digits = "".join(character for character in (servicenow_priority or "") if character.isdigit())[:1]
    return PRIORITY_NAMES[min(int(digits), 4) - 1] if digits else None


class IncidentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.servicenow_client = ServiceNowClient(self.settings, application_context.secret_store())

    # ══ ServiceNow polling (job: poll_servicenow) ═════════════════════════════
    async def poll_servicenow_for_application(self, application_id: str) -> dict[str, Any] | None:
        application = await self.session.get(Application, application_id)
        if application is None or self.settings.servicenow_mode == IntegrationMode.DISABLED:
            return None
        group_names = list((await self.session.scalars(select(ServiceNowAssignmentGroup.group_name).where(ServiceNowAssignmentGroup.application_id == application_id))).all())
        if not group_names:
            return {"polled": 0}
        watermark_key = f"servicenow_watermark:{application_id}"
        watermark_setting = await self.session.get(PlatformSetting, watermark_key)
        updated_since = (
            datetime.fromisoformat(watermark_setting.setting_value_json["updatedSince"])
            if watermark_setting and watermark_setting.setting_value_json and watermark_setting.setting_value_json.get("updatedSince")
            else utc_now() - FIRST_POLL_LOOKBACK
        )
        records = await self.servicenow_client.list_incidents(group_names, updated_since)
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all())
        newest_update = updated_since
        created_count = 0
        for record in sorted(records, key=lambda candidate: read_field_value(candidate, "sys_updated_on")):
            created_count += 1 if await self._upsert_incident(application, record, services) else 0
            record_updated_at = parse_servicenow_timestamp(read_field_value(record, "sys_updated_on"))
            if record_updated_at and record_updated_at > newest_update:
                newest_update = record_updated_at
        watermark_value = {"updatedSince": newest_update.isoformat()}
        if watermark_setting is None:
            self.session.add(PlatformSetting(setting_key=watermark_key, setting_value_json=watermark_value, setting_description="ServiceNow polling watermark"))
        else:
            watermark_setting.setting_value_json = watermark_value
        return {"polled": len(records), "newIncidents": created_count}

    async def _upsert_incident(self, application: Application, record: dict[str, Any], services: list[MonitoredService], source: str = "servicenow") -> Incident | None:
        """Create or update an incident from a ServiceNow record. Returns the incident only when it is new."""
        incident_number = read_field_value(record, "number")
        if not incident_number:
            return None
        existing = await self.session.scalar(select(Incident).where(Incident.application_id == application.application_id, Incident.external_incident_number == incident_number))
        state_name = normalized_state_name(record)
        updated_at = parse_servicenow_timestamp(read_field_value(record, "sys_updated_on"))
        priority_text, impact_text, urgency_text = read_field_value(record, "priority"), read_field_value(record, "impact"), read_field_value(record, "urgency")
        if existing is not None:
            await self._synchronize_existing_incident(existing, record, state_name, priority_text, impact_text, urgency_text, updated_at)
            return None
        masker = PiiMasker()
        configuration_item = read_field_display(record, "cmdb_ci").strip().lower()
        title_text = read_field_value(record, "short_description")
        matched_services = [service for service in services if service.service_name.lower() == configuration_item or (configuration_item == "" and service.service_name.lower() in title_text.lower())]
        incident_status = IncidentStatus.CLOSED if state_name in CLOSED_SERVICENOW_STATES else IncidentStatus.RESOLVED if state_name in RESOLVED_SERVICENOW_STATES else IncidentStatus.NEW
        now = utc_now()
        incident = Incident(
            application_id=application.application_id, incident_source=source, external_incident_number=incident_number, external_system_identifier=read_field_value(record, "sys_id"),
            incident_title=masker.mask_text(title_text)[:500], incident_description=masker.mask_text(read_field_value(record, "description")),
            servicenow_priority=priority_text or None, servicenow_impact=impact_text or None, servicenow_urgency=urgency_text or None,
            keigan_priority=map_servicenow_priority(impact_text, urgency_text, priority_text), incident_status=incident_status,
            assignment_group_name=read_field_display(record, "assignment_group") or None,
            external_state=state_name, opened_at=parse_servicenow_timestamp(read_field_value(record, "opened_at")) or now, detected_by_keigan_at=now,
            resolved_at=now if incident_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) else None, external_last_updated_at=updated_at, created_by_user_principal_name="system:poller",
        )
        incident.replace_linked_ids("affected_service_links", [service.service_id for service in matched_services])
        self.session.add(incident)
        await self.session.flush()
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=incident.incident_id, event_occurred_at=incident.opened_at, event_type="incident_opened", event_title=f"Incident {incident_number} opened in ServiceNow",
                event_details_markdown=f"Priority {priority_label_from_servicenow(priority_text) or 'n/a'}; assignment group {incident.assignment_group_name or 'n/a'}.", event_source="servicenow", source_reference=incident_number,
            )
        )
        if incident_status == IncidentStatus.NEW:
            if not await self._adopt_open_alert_group_investigation(incident):
                await InvestigationService(self.session).start_investigation(application.application_id, "incident", incident_id=incident.incident_id, requested_by_user_principal_name="system:poller")
            await JobQueue(self.session).enqueue("notify_incident_detected", {"incident_id": incident.incident_id}, deduplication_key=f"notify_incident_detected:{incident.incident_id}", priority_number=15)
        return incident

    async def _adopt_open_alert_group_investigation(self, incident: Incident) -> bool:
        """Alerts usually arrive before the ticket. If an open alert group of this application is already being investigated,
        link the incident to it instead of starting a second investigation of the same problem (mirror of alert grouping rule d)."""
        recent_activity_since = incident.opened_at - timedelta(minutes=ALERT_GROUP_ADOPTION_WINDOW_MINUTES)
        candidate_groups = list(
            (
                await self.session.scalars(
                    select(AlertGroup)
                    .where(
                        AlertGroup.application_id == incident.application_id, AlertGroup.group_status.in_((AlertGroupStatus.OPEN, AlertGroupStatus.INVESTIGATING, AlertGroupStatus.QUEUED)),
                        AlertGroup.incident_id.is_(None), AlertGroup.investigation_id.is_not(None), AlertGroup.last_activity_at >= recent_activity_since,
                    )
                    .order_by(AlertGroup.priority_score.desc(), AlertGroup.last_activity_at.desc())
                )
            ).all()
        )
        incident_service_ids = set(incident.affected_service_ids)
        matching_groups = [group for group in candidate_groups if not incident_service_ids or incident_service_ids & set(group.affected_service_ids or [group.primary_service_id])]
        if not matching_groups:
            return False
        adopted_group = matching_groups[0]
        await AlertGroupLinkService(self.session).link(adopted_group, incident_id=incident.incident_id)
        investigation = await self.session.get(Investigation, adopted_group.investigation_id)
        assert investigation is not None  # the group query only returns groups with an investigation, and the foreign key guarantees it exists
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=incident.incident_id, investigation_id=investigation.investigation_id, event_type="investigation_started",
                event_title=f"Linked to alert group {adopted_group.group_title[:120]}; Keigan continues the investigation it already started from the alerts",
                event_source="keigan", source_reference=adopted_group.alert_group_id,
            )
        )
        logger.info("Incident %s adopted alert group %s and its investigation", incident.external_incident_number, adopted_group.alert_group_id)
        return True

    async def _synchronize_existing_incident(
        self, incident: Incident, record: dict[str, Any], state_name: str, priority_text: str, impact_text: str, urgency_text: str, updated_at: datetime | None
    ) -> None:
        def add_event(event_type: str, title: str, details: str | None = None) -> None:
            self.session.add(InvestigationTimelineEvent(incident_id=incident.incident_id, event_type=event_type, event_title=title, event_details_markdown=details, event_source="servicenow", source_reference=incident.external_incident_number))

        if priority_text and priority_text != incident.servicenow_priority:
            add_event("priority_changed", f"ServiceNow priority changed from {priority_label_from_servicenow(incident.servicenow_priority) or 'n/a'} to {priority_label_from_servicenow(priority_text)}")
            incident.servicenow_priority, incident.servicenow_impact, incident.servicenow_urgency = priority_text, impact_text or incident.servicenow_impact, urgency_text or incident.servicenow_urgency
        if state_name and state_name != incident.external_state:
            add_event("state_changed", f"ServiceNow state changed to {state_name}")
            incident.external_state = state_name
            if state_name in CLOSED_SERVICENOW_STATES or state_name in RESOLVED_SERVICENOW_STATES:
                await enqueue_error_budget_evaluation(self.session, incident.application_id)  # the incident's budget figure is worked out now it has an end
            if state_name in CLOSED_SERVICENOW_STATES:
                incident.incident_status, incident.closed_at = IncidentStatus.CLOSED, utc_now()
                incident.resolved_at = incident.resolved_at or utc_now()
            elif state_name in RESOLVED_SERVICENOW_STATES:
                incident.incident_status, incident.resolved_at = IncidentStatus.RESOLVED, incident.resolved_at or utc_now()
            elif incident.incident_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                incident.incident_status, incident.resolved_at, incident.closed_at = IncidentStatus.INVESTIGATING, None, None
                add_event("incident_reopened", "Incident reopened in ServiceNow")
        assignment_group = read_field_display(record, "assignment_group")
        if assignment_group and assignment_group != incident.assignment_group_name:
            add_event("assignment_changed", f"Assigned to {assignment_group}")
            incident.assignment_group_name = assignment_group
        incident.external_last_updated_at = updated_at or incident.external_last_updated_at

    # ══ Contract used by S3 ═══════════════════════════════════════════════════
    async def create_servicenow_incident_from_alert_group(self, alert_group_id: str, requested_by_user_principal_name: str | None = None) -> str:
        alert_group = await self.session.get(AlertGroup, alert_group_id)
        if alert_group is None:
            raise NotFoundException("The alert group was not found.")
        if alert_group.incident_id:
            return alert_group.incident_id
        application = await self.session.get(Application, alert_group.application_id)
        assert application is not None
        assignment_group = await self.session.scalar(select(ServiceNowAssignmentGroup).where(ServiceNowAssignmentGroup.application_id == application.application_id).limit(1))
        if assignment_group is None:
            raise BusinessValidationException("Add a ServiceNow assignment group to this application before creating incidents from alerts.")
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application.application_id))).all())
        primary_service = next((service for service in services if service.service_id == alert_group.primary_service_id), None)
        servicenow_priority = str(min(max(alert_group.highest_severity_level, 0) + 1, 4))
        created_record = await self.servicenow_client.create_incident(
            {
                "short_description": f"{application.application_name}: {alert_group.group_title}"[:160], "description": f"{alert_group.group_summary or ''}\n\nCreated by Keigan from an alert group with {alert_group.member_alert_count} alert(s).",
                "priority": servicenow_priority, "impact": servicenow_priority if int(servicenow_priority) <= 3 else "3", "urgency": servicenow_priority if int(servicenow_priority) <= 3 else "3",
                "assignment_group": assignment_group.group_name, "cmdb_ci": primary_service.service_name if primary_service else "", "opened_at": alert_group.started_at,
            }
        )
        incident = await self._upsert_incident(application, created_record, services, source="alert")
        if incident is None:
            incident = await self.session.scalar(select(Incident).where(Incident.application_id == application.application_id, Incident.external_incident_number == read_field_value(created_record, "number")))
        assert incident is not None
        await AlertGroupLinkService(self.session).link(alert_group, incident_id=incident.incident_id)  # also gives the investigation that already analysed the group this incident
        if alert_group.investigation_id:
            pending_investigations = await self.session.scalars(select(Investigation).where(Investigation.incident_id == incident.incident_id, Investigation.investigation_id != alert_group.investigation_id, Investigation.investigation_status == InvestigationStatus.QUEUED))
            for pending_investigation in pending_investigations:
                pending_investigation.investigation_status = InvestigationStatus.CANCELLED
        await AuditService(self.session).record(requested_by_user_principal_name or "system:worker", "incident.create_from_alert_group", target_entity_type="incident", target_entity_id=incident.incident_id, application_id=application.application_id, action_details={"alertGroupId": alert_group_id, "number": incident.external_incident_number})
        return incident.incident_id

    # ══ Incident room API ═════════════════════════════════════════════════════
    async def list_incidents(
        self, current_user: CurrentUser, *, application_ids: list[str] | None, priorities: list[str] | None, statuses: list[str] | None, sources: list[str] | None,
        from_time: datetime | None, to_time: datetime | None, search: str | None, only_mine: bool, page: int, page_size: int,
    ) -> PagedResult[IncidentSummaryDto]:
        scoped_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids)
        conditions: list[Any] = [Incident.application_id.in_(scoped_ids or ["none"])]
        if priorities:
            conditions.append(func.coalesce(Incident.keigan_priority, Priority.P3).in_(priorities))
        if statuses:
            conditions.append(Incident.incident_status.in_(statuses))
        if sources:
            conditions.append(Incident.incident_source.in_(sources))
        if from_time:
            conditions.append(Incident.opened_at >= from_time)
        if to_time:
            conditions.append(Incident.opened_at <= to_time)
        if search:
            like_pattern = f"%{search.strip().lower()}%"
            conditions.append(or_(func.lower(Incident.incident_title).like(like_pattern), func.lower(func.coalesce(Incident.external_incident_number, "")).like(like_pattern)))
        if only_mine:
            mine_ids = select(Investigation.incident_id).where(Investigation.requested_by_user_principal_name == current_user.user_principal_name, Investigation.incident_id.is_not(None))
            conditions.append(or_(Incident.incident_id.in_(mine_ids), Incident.created_by_user_principal_name == current_user.user_principal_name))
        total_count = int(await self.session.scalar(select(func.count()).select_from(Incident).where(*conditions)) or 0)
        incidents = list(
            (await self.session.scalars(select(Incident).where(*conditions).order_by(Incident.opened_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
        )
        return PagedResult[IncidentSummaryDto](items=await self.summarize_incidents(incidents), total_count=total_count, page=page, page_size=page_size)

    async def get_incident(self, current_user: CurrentUser, incident_id: str) -> IncidentDetailDto:
        incident = await self.load_readable_incident(current_user, incident_id)
        summary = (await self.summarize_incidents([incident]))[0]
        latest_investigation = await self.session.scalar(select(Investigation).where(Investigation.incident_id == incident_id).order_by(Investigation.created_at.desc()).limit(1))
        postmortem = await self.session.scalar(select(PostmortemReport).where(PostmortemReport.incident_id == incident_id).order_by(PostmortemReport.created_at.desc()).limit(1))
        return IncidentDetailDto(
            **summary.model_dump(), incident_description=incident.incident_description, priority_rationale=incident.priority_rationale, servicenow_impact=incident.servicenow_impact,
            servicenow_urgency=incident.servicenow_urgency, first_update_sent_at=incident.first_update_sent_at, closed_at=incident.closed_at,
            latest_investigation=InvestigationBrief.model_validate(latest_investigation) if latest_investigation else None,
            postmortem_id=postmortem.postmortem_id if postmortem else None, postmortem_status=postmortem.report_status if postmortem else None,
        )

    async def load_readable_incident(self, current_user: CurrentUser, incident_id: str, require_admin: bool = False) -> Incident:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundException("The incident was not found.")
        authorization = AuthorizationService(self.session)
        if require_admin:
            await authorization.ensure_application_admin(current_user, incident.application_id)
        else:
            await authorization.ensure_application_reader(current_user, incident.application_id)
        return incident

    async def resolve_incident(self, current_user: CurrentUser, incident_id: str, request: ResolveIncidentRequest) -> IncidentDetailDto:
        incident = await self.load_readable_incident(current_user, incident_id, require_admin=True)
        if incident.incident_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            raise BusinessValidationException("This incident is already resolved.")
        now = utc_now()
        incident.incident_status, incident.resolved_at, incident.updated_by_user_principal_name = IncidentStatus.RESOLVED, now, current_user.user_principal_name
        note_text = PiiMasker().mask_text(request.resolution_note or "")
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=incident.incident_id, event_occurred_at=now, event_type="incident_resolved", event_title="Incident resolved", event_details_markdown=note_text or None,
                event_source="keigan", actor_display_name=current_user.display_name,
            )
        )
        if incident.external_system_identifier:
            try:
                changed_fields: dict[str, Any] = {"state": "Resolved" if self.servicenow_client.is_simulated else "6", "close_notes": note_text or "Resolved (recorded by Keigan)."}
                if not self.servicenow_client.is_simulated:
                    changed_fields["close_code"] = "Solved (Permanently)"
                await self.servicenow_client.update_incident(incident.external_system_identifier, changed_fields)
                incident.external_state = "resolved"
            except Exception as servicenow_error:  # noqa: BLE001 — the incident is resolved in Keigan regardless
                logger.warning("Could not update ServiceNow for %s: %s", incident.external_incident_number, servicenow_error)
                self.session.add(InvestigationTimelineEvent(incident_id=incident.incident_id, event_type="servicenow_update_failed", event_title="Could not update the ServiceNow incident", event_details_markdown="Update the state in ServiceNow manually.", event_source="keigan"))
        latest_investigation = await self.session.scalar(select(Investigation).where(Investigation.incident_id == incident_id).order_by(Investigation.created_at.desc()).limit(1))
        if latest_investigation is not None and latest_investigation.investigation_status.startswith("completed"):
            await JobQueue(self.session).enqueue(
                "generate_communications", {"investigation_id": latest_investigation.investigation_id, "communication_types": ["resolution_update"], "language_codes": ["en", "ja"]},
                deduplication_key=f"resolution_comms:{incident_id}",
            )
        await enqueue_memory_refresh_for_incident(self.session, incident_id)  # the resolution note is what fixed it
        if request.generate_postmortem:
            from keigan.services.communication_service import CommunicationService

            await CommunicationService(self.session).start_postmortem(current_user, incident_id, "user_button")
        await enqueue_error_budget_evaluation(self.session, incident.application_id)
        await AuditService(self.session).record(current_user, "incident.resolve", target_entity_type="incident", target_entity_id=incident_id, application_id=incident.application_id, action_details={"generatePostmortem": request.generate_postmortem})
        await self.session.flush()
        return await self.get_incident(current_user, incident_id)

    # ── Summaries ──────────────────────────────────────────────────────────────
    async def summarize_incidents(self, incidents: list[Incident]) -> list[IncidentSummaryDto]:
        if not incidents:
            return []
        application_ids = {incident.application_id for incident in incidents}
        applications = {application.application_id: application for application in (await self.session.scalars(select(Application).where(Application.application_id.in_(application_ids)))).all()}
        service_ids = {service_id for incident in incidents for service_id in incident.affected_service_ids}
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))).all()} if service_ids else {}
        investigations = (await self.session.scalars(select(Investigation).where(Investigation.incident_id.in_([incident.incident_id for incident in incidents])).order_by(Investigation.created_at.desc()))).all()
        latest_by_incident: dict[str, Investigation] = {}
        for investigation in investigations:
            latest_by_incident.setdefault(investigation.incident_id or "", investigation)
        now = utc_now()
        summaries: list[IncidentSummaryDto] = []
        for incident in incidents:
            application = applications[incident.application_id]
            investigation = latest_by_incident.get(incident.incident_id)
            end_time = incident.resolved_at or now
            summaries.append(
                IncidentSummaryDto(
                    incident_id=incident.incident_id, application=ApplicationReference(application_id=application.application_id, application_code=application.application_code, application_name=application.application_name),
                    incident_source=incident.incident_source, external_incident_number=incident.external_incident_number, incident_title=incident.incident_title,
                    servicenow_priority=priority_label_from_servicenow(incident.servicenow_priority), keigan_priority=incident.keigan_priority, incident_category=incident.incident_category,
                    incident_status=incident.incident_status, external_state=incident.external_state, affected_service_names=[service_names[service_id] for service_id in incident.affected_service_ids if service_id in service_names],
                    assignment_group_name=incident.assignment_group_name, opened_at=incident.opened_at, detected_by_keigan_at=incident.detected_by_keigan_at, resolved_at=incident.resolved_at,
                    duration_minutes=max(0, int((end_time - incident.opened_at).total_seconds() // 60)), keigan_confidence=investigation.overall_confidence_score if investigation else None,
                    latest_investigation_id=investigation.investigation_id if investigation else None, latest_investigation_status=investigation.investigation_status if investigation else None,
                    servicenow_url=self.servicenow_client.incident_url(incident.external_incident_number) if incident.incident_source != IncidentSource.MANUAL else None,
                )
            )
        return summaries

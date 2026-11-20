"""Stakeholder routing, email, Teams incident chats, bot replies, chat polling, milestone detection and the outbox.

Every message becomes a ``notification_delivery`` row and a ``deliver_notification`` job. Teams chat traffic lives in
``TeamsChatService``; this class owns routing, rendering and the outbox.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import EmailMode, IntegrationMode, get_settings
from keigan.dtos.common_dtos import PagedResult
from keigan.dtos.notification_dtos import NotificationDeliveryDetail, NotificationDeliverySummary
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import Incident, IncidentCommunication, Investigation, PostmortemReport
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder, TeamsIncidentChat
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SloBurnAlert
from keigan.exceptions.keigan_exceptions import IntegrationException, NotFoundException
from keigan.integrations.email_sender import SmtpEmailSender
from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient
from keigan.services.notification_renderer import NotificationRenderer, RenderedEmail, resolve_language_code, translate
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
PRIORITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
COMMUNICATION_TO_NOTIFICATION_TYPE = {"preliminary_report": "preliminary_report", "initial_update": "incident_detected"}
EXECUTIVE_ROLES = {"manager", "executive", "business_owner"}
TECHNICAL_ROLES = {"sre", "developer", "vendor_contact"}
MAXIMUM_DELIVERY_ATTEMPTS = 3


def priority_rank(priority_code: str | None) -> int:
    return PRIORITY_RANK.get((priority_code or "P3").upper(), 3)


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.renderer = NotificationRenderer()

    # ── Routing ────────────────────────────────────────────────────────────────
    async def matching_stakeholders(
        self, application_id: str, notification_type: str, channel: str, *, priority: str | None = None, service_ids: list[str] | None = None
    ) -> list[Stakeholder]:
        """Active stakeholders that subscribed to the type and channel, whose services intersect and whose minimum priority is met."""
        stakeholders = (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == application_id, Stakeholder.is_active.is_(True)).order_by(Stakeholder.display_name))).all()
        matches: list[Stakeholder] = []
        for stakeholder in stakeholders:
            if notification_type not in (stakeholder.subscribed_notification_types_json or []):
                continue
            if channel not in (stakeholder.notification_channels_json or []):
                continue
            if priority is not None and priority_rank(priority) > priority_rank(stakeholder.minimum_priority):
                continue
            subscribed_services = set(stakeholder.subscribed_service_ids_json or [])
            if subscribed_services and service_ids and not subscribed_services.intersection(service_ids):
                continue
            matches.append(stakeholder)
        return matches

    @staticmethod
    def recipient_address_for(stakeholder: Stakeholder, channel: str) -> str | None:
        if channel == "teams_channel":
            return f"{stakeholder.teams_team_id}/{stakeholder.teams_channel_id}" if stakeholder.teams_channel_id else None
        return stakeholder.email_address or stakeholder.user_principal_name

    async def _application_name(self, application_id: str) -> str:
        application = await self.session.get(Application, application_id)
        return application.application_name if application else "Keigan"

    async def _service_names(self, service_ids: list[str] | None) -> str:
        if not service_ids:
            return ""
        names = (await self.session.scalars(select(MonitoredService.service_name).where(MonitoredService.service_id.in_(service_ids)))).all()
        return ", ".join(sorted(names))

    # ── Outbox ─────────────────────────────────────────────────────────────────
    async def queue_email(
        self, application_id: str | None, notification_type: str, recipient_address: str, rendered: RenderedEmail, *, incident_id: str | None = None, investigation_id: str | None = None,
        channel: str = "email", deduplicate: bool = False, ignore_subject: bool = False,
    ) -> str | None:
        """Add an outbox row and the delivery job. With ``deduplicate`` the same incident/type/recipient is only ever queued once."""
        if deduplicate and incident_id:
            existing_identifier = await self.session.scalar(select(NotificationDelivery.notification_delivery_id).where(
                NotificationDelivery.incident_id == incident_id, NotificationDelivery.notification_type == notification_type,
                NotificationDelivery.recipient_address == recipient_address, NotificationDelivery.delivery_channel == channel,
                *([] if ignore_subject else [NotificationDelivery.subject_line == rendered.subject_line])).limit(1))
            if existing_identifier:
                return None
        delivery = NotificationDelivery(
            application_id=application_id, incident_id=incident_id, investigation_id=investigation_id, notification_type=notification_type, delivery_channel=channel,
            recipient_address=recipient_address, subject_line=rendered.subject_line, body_html=rendered.body_html, body_text=rendered.body_text, delivery_status="pending",
        )
        self.session.add(delivery)
        await self.session.flush()
        from keigan.workers.job_queue import JobQueue

        await JobQueue(self.session).enqueue("deliver_notification", {"notification_delivery_id": delivery.notification_delivery_id}, deduplication_key=f"deliver:{delivery.notification_delivery_id}", priority_number=20)
        return delivery.notification_delivery_id

    async def record_chat_delivery(self, application_id: str, incident_id: str, notification_type: str, chat_identifier: str, subject_line: str, body_text: str, delivery_status: str, error_message: str | None = None) -> None:
        self.session.add(NotificationDelivery(
            application_id=application_id, incident_id=incident_id, notification_type=notification_type, delivery_channel="teams_incident_chat", recipient_address=chat_identifier,
            subject_line=subject_line[:400], body_text=body_text, delivery_status=delivery_status, attempt_count=1, last_error_message=error_message, sent_at=utc_now() if delivery_status in ("sent", "simulated") else None,
        ))
        await self.session.flush()

    async def deliver(self, notification_delivery_id: str) -> dict[str, Any] | None:
        """Job handler: send one outbox row through Graph, SMTP or the simulator."""
        delivery = await self.session.get(NotificationDelivery, notification_delivery_id)
        if delivery is None or delivery.delivery_status in ("sent", "simulated", "skipped"):
            return None
        delivery.attempt_count += 1
        try:
            provider_identifier = await self._send_through_provider(delivery)
        except IntegrationException as delivery_error:
            delivery.last_error_message = delivery_error.detail[:1000]
            if delivery.attempt_count >= MAXIMUM_DELIVERY_ATTEMPTS:
                delivery.delivery_status = "failed"
                await self.session.flush()
                return {"status": "failed", "error": delivery.last_error_message}
            delivery.delivery_status = "pending"
            await self.session.flush()
            await self.session.commit()  # keep the attempt counter, then let the queue retry
            raise
        delivery.provider_message_identifier = provider_identifier
        delivery.sent_at = utc_now()
        delivery.last_error_message = None
        await self.session.flush()
        return {"status": delivery.delivery_status}

    async def _send_through_provider(self, delivery: NotificationDelivery) -> str | None:
        if delivery.delivery_channel == "email":
            if self.settings.email_mode == EmailMode.GRAPH:
                await MicrosoftGraphClient(application_context.azure_credential_provider()).send_mail(delivery.recipient_address, delivery.subject_line or "", delivery.body_html or "")
                delivery.delivery_status = "sent"
                return "graph-sendMail"
            if self.settings.email_mode == EmailMode.SMTP:
                provider_identifier = await SmtpEmailSender(self.settings, application_context.secret_store()).send(delivery.recipient_address, delivery.subject_line or "", delivery.body_html or "", delivery.body_text or "")
                delivery.delivery_status = "sent"
                return provider_identifier
            delivery.delivery_status = "skipped" if self.settings.email_mode == EmailMode.DISABLED else "simulated"
            return f"simulated:{delivery.notification_delivery_id}"
        if delivery.delivery_channel == "teams_channel":
            if self.settings.teams_mode != IntegrationMode.LIVE:
                delivery.delivery_status = "simulated"
                return f"simulated:{delivery.notification_delivery_id}"
            from keigan.services.teams_chat_service import TeamsChatService

            provider_identifier = await TeamsChatService(self.session).send_to_channel(delivery.recipient_address, delivery.subject_line or "", delivery.body_text or "")
            delivery.delivery_status = "sent"
            return provider_identifier
        delivery.delivery_status = "simulated"
        return f"simulated:{delivery.notification_delivery_id}"

    async def list_outbox(self, application_id: str | None, notification_type: str | None, delivery_status: str | None, page: int, page_size: int) -> PagedResult[NotificationDeliverySummary]:
        conditions = []
        if application_id:
            conditions.append(NotificationDelivery.application_id == application_id)
        if notification_type:
            conditions.append(NotificationDelivery.notification_type == notification_type)
        if delivery_status:
            conditions.append(NotificationDelivery.delivery_status == delivery_status)
        total_count = await self.session.scalar(select(func.count()).select_from(NotificationDelivery).where(*conditions)) or 0
        rows = (await self.session.scalars(select(NotificationDelivery).where(*conditions).order_by(NotificationDelivery.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all()
        application_names = {application.application_id: application.application_name for application in (await self.session.scalars(select(Application))).all()}
        items = [NotificationDeliverySummary(**self._summary_values(row), application_name=application_names.get(row.application_id or "")) for row in rows]
        return PagedResult[NotificationDeliverySummary](items=items, total_count=total_count, page=page, page_size=page_size)

    @staticmethod
    def _summary_values(row: NotificationDelivery) -> dict[str, Any]:
        return {
            "notification_delivery_id": row.notification_delivery_id, "application_id": row.application_id, "incident_id": row.incident_id, "notification_type": row.notification_type,
            "delivery_channel": row.delivery_channel, "recipient_address": row.recipient_address, "subject_line": row.subject_line, "delivery_status": row.delivery_status,
            "attempt_count": row.attempt_count, "last_error_message": row.last_error_message, "created_at": row.created_at, "sent_at": row.sent_at,
        }

    async def get_outbox_delivery(self, notification_delivery_id: str) -> NotificationDeliveryDetail:
        row = await self.session.get(NotificationDelivery, notification_delivery_id)
        if row is None:
            raise NotFoundException("Notification delivery not found.")
        application_name = await self._application_name(row.application_id) if row.application_id else None
        return NotificationDeliveryDetail(**self._summary_values(row), application_name=application_name, body_html=row.body_html, body_text=row.body_text, provider_message_identifier=row.provider_message_identifier, investigation_id=row.investigation_id)

    # ── Incident lifecycle (job handlers) ──────────────────────────────────────
    async def on_incident_detected(self, incident_id: str) -> dict[str, Any] | None:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            return None
        application_name = await self._application_name(incident.application_id)
        priority = incident.keigan_priority or "P3"
        facts_services = await self._service_names(incident.affected_service_ids_json)
        queued_count = 0
        for stakeholder in await self.matching_stakeholders(incident.application_id, "incident_detected", "email", priority=priority, service_ids=incident.affected_service_ids_json):
            recipient_address = self.recipient_address_for(stakeholder, "email")
            if not recipient_address:
                continue
            language = stakeholder.preferred_language_code
            facts = [
                (translate(language, "labels.incident"), incident.external_incident_number or incident.incident_id[:8]), (translate(language, "labels.priority"), priority),
                (translate(language, "labels.application"), application_name), (translate(language, "labels.services"), facts_services), (translate(language, "labels.category"), (incident.incident_category or "").replace("_", " ")),
            ]
            rendered = self.renderer.render_email("incident_detected", language, application_name, incident.incident_title, facts=facts, body_markdown=incident.incident_description, action_path=f"/incidents/{incident.incident_id}", priority=priority)
            if await self.queue_email(incident.application_id, "incident_detected", recipient_address, rendered, incident_id=incident.incident_id, deduplicate=True):
                queued_count += 1
        chat_enqueued = False
        if self.settings.teams_mode != IntegrationMode.DISABLED and await self.matching_stakeholders(incident.application_id, "incident_detected", "teams_incident_chat", priority=priority, service_ids=incident.affected_service_ids_json):
            from keigan.workers.job_queue import JobQueue

            await JobQueue(self.session).enqueue("create_incident_chat", {"incident_id": incident_id}, deduplication_key=f"create_incident_chat:{incident_id}", priority_number=15)
            chat_enqueued = True
        return {"emailsQueued": queued_count, "chatRequested": chat_enqueued}

    @staticmethod
    def investigation_email_body(investigation: Investigation, *, include_fix: bool) -> str:
        """Audience rule: the fix steps (commands, resource names) go only to engineering roles; business stakeholders get impact and likely cause."""
        parts = [
            investigation.executive_summary,
            f"**What went wrong**\n{investigation.what_went_wrong_markdown}" if investigation.what_went_wrong_markdown else "",
            f"**Likely cause**\n{investigation.why_it_happened_markdown}" if investigation.why_it_happened_markdown else "",
            f"**Suggested fix**\n{investigation.how_to_fix_markdown}" if include_fix and investigation.how_to_fix_markdown else "",
        ]
        return "\n\n".join(part for part in parts if part)

    async def on_investigation_completed(self, investigation_id: str) -> dict[str, Any] | None:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None or investigation.incident_id is None:
            return None
        incident = await self.session.get(Incident, investigation.incident_id)
        if incident is None:
            return None
        application_name = await self._application_name(incident.application_id)
        priority = incident.keigan_priority or "P3"
        queued_count = 0
        if self.settings.auto_send_preliminary_report and investigation.investigation_status.startswith("completed"):
            confidence_text = f"{round((investigation.overall_confidence_score or 0) * 100)}%"
            for stakeholder in await self.matching_stakeholders(incident.application_id, "preliminary_report", "email", priority=priority, service_ids=incident.affected_service_ids_json):
                recipient_address = self.recipient_address_for(stakeholder, "email")
                if not recipient_address:
                    continue
                body_markdown = self.investigation_email_body(investigation, include_fix=stakeholder.stakeholder_role in TECHNICAL_ROLES)
                language = stakeholder.preferred_language_code
                facts = [(translate(language, "labels.incident"), incident.external_incident_number or ""), (translate(language, "labels.priority"), priority), (translate(language, "labels.confidence"), confidence_text)]
                rendered = self.renderer.render_email("preliminary_report", language, application_name, incident.incident_title, facts=facts, body_markdown=body_markdown, action_path=f"/incidents/{incident.incident_id}", priority=priority)
                if await self.queue_email(incident.application_id, "preliminary_report", recipient_address, rendered, incident_id=incident.incident_id, investigation_id=investigation_id, deduplicate=True, ignore_subject=True):
                    queued_count += 1
            if incident.first_update_sent_at is None and queued_count:
                incident.first_update_sent_at = utc_now()
        from keigan.services.teams_chat_service import TeamsChatService

        chat_service = TeamsChatService(self.session)
        card = self.renderer.render_card(
            "preliminary_report", "en", "preliminary_report", incident.incident_title, investigation.executive_summary or "",
            [("Incident", incident.external_incident_number or ""), ("Priority", priority), ("Confidence", f"{round((investigation.overall_confidence_score or 0) * 100)}%")], f"/incidents/{incident.incident_id}",
        )
        card_posted = await chat_service.post_card_if_chat_exists(incident.incident_id, f"Preliminary report: {incident.incident_title}", investigation.executive_summary or "", card)
        return {"emailsQueued": queued_count, "cardPosted": card_posted}

    # ── Called by other slices ─────────────────────────────────────────────────
    async def send_communication(self, communication_id: str, requested_by_user_principal_name: str | None = None) -> int:
        communication = await self.session.get(IncidentCommunication, communication_id)
        if communication is None or communication.incident_id is None:
            raise NotFoundException("Communication not found.")
        incident = await self.session.get(Incident, communication.incident_id)
        if incident is None:
            raise NotFoundException("Incident not found.")
        application_name = await self._application_name(incident.application_id)
        priority = incident.keigan_priority or "P3"
        notification_type = COMMUNICATION_TO_NOTIFICATION_TYPE.get(communication.communication_type, "progress_update")
        sibling_languages = set((await self.session.scalars(select(IncidentCommunication.language_code).where(
            IncidentCommunication.incident_id == communication.incident_id, IncidentCommunication.communication_type == communication.communication_type, IncidentCommunication.communication_status.in_(("approved", "sent", "draft"))))).all())
        sibling_languages = {resolve_language_code(code) for code in sibling_languages}
        own_language = resolve_language_code(communication.language_code)
        queued_count = 0
        for stakeholder in await self.matching_stakeholders(incident.application_id, notification_type, "email", priority=priority, service_ids=incident.affected_service_ids_json):
            recipient_address = self.recipient_address_for(stakeholder, "email")
            recipient_language = resolve_language_code(stakeholder.preferred_language_code)
            if not recipient_address or not (recipient_language == own_language or (own_language == "en" and recipient_language not in sibling_languages)):
                continue
            if communication.audience_type == "executives" and stakeholder.stakeholder_role not in EXECUTIVE_ROLES:
                continue
            if communication.audience_type == "technical" and stakeholder.stakeholder_role not in TECHNICAL_ROLES:
                continue
            facts = [(translate(own_language, "labels.incident"), incident.external_incident_number or ""), (translate(own_language, "labels.priority"), priority)]
            rendered = self.renderer.render_email(
                "progress_update", own_language, application_name, incident.incident_title, facts=facts, body_markdown=communication.body_markdown, action_path=f"/incidents/{incident.incident_id}",
                subject_override=communication.subject_line, priority=priority,
            )
            if await self.queue_email(incident.application_id, notification_type, recipient_address, rendered, incident_id=incident.incident_id, investigation_id=communication.investigation_id, deduplicate=True):
                queued_count += 1
        if own_language == "en" or own_language == resolve_language_code(None):
            from keigan.services.teams_chat_service import TeamsChatService

            await TeamsChatService(self.session).post_card_if_chat_exists(incident.incident_id, communication.subject_line, communication.body_markdown, None)
        return queued_count

    async def send_postmortem(self, postmortem_id: str, requested_by_user_principal_name: str | None = None) -> int:
        postmortem = await self.session.get(PostmortemReport, postmortem_id)
        if postmortem is None:
            raise NotFoundException("Postmortem not found.")
        incident = await self.session.get(Incident, postmortem.incident_id)
        if incident is None:
            raise NotFoundException("Incident not found.")
        application_name = await self._application_name(incident.application_id)
        queued_count = 0
        for stakeholder in await self.matching_stakeholders(incident.application_id, "postmortem", "email", service_ids=incident.affected_service_ids_json):
            recipient_address = self.recipient_address_for(stakeholder, "email")
            if not recipient_address:
                continue
            language = stakeholder.preferred_language_code
            facts = [(translate(language, "labels.incident"), incident.external_incident_number or ""), (translate(language, "labels.application"), application_name)]
            rendered = self.renderer.render_email("postmortem", language, application_name, incident.incident_title, facts=facts, body_markdown=postmortem.report_markdown, action_path=f"/incidents/{incident.incident_id}")
            if await self.queue_email(incident.application_id, "postmortem", recipient_address, rendered, incident_id=incident.incident_id, deduplicate=True):
                queued_count += 1
        from keigan.services.teams_chat_service import TeamsChatService

        card = self.renderer.render_card("postmortem_ready", "en", "postmortem_ready", postmortem.report_title, f"The postmortem for {incident.incident_title} is ready.", [("Incident", incident.external_incident_number or "")], f"/incidents/{incident.incident_id}")
        await TeamsChatService(self.session).post_card_if_chat_exists(incident.incident_id, postmortem.report_title, f"The postmortem for {incident.incident_title} is ready.", card)
        return queued_count

    async def post_to_incident_chat(self, incident_id: str, message_markdown: str, adaptive_card: dict[str, Any] | None = None) -> None:
        from keigan.services.teams_chat_service import TeamsChatService

        await TeamsChatService(self.session).post_card_if_chat_exists(incident_id, message_markdown[:120], message_markdown, adaptive_card)

    async def notify_slo_burn_alert(self, slo_burn_alert_id: str) -> int:
        burn_alert = await self.session.get(SloBurnAlert, slo_burn_alert_id)
        if burn_alert is None:
            return 0
        slo = await self.session.get(ServiceLevelObjective, burn_alert.slo_id)
        sli = await self.session.get(ServiceLevelIndicator, slo.sli_id) if slo else None
        if slo is None or sli is None:
            return 0
        application_name = await self._application_name(burn_alert.application_id)
        service_ids = [sli.service_id] if sli.service_id else None
        priority = "P1" if burn_alert.burn_alert_severity in ("page", "critical") else "P3"
        queued_count = 0
        for stakeholder in await self.matching_stakeholders(burn_alert.application_id, "slo_burn_alert", "email", priority=priority, service_ids=service_ids):
            recipient_address = self.recipient_address_for(stakeholder, "email")
            if not recipient_address:
                continue
            language = stakeholder.preferred_language_code
            facts = [
                (translate(language, "labels.slo"), f"{sli.sli_name} ({slo.target_percentage}% / {slo.rolling_window_days}d)"), (translate(language, "labels.severity"), burn_alert.burn_alert_severity),
                (translate(language, "labels.burn_rate"), f"{burn_alert.long_window_burn_rate}x (long) / {burn_alert.short_window_burn_rate}x (short)"),
            ]
            rendered = self.renderer.render_email("slo_burn_alert", language, application_name, sli.sli_name, facts=facts, action_path="/slos", severity=burn_alert.burn_alert_severity)
            delivery_identifier = await self.queue_email(burn_alert.application_id, "slo_burn_alert", recipient_address, rendered)
            queued_count += 1 if delivery_identifier else 0
        return queued_count

    # ── Chat job handlers (delegated) ──────────────────────────────────────────
    async def create_incident_chat(self, incident_id: str) -> dict[str, Any] | None:
        from keigan.services.teams_chat_service import TeamsChatService

        return await TeamsChatService(self.session).create_incident_chat(incident_id)

    async def poll_incident_chat(self, teams_incident_chat_id: str) -> dict[str, Any] | None:
        from keigan.services.teams_chat_service import TeamsChatService

        return await TeamsChatService(self.session).poll_incident_chat(teams_incident_chat_id)

    async def has_active_chat(self, incident_id: str) -> bool:
        return await self.session.scalar(select(TeamsIncidentChat.teams_incident_chat_id).where(TeamsIncidentChat.incident_id == incident_id, TeamsIncidentChat.chat_status == "active")) is not None


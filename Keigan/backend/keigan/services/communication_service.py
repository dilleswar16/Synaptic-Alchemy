"""Incident communications (EN/JA drafts, approvals, sending) and blameless postmortems.

Slice S2. Contract methods (job handlers and S4's milestone detection) keep their signatures.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.investigation_ai_caller import InvestigationAiCaller, build_mock_context
from keigan.ai.investigation_ai_schemas import CommunicationDraftSet, PostmortemResult
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.author_labels import mask_author_name
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown, sanitize_ai_model
from keigan.ai.user_facing_errors import describe_failure_for_user
from keigan.config.settings import get_settings
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.incident_dtos import CommunicationDto, CommunicationSendResult, CommunicationUpdateRequest, GenerateCommunicationsRequest, PostmortemDto, PostmortemUpdateRequest
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.incident_entities import (
    ConversationMessage, Incident, IncidentCommunication, Investigation, InvestigationEvidence, InvestigationTimelineEvent, PostmortemReport,
)
from keigan.entities.notification_entities import Stakeholder, TeamsIncidentChat
from keigan.exceptions.keigan_exceptions import BusinessValidationException, KeiganException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue

logger = logging.getLogger(__name__)

SUPPORTED_COMMUNICATION_LANGUAGES = ("en", "ja", "zh-CN", "es", "es-MX", "nl", "fr")
AUDIENCE_BY_TYPE = {"initial_update": "stakeholders", "executive_summary": "executives", "preliminary_report": "stakeholders", "progress_update": "stakeholders", "resolution_update": "stakeholders"}
AskCallable = Callable[..., Awaitable[Any]]


class CommunicationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ══ Communications: generation ════════════════════════════════════════════
    async def generate_communications(
        self, investigation_id: str, communication_types: list[str] | None = None, language_codes: list[str] | None = None, offline_ai: bool = False
    ) -> dict[str, Any] | None:
        """Job handler: draft (or re-draft) communications for an investigation."""
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            return None
        application = await self.session.get(Application, investigation.application_id)
        assert application is not None
        incident = await self.session.get(Incident, investigation.incident_id) if investigation.incident_id else None
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application.application_id))).all())
        evidence_rows = list((await self.session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation_id))).all())
        mock_context = await build_mock_context(investigation, incident, application.application_name, services, evidence_rows)
        mock_context.synthesis = {"executive_summary": investigation.executive_summary, "why_it_happened_markdown": investigation.why_it_happened_markdown, "overall_confidence_score": investigation.overall_confidence_score}
        if incident and incident.resolved_at:
            mock_context.duration_minutes = max(0, int((incident.resolved_at - incident.opened_at).total_seconds() // 60))
        caller = InvestigationAiCaller(application.application_id, application.application_name, application.criticality_tier, investigation_id, investigation.requested_by_user_principal_name, mock_context, offline_ai)
        drafts = await self.draft_investigation_communications(investigation, communication_types or ["progress_update"], language_codes, auto_send=False, ask=caller.ask)
        return {"drafted": len(drafts)}

    async def draft_investigation_communications(
        self, investigation: Investigation, communication_types: list[str], language_codes: list[str] | None, *, auto_send: bool, ask: AskCallable
    ) -> list[IncidentCommunication]:
        application = await self.session.get(Application, investigation.application_id)
        assert application is not None
        incident = await self.session.get(Incident, investigation.incident_id) if investigation.incident_id else None
        stakeholder_languages = list((await self.session.scalars(select(Stakeholder.preferred_language_code).where(Stakeholder.application_id == application.application_id, Stakeholder.is_active.is_(True)))).all())
        languages = [language for language in dict.fromkeys([*(language_codes or ["en", "ja"]), *([] if language_codes else stakeholder_languages)]) if language in SUPPORTED_COMMUNICATION_LANGUAGES]
        # Audience rule: updates go to business and technical stakeholders by email, so the fix steps (commands, resource names) are
        # not given to the writer at all. Engineers read the fix on the investigation page and in the incident's Teams room.
        findings_text = (
            f"Priority: {(incident.keigan_priority if incident else None) or 'P3'}\nExecutive summary: {investigation.executive_summary}\nWhat went wrong: {investigation.what_went_wrong_markdown}\n"
            f"Why it happened: {investigation.why_it_happened_markdown}\nConfidence: {investigation.overall_confidence_score}\n"
            f"Incident opened: {incident.opened_at.isoformat() if incident else 'n/a'}; resolved: {incident.resolved_at.isoformat() if incident and incident.resolved_at else 'not yet'}"
        )
        sections = [
            PromptSection("Application", f"{application.application_name} ({application.application_code}), tier {application.criticality_tier}, primary language {application.primary_locale}"),
            PromptSection("Investigation findings", findings_text, is_untrusted=True, source_label="investigation findings"),
            PromptSection("Requested drafts", f"Types: {', '.join(communication_types)}\nLanguages: {', '.join(languages)}"),
            PromptSection("Task", "Draft every requested type in every requested language."),
        ]
        draft_set: CommunicationDraftSet = await ask("incident_communications", sections, CommunicationDraftSet)
        existing_drafts = (
            await self.session.scalars(
                select(IncidentCommunication).where(
                    IncidentCommunication.investigation_id == investigation.investigation_id, IncidentCommunication.communication_status == "draft",
                    IncidentCommunication.communication_type.in_(communication_types),
                )
            )
        ).all()
        for existing_draft in existing_drafts:
            await self.session.delete(existing_draft)
        created: list[IncidentCommunication] = []
        for draft in draft_set.drafts:
            if draft.communication_type not in communication_types or draft.language_code not in languages:
                continue
            communication = IncidentCommunication(
                incident_id=investigation.incident_id, investigation_id=investigation.investigation_id, communication_type=draft.communication_type,
                audience_type=AUDIENCE_BY_TYPE.get(draft.communication_type, "stakeholders"), language_code=draft.language_code, subject_line=sanitize_ai_line(draft.subject_line),
                body_markdown=sanitize_ai_markdown(draft.body_markdown), communication_status="draft", created_by_user_principal_name="system:keigan",
            )
            self.session.add(communication)
            created.append(communication)
        await self.session.flush()
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=investigation.incident_id, investigation_id=investigation.investigation_id, event_type="communications_drafted",
                event_title=f"Drafted {len(created)} communication(s): {', '.join(dict.fromkeys(communication_types))} in {', '.join(languages)}", event_source="keigan",
            )
        )
        if auto_send and self.settings.auto_send_preliminary_report:
            for communication in created:
                if communication.communication_type == "preliminary_report":
                    communication.communication_status, communication.approved_by_user_principal_name, communication.approved_at = "approved", "system:auto-send", utc_now()
                    await self._deliver(communication, "system:keigan")
        return created

    async def start_generation_job(self, current_user: CurrentUser, investigation_id: str, request: GenerateCommunicationsRequest) -> JobAcceptedResponse:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("The investigation was not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, investigation.application_id)
        if not investigation.investigation_status.startswith("completed"):
            raise BusinessValidationException("Communications can be drafted once the investigation has completed.")
        invalid_languages = [language for language in request.language_codes if language not in SUPPORTED_COMMUNICATION_LANGUAGES]
        if invalid_languages or request.communication_type not in AUDIENCE_BY_TYPE:
            raise BusinessValidationException("Unsupported communication type or language.")
        job_id = await JobQueue(self.session).enqueue(
            "generate_communications", {"investigation_id": investigation_id, "communication_types": [request.communication_type], "language_codes": request.language_codes},
            deduplication_key=f"comms:{investigation_id}:{request.communication_type}", priority_number=30,
        )
        await AuditService(self.session).record(current_user, "communication.generate", target_entity_type="investigation", target_entity_id=investigation_id, application_id=investigation.application_id, action_details={"type": request.communication_type})
        return JobAcceptedResponse(job_id=job_id, status="queued")

    # ══ Communications: read, edit, approve, send ═════════════════════════════
    async def list_communications(self, current_user: CurrentUser, investigation_id: str) -> list[CommunicationDto]:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("The investigation was not found.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, investigation.application_id)
        communications = (await self.session.scalars(select(IncidentCommunication).where(IncidentCommunication.investigation_id == investigation_id).order_by(IncidentCommunication.created_at, IncidentCommunication.communication_type))).all()
        return [CommunicationDto.model_validate(communication) for communication in communications]

    async def _load_communication(self, current_user: CurrentUser, communication_id: str) -> tuple[IncidentCommunication, str]:
        communication = await self.session.get(IncidentCommunication, communication_id)
        if communication is None:
            raise NotFoundException("The communication was not found.")
        investigation = await self.session.get(Investigation, communication.investigation_id) if communication.investigation_id else None
        incident = await self.session.get(Incident, communication.incident_id) if communication.incident_id else None
        application_id = investigation.application_id if investigation else incident.application_id if incident else None
        if application_id is None:
            raise NotFoundException("The communication has no application.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, application_id)
        return communication, application_id

    async def update_communication(self, current_user: CurrentUser, communication_id: str, request: CommunicationUpdateRequest) -> CommunicationDto:
        communication, application_id = await self._load_communication(current_user, communication_id)
        if communication.communication_status == "sent":
            raise BusinessValidationException("A sent communication can no longer be edited.")
        masker = PiiMasker()
        if request.subject_line is not None:
            communication.subject_line = sanitize_ai_line(masker.mask_text(request.subject_line))
        if request.body_markdown is not None:
            communication.body_markdown = sanitize_ai_markdown(masker.mask_text(request.body_markdown))
        communication.communication_status, communication.approved_by_user_principal_name, communication.approved_at = "draft", None, None  # edits need a fresh approval
        communication.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "communication.edit", target_entity_type="incident_communication", target_entity_id=communication_id, application_id=application_id)
        await self.session.flush()
        return CommunicationDto.model_validate(communication)

    async def approve_communication(self, current_user: CurrentUser, communication_id: str) -> CommunicationDto:
        communication, application_id = await self._load_communication(current_user, communication_id)
        if communication.communication_status == "sent":
            raise BusinessValidationException("This communication was already sent.")
        communication.communication_status, communication.approved_by_user_principal_name, communication.approved_at = "approved", current_user.user_principal_name, utc_now()
        await AuditService(self.session).record(current_user, "communication.approve", target_entity_type="incident_communication", target_entity_id=communication_id, application_id=application_id)
        await self.session.flush()
        return CommunicationDto.model_validate(communication)

    async def send_communication(self, current_user: CurrentUser, communication_id: str) -> CommunicationSendResult:
        communication, application_id = await self._load_communication(current_user, communication_id)
        if communication.communication_status == "sent":
            raise BusinessValidationException("This communication was already sent.")
        if communication.communication_status != "approved":
            raise BusinessValidationException("Approve the communication before sending it.")
        deliveries, message = await self._deliver(communication, current_user.user_principal_name)
        await AuditService(self.session).record(current_user, "communication.send", target_entity_type="incident_communication", target_entity_id=communication_id, application_id=application_id, action_details={"deliveries": deliveries})
        await self.session.flush()
        return CommunicationSendResult(communication=CommunicationDto.model_validate(communication), deliveries_queued=deliveries, message=message)

    async def _deliver(self, communication: IncidentCommunication, requested_by: str) -> tuple[int, str]:
        """Hand an approved communication to S4's notification service; keep it approved when delivery is not available yet."""
        from keigan.services.notification_service import NotificationService

        try:
            deliveries = await NotificationService(self.session).send_communication(communication.communication_id, requested_by)
        except NotImplementedError:
            return 0, "Delivery is not enabled in this environment yet. The communication stays approved and can be sent later."
        except KeiganException as delivery_error:
            return 0, f"Delivery could not be queued: {delivery_error.detail}"
        communication.communication_status, communication.sent_at = "sent", utc_now()
        incident = await self.session.get(Incident, communication.incident_id) if communication.incident_id else None
        if incident is not None and incident.first_update_sent_at is None:
            incident.first_update_sent_at = communication.sent_at
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=communication.incident_id, investigation_id=communication.investigation_id, event_type="communication_sent",
                event_title=f"Sent {communication.communication_type.replace('_', ' ')} ({communication.language_code})", event_details_markdown=communication.subject_line, event_source="keigan",
            )
        )
        return deliveries, f"Queued {deliveries} delivery(ies)."

    # ══ Postmortems ═══════════════════════════════════════════════════════════
    async def start_postmortem(self, current_user: CurrentUser, incident_id: str, generation_trigger: str = "user_button") -> JobAcceptedResponse:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundException("The incident was not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, incident.application_id)
        postmortem = await self._postmortem_for_incident(incident_id)
        if postmortem is not None and postmortem.report_status == "final":
            raise BusinessValidationException("The postmortem was finalised. It can no longer be regenerated.")
        if postmortem is None:
            postmortem = PostmortemReport(incident_id=incident_id, report_title=f"Postmortem: {incident.incident_title}", report_status="generating", generation_trigger=generation_trigger, created_by_user_principal_name=current_user.user_principal_name)
            self.session.add(postmortem)
        else:
            postmortem.report_status = "generating"
        await self.session.flush()
        job_id = await JobQueue(self.session).enqueue(
            "generate_postmortem", {"incident_id": incident_id, "generation_trigger": generation_trigger, "requested_by_user_principal_name": current_user.user_principal_name},
            deduplication_key=f"postmortem:{incident_id}", priority_number=30,
        )
        await AuditService(self.session).record(current_user, "postmortem.generate", target_entity_type="incident", target_entity_id=incident_id, application_id=incident.application_id)
        return JobAcceptedResponse(job_id=job_id, status="queued")

    async def _postmortem_for_incident(self, incident_id: str) -> PostmortemReport | None:
        return await self.session.scalar(select(PostmortemReport).where(PostmortemReport.incident_id == incident_id).order_by(PostmortemReport.created_at.desc()).limit(1))

    async def generate_postmortem(self, incident_id: str, generation_trigger: str = "user_button", requested_by_user_principal_name: str | None = None) -> dict[str, Any] | None:
        """Job handler (also used by S4's Teams milestone detection): write the blameless postmortem draft."""
        return await self._write_postmortem(incident_id, generation_trigger, requested_by_user_principal_name, offline_ai=False)

    async def write_postmortem_offline(self, incident_id: str) -> dict[str, Any] | None:
        """Seed helper using the offline mock factories regardless of the configured provider."""
        return await self._write_postmortem(incident_id, "seed", "system:seed", offline_ai=True)

    async def _write_postmortem(self, incident_id: str, generation_trigger: str, requested_by: str | None, offline_ai: bool) -> dict[str, Any] | None:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            return None
        application = await self.session.get(Application, incident.application_id)
        assert application is not None
        postmortem = await self._postmortem_for_incident(incident_id)
        if postmortem is None:
            postmortem = PostmortemReport(incident_id=incident_id, report_title=f"Postmortem: {incident.incident_title}", report_status="generating", generation_trigger=generation_trigger, created_by_user_principal_name=requested_by)
            self.session.add(postmortem)
            await self.session.flush()
        elif postmortem.report_status == "final":
            return {"postmortemId": postmortem.postmortem_id}
        investigation = await self.session.scalar(select(Investigation).where(Investigation.incident_id == incident_id, Investigation.investigation_status.like("completed%")).order_by(Investigation.created_at.desc()).limit(1))
        postmortem.investigation_id = investigation.investigation_id if investigation else None
        masker = PiiMasker()
        timeline_events = (await self.session.scalars(select(InvestigationTimelineEvent).where(InvestigationTimelineEvent.incident_id == incident_id).order_by(InvestigationTimelineEvent.event_occurred_at))).all()
        timeline_lines = [(event.event_occurred_at.strftime("%Y-%m-%d %H:%M UTC"), event.event_title) for event in timeline_events if event.event_type not in ("communications_drafted",)]
        chat_facts = [f"{event.event_occurred_at.strftime('%H:%M')} {event.event_title}" for event in timeline_events if event.event_type == "chat_fact"]
        chat = await self.session.scalar(select(TeamsIncidentChat).where(TeamsIncidentChat.incident_id == incident_id))
        chat_messages = (
            list((await self.session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == chat.conversation_id).order_by(ConversationMessage.created_at).limit(80))).all())
            if chat and chat.conversation_id else []
        )
        sent_communications = (await self.session.scalars(select(IncidentCommunication).where(IncidentCommunication.incident_id == incident_id, IncidentCommunication.communication_status == "sent"))).all()
        resolution_note = next((event.event_details_markdown for event in reversed(timeline_events) if event.event_type == "incident_resolved" and event.event_details_markdown), None)
        sections = [
            PromptSection("Application", f"{application.application_name} ({application.application_code}), tier {application.criticality_tier}"),
            PromptSection("Incident", f"{incident.external_incident_number}: {incident.incident_title}\nPriority {incident.keigan_priority}; opened {incident.opened_at.isoformat()}; resolved {incident.resolved_at.isoformat() if incident.resolved_at else 'not recorded'}\nResolution note: {resolution_note or 'none'}\n{incident.incident_description or ''}", is_untrusted=True, source_label="incident"),
            PromptSection("Investigation", f"{investigation.executive_summary}\n\nWhat went wrong: {investigation.what_went_wrong_markdown}\n\nWhy: {investigation.why_it_happened_markdown}\n\nFix: {investigation.how_to_fix_markdown}" if investigation else "No investigation was completed.", is_untrusted=True, source_label="investigation"),
            PromptSection("Timeline", "\n".join(f"{time_text} {title}" for time_text, title in timeline_lines), is_untrusted=True, source_label="timeline"),
            PromptSection("Facts from the responders' chat", "\n".join(chat_facts) or "None recorded.", is_untrusted=True, source_label="teams chat facts"),
            # Postmortems name roles, not people: author names are replaced by stable placeholders before the model sees them (V12).
            PromptSection("Teams conversation", masker.mask_text("\n".join(f"{mask_author_name(masker, message.author_display_name or message.author_role)}: {message.message_text}" for message in chat_messages)) or "None.", is_untrusted=True, source_label="teams chat"),
            PromptSection("Communications sent", "\n".join(f"{communication.sent_at}: {communication.subject_line}" for communication in sent_communications) or "None sent.", is_untrusted=True, source_label="communications"),
            PromptSection("Task", "Write the blameless postmortem."),
        ]
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application.application_id))).all())
        evidence_rows = list((await self.session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation.investigation_id))).all()) if investigation else []
        mock_context = await build_mock_context(investigation or Investigation(application_id=incident.application_id, investigation_window_start=incident.opened_at - timedelta(hours=1), investigation_window_end=incident.resolved_at or utc_now()), incident, application.application_name, services, evidence_rows)
        if investigation:
            mock_context.synthesis = {"executive_summary": investigation.executive_summary, "why_it_happened_markdown": investigation.why_it_happened_markdown, "overall_confidence_score": investigation.overall_confidence_score}
        mock_context.timeline_lines = timeline_lines
        mock_context.duration_minutes = max(0, int(((incident.resolved_at or utc_now()) - incident.opened_at).total_seconds() // 60))
        caller = InvestigationAiCaller(application.application_id, application.application_name, application.criticality_tier, investigation.investigation_id if investigation else None, requested_by, mock_context, offline_ai)
        try:
            result: PostmortemResult = await caller.ask("postmortem_report", sections, PostmortemResult)
        except KeiganException as ai_error:
            postmortem.report_status = "failed"
            postmortem.report_markdown = f"The postmortem could not be generated: {describe_failure_for_user(ai_error)} Try again later or write it manually."
            return {"postmortemId": postmortem.postmortem_id, "status": "failed"}
        result = sanitize_ai_model(result)
        sections_payload = result.model_dump()
        sections_payload["incident_resolved_at"] = incident.resolved_at.isoformat() if incident.resolved_at else None
        postmortem.report_title = sanitize_ai_line(result.report_title)
        postmortem.report_sections_json = sections_payload
        postmortem.report_markdown = sanitize_ai_markdown(self.render_postmortem_markdown(result, incident))
        postmortem.report_status, postmortem.generation_trigger = "draft", generation_trigger
        self.session.add(InvestigationTimelineEvent(incident_id=incident_id, investigation_id=postmortem.investigation_id, event_type="postmortem_drafted", event_title="Postmortem draft prepared", event_source="keigan"))
        return {"postmortemId": postmortem.postmortem_id}

    @staticmethod
    def render_postmortem_markdown(result: PostmortemResult, incident: Incident) -> str:
        due_base = incident.resolved_at or utc_now()
        bullet = lambda items: "\n".join(f"- {item}" for item in items) or "- None recorded."  # noqa: E731
        timeline_table = "| Time | Event |\n|---|---|\n" + "\n".join(f"| {entry.time_text} | {entry.description} |" for entry in result.timeline) if result.timeline else "No timeline entries recorded."
        action_table = "| Action | Owner | Due | Type |\n|---|---|---|---|\n" + "\n".join(
            f"| {item.description} | {item.owner_role} | {(due_base + timedelta(days=item.due_in_days)).strftime('%Y-%m-%d')} | {item.action_type} |" for item in result.action_items
        ) if result.action_items else "No action items recorded."
        return (
            f"# {result.report_title}\n\n## Summary\n{result.summary}\n\n## Impact\n{result.impact}\n\n## Timeline\n{timeline_table}\n\n## Root cause\n{result.root_cause}\n\n"
            f"## Contributing factors\n{bullet(result.contributing_factors)}\n\n## Detection\n{result.detection}\n\n## Response\n{result.response}\n\n## What went well\n{bullet(result.what_went_well)}\n\n"
            f"## What could be improved\n{bullet(result.what_could_be_improved)}\n\n## Action items\n{action_table}\n\n## Lessons learned\n{bullet(result.lessons_learned)}\n"
        )

    async def get_postmortem(self, current_user: CurrentUser, incident_id: str) -> PostmortemDto | None:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundException("The incident was not found.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, incident.application_id)
        postmortem = await self._postmortem_for_incident(incident_id)
        return self._postmortem_dto(postmortem) if postmortem else None

    @staticmethod
    def _postmortem_dto(postmortem: PostmortemReport) -> PostmortemDto:
        return PostmortemDto(
            postmortem_id=postmortem.postmortem_id, incident_id=postmortem.incident_id, investigation_id=postmortem.investigation_id, report_title=postmortem.report_title,
            report_markdown=postmortem.report_markdown, report_sections=postmortem.report_sections_json, language_code=postmortem.language_code, report_status=postmortem.report_status,
            generation_trigger=postmortem.generation_trigger, finalized_by_user_principal_name=postmortem.finalized_by_user_principal_name, finalized_at=postmortem.finalized_at,
            sent_at=postmortem.sent_at, created_at=postmortem.created_at, updated_at=postmortem.updated_at,
        )

    async def _load_postmortem_for_admin(self, current_user: CurrentUser, postmortem_id: str) -> tuple[PostmortemReport, str]:
        postmortem = await self.session.get(PostmortemReport, postmortem_id)
        incident = await self.session.get(Incident, postmortem.incident_id) if postmortem else None
        if postmortem is None or incident is None:
            raise NotFoundException("The postmortem was not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, incident.application_id)
        return postmortem, incident.application_id

    async def update_postmortem(self, current_user: CurrentUser, postmortem_id: str, request: PostmortemUpdateRequest) -> PostmortemDto:
        postmortem, application_id = await self._load_postmortem_for_admin(current_user, postmortem_id)
        if postmortem.report_status == "final":
            raise BusinessValidationException("A finalised postmortem cannot be edited.")
        if postmortem.report_status == "generating":
            raise BusinessValidationException("The postmortem is still being generated.")
        if request.report_title is not None:
            postmortem.report_title = sanitize_ai_line(PiiMasker().mask_text(request.report_title))
        if request.report_markdown is not None:
            postmortem.report_markdown = sanitize_ai_markdown(PiiMasker().mask_text(request.report_markdown))
        postmortem.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "postmortem.edit", target_entity_type="postmortem_report", target_entity_id=postmortem_id, application_id=application_id)
        await self.session.flush()
        return self._postmortem_dto(postmortem)

    async def finalize_postmortem(self, current_user: CurrentUser, postmortem_id: str) -> PostmortemDto:
        postmortem, application_id = await self._load_postmortem_for_admin(current_user, postmortem_id)
        if postmortem.report_status not in ("draft",):
            raise BusinessValidationException("Only a draft postmortem can be finalised.")
        postmortem.report_status, postmortem.finalized_by_user_principal_name, postmortem.finalized_at = "final", current_user.user_principal_name, utc_now()
        await AuditService(self.session).record(current_user, "postmortem.finalize", target_entity_type="postmortem_report", target_entity_id=postmortem_id, application_id=application_id)
        await self.session.flush()
        return self._postmortem_dto(postmortem)

    async def send_postmortem(self, current_user: CurrentUser, postmortem_id: str) -> CommunicationSendResult | dict[str, Any]:
        from keigan.services.notification_service import NotificationService

        postmortem, application_id = await self._load_postmortem_for_admin(current_user, postmortem_id)
        if postmortem.report_status != "final":
            raise BusinessValidationException("Finalise the postmortem before sending it.")
        try:
            deliveries = await NotificationService(self.session).send_postmortem(postmortem_id, current_user.user_principal_name)
        except NotImplementedError:
            return {"postmortem": self._postmortem_dto(postmortem).model_dump(by_alias=True, mode="json"), "deliveriesQueued": 0, "message": "Delivery is not enabled in this environment yet. The postmortem stays finalised and can be sent later."}
        postmortem.sent_at = utc_now()
        await AuditService(self.session).record(current_user, "postmortem.send", target_entity_type="postmortem_report", target_entity_id=postmortem_id, application_id=application_id, action_details={"deliveries": deliveries})
        await self.session.flush()
        return {"postmortem": self._postmortem_dto(postmortem).model_dump(by_alias=True, mode="json"), "deliveriesQueued": deliveries, "message": f"Queued {deliveries} delivery(ies)."}

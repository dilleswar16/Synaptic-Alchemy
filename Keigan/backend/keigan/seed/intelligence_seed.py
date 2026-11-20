"""Predictive signals (detectors over the seeded world), intelligence reports, outbox history and a simulated Teams incident chat. Idempotent."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Conversation, ConversationMessage, Incident, IncidentCommunication, Investigation, InvestigationTimelineEvent
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder, TeamsIncidentChat
from keigan.entities.platform_entities import BackgroundJob
from keigan.entities.slo_entities import IntelligenceReport, PredictiveSignal
from keigan.seed.foundation_seed import SeedContext
from keigan.services.intelligence_service import IntelligenceService
from keigan.services.notification_service import NotificationService
from keigan.services.notification_renderer import translate
from keigan.services.teams_chat_service import KEIGAN_DISPLAY_NAME, TeamsChatService
from keigan.utils.time_utils import utc_now

SEED_ORDER = 40
logger = logging.getLogger(__name__)
REPORT_APPLICATION_CODES = ("CLMJP", "CHAD")


async def _seed_signals_and_reports(session: AsyncSession, seed_context: SeedContext) -> None:
    intelligence_service = IntelligenceService(session)
    for application_code, application_id in seed_context.application_ids_by_code.items():
        if await session.scalar(select(func.count()).select_from(PredictiveSignal).where(PredictiveSignal.application_id == application_id)):
            continue
        outcome = await intelligence_service.run_detectors_for_application(application_id)
        logger.info("Seeded predictive signals for %s: %s", application_code, outcome)
    await session.flush()
    for application_code in REPORT_APPLICATION_CODES:
        application_id = seed_context.application_ids_by_code.get(application_code)
        if application_id is None or await session.scalar(select(func.count()).select_from(IntelligenceReport).where(IntelligenceReport.application_id == application_id)):
            continue
        application = await session.get(Application, application_id)
        weekly_report = await intelligence_service._build_report(application, "weekly_digest", None, period_end=utc_now() - timedelta(days=1))
        weekly_report.created_at = weekly_report.report_period_end
        await intelligence_service._send_report(application, weekly_report)
        open_signal_ids = list((await session.scalars(select(PredictiveSignal.predictive_signal_id).where(PredictiveSignal.application_id == application_id, PredictiveSignal.signal_status == "open").order_by(PredictiveSignal.confidence_score.desc()).limit(3))).all())
        if open_signal_ids:
            alert_report = await intelligence_service._build_report(application, "proactive_alert", open_signal_ids)
            await intelligence_service._send_report(application, alert_report)
    # Seeded emails count as already delivered (simulated); drop the queued jobs that would deliver or regenerate them.
    await session.execute(update(NotificationDelivery).where(NotificationDelivery.delivery_status == "pending").values(delivery_status="simulated", attempt_count=1, sent_at=utc_now()))
    await session.execute(delete(BackgroundJob).where(BackgroundJob.job_type.in_(("deliver_notification", "send_intelligence_report")), BackgroundJob.job_status == "queued"))


async def _seed_communication_outbox(session: AsyncSession) -> None:
    """Historical communications were 'sent' by the incident seed; give them outbox rows so the outbox page and the room look real."""
    communications = (await session.scalars(select(IncidentCommunication).where(IncidentCommunication.communication_status == "sent"))).all()
    notification_service = NotificationService(session)
    for communication in communications:
        if communication.incident_id is None or await session.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.incident_id == communication.incident_id, NotificationDelivery.subject_line == communication.subject_line)):
            continue
        incident = await session.get(Incident, communication.incident_id)
        if incident is None:
            continue
        application_name = await notification_service._application_name(incident.application_id)
        notification_type = "preliminary_report" if communication.communication_type == "preliminary_report" else "progress_update"
        for stakeholder in await notification_service.matching_stakeholders(incident.application_id, notification_type, "email", priority=incident.keigan_priority or "P3", service_ids=incident.affected_service_ids):
            recipient_language = stakeholder.preferred_language_code.split("-")[0]
            if recipient_language != communication.language_code.split("-")[0] and not (communication.language_code == "en" and recipient_language not in ("en", "ja")):
                continue
            rendered = notification_service.renderer.render_email(
                "progress_update", communication.language_code, application_name, incident.incident_title, facts=[(translate(communication.language_code, "labels.incident"), incident.external_incident_number or "")],
                body_markdown=communication.body_markdown, action_path=f"/incidents/{incident.incident_id}", subject_override=communication.subject_line, priority=incident.keigan_priority or "P3",
            )
            session.add(NotificationDelivery(
                application_id=incident.application_id, incident_id=incident.incident_id, notification_type=notification_type, delivery_channel="email", recipient_address=stakeholder.email_address or stakeholder.display_name,
                subject_line=rendered.subject_line, body_html=rendered.body_html, body_text=rendered.body_text, delivery_status="simulated", attempt_count=1, created_at=communication.sent_at or utc_now(), sent_at=communication.sent_at,
            ))
    await session.flush()


async def _seed_simulated_chat(session: AsyncSession, seed_context: SeedContext) -> None:
    application_id = seed_context.application_ids_by_code.get("CLMJP")
    if application_id is None:
        return
    incident = await session.scalar(select(Incident).where(Incident.application_id == application_id, Incident.incident_status.in_(("resolved", "closed"))).order_by(Incident.opened_at.desc()).limit(1))
    if incident is None or await session.scalar(select(TeamsIncidentChat.teams_incident_chat_id).where(TeamsIncidentChat.incident_id == incident.incident_id)):
        return
    chat_service = TeamsChatService(session)
    await chat_service.create_incident_chat(incident.incident_id)
    chat = await session.scalar(select(TeamsIncidentChat).where(TeamsIncidentChat.incident_id == incident.incident_id))
    if chat is None:
        return
    investigation = await session.scalar(select(Investigation).where(Investigation.incident_id == incident.incident_id).order_by(Investigation.created_at.desc()).limit(1))
    base_time = incident.opened_at
    existing_messages = (await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == chat.conversation_id).order_by(ConversationMessage.created_at))).all()
    for offset, message in enumerate(existing_messages):
        message.created_at = base_time + timedelta(minutes=8, seconds=offset * 20)
    members = {stakeholder.display_name: stakeholder.user_principal_name for stakeholder in (await session.scalars(select(Stakeholder).where(Stakeholder.application_id == application_id))).all()}
    aiko, rui = ("Aiko AppAdmin", members.get("Aiko AppAdmin")), ("Rui Reader", members.get("Rui Reader"))
    script: list[tuple[int, str, tuple[str, str | None] | None, str]] = [
        (10, "teams_participant", aiko, "調査結果を確認しました。接続プールの枯渇が原因のようです。デプロイ直後から増えていますね。"),
        (11, "teams_participant", rui, "Keigan, what changed in the last hour?"),
        (11, "assistant", None, TeamsChatService._fallback_answer(investigation)),
        (16, "teams_participant", rui, "I restarted the claims-api pods and increased the connection pool size to 200."),
        (19, "teams_participant", aiko, "再起動後、エラー率が下がりました。顧客への影響も解消しています。"),
        (22, "teams_participant", rui, "Keigan, this is finished"),
        (22, "assistant", None, translate("en", "chat.milestone_ack")),
    ]
    last_participant_message: ConversationMessage | None = None
    for minutes, role, author, text in script:
        message = ConversationMessage(
            conversation_id=chat.conversation_id, author_role=role, author_display_name=author[0] if author else KEIGAN_DISPLAY_NAME, author_user_principal_name=author[1] if author else None, message_text=text,
            created_at=base_time + timedelta(minutes=minutes, seconds=5 if role == "assistant" else 0),
        )
        session.add(message)
        last_participant_message = message if role == "teams_participant" else last_participant_message
    await session.flush()
    chat.last_processed_message_identifier = last_participant_message.message_id if last_participant_message else None
    for minutes, title, details, actor in (
        (16, "Rui restarted the claims-api pods and raised the connection pool size to 200", "Captured from the incident chat.", "Rui Reader"),
        (19, "Aiko confirmed the error rate dropped after the restart and customer impact ended", "Captured from the incident chat.", "Aiko AppAdmin"),
    ):
        session.add(InvestigationTimelineEvent(
            incident_id=incident.incident_id, investigation_id=investigation.investigation_id if investigation else None, event_occurred_at=base_time + timedelta(minutes=minutes), event_type="chat_fact", event_title=title,
            event_details_markdown=details, event_source="teams_chat", source_reference=chat.teams_incident_chat_id, actor_display_name=actor,
        ))
    conversation = await session.get(Conversation, chat.conversation_id)
    if conversation is not None:
        conversation.created_at = base_time + timedelta(minutes=8)
    await session.flush()


async def seed(session: AsyncSession, seed_context: SeedContext) -> None:
    for step in (lambda: _seed_signals_and_reports(session, seed_context), lambda: _seed_communication_outbox(session), lambda: _seed_simulated_chat(session, seed_context)):
        try:
            async with session.begin_nested():
                await step()
        except Exception:  # noqa: BLE001 - one part must not block the others
            logger.exception("An S4 seed part failed")

"""Teams incident chats: creation, Keigan posts, polling, milestone phrases, questions to Keigan and chat-fact extraction.

Live mode uses Microsoft Graph (create chat, install the bot, read messages through the RSC permission) and the Bot Framework
(proactive posts). Simulated mode mirrors the chat in ``conversation``/``conversation_message`` so the demo works offline.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.author_labels import AuthorAliases
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.ai.notification_ai_schemas import TeamsChatDigestResult, deterministic_chat_facts
from keigan.config import application_context
from keigan.config.settings import IntegrationMode, get_settings
from keigan.dtos.notification_dtos import TeamsChatFactResponse, TeamsChatMessageResponse, TeamsChatParticipant, TeamsChatResponse
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Conversation, ConversationMessage, Incident, Investigation, InvestigationTimelineEvent
from keigan.entities.notification_entities import Stakeholder, TeamsIncidentChat
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, IntegrationException, KeiganException, NotFoundException
from keigan.integrations.bot_framework_client import BotFrameworkClient
from keigan.integrations.microsoft_graph_client import MicrosoftGraphClient
from keigan.security.current_user import CurrentUser
from keigan.services.notification_renderer import NotificationRenderer, translate
from keigan.services.teams_sender_authorizer import TeamsSenderAuthorizer
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
CHAT_SCOPE = "teams_incident_chat"
KEIGAN_DISPLAY_NAME = "Keigan"
MENTION_PATTERN = re.compile(r"^\s*(@keigan|keigan)\b[\s,:：、-]*", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
DEFAULT_BOT_SERVICE_URL = "https://smba.trafficmanager.net/teams/"
NOT_AUTHORIZED_REPLY = "I can only answer people who have access to this application in Keigan. Ask the application's admin to add you to its reader group."


def is_message_for_keigan(message_text: str) -> bool:
    lowered = message_text.lower()
    return bool(MENTION_PATTERN.match(message_text)) or "@keigan" in lowered


def strip_keigan_address(message_text: str) -> str:
    without_markup = re.sub(r"<at>.*?</at>", "", message_text, flags=re.IGNORECASE)
    without_mention = re.sub(r"@keigan", "", without_markup, flags=re.IGNORECASE)
    return MENTION_PATTERN.sub("", without_mention, count=1).strip() or without_mention.strip()


class TeamsChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.renderer = NotificationRenderer()

    @property
    def is_live(self) -> bool:
        return self.settings.teams_mode == IntegrationMode.LIVE

    # ── Lookups ────────────────────────────────────────────────────────────────
    async def _chat_for_incident(self, incident_id: str) -> TeamsIncidentChat | None:
        return await self.session.scalar(select(TeamsIncidentChat).where(TeamsIncidentChat.incident_id == incident_id))

    async def _latest_investigation(self, incident_id: str) -> Investigation | None:
        return await self.session.scalar(select(Investigation).where(Investigation.incident_id == incident_id).order_by(Investigation.created_at.desc()).limit(1))

    async def _chat_stakeholders(self, incident: Incident) -> list[Stakeholder]:
        from keigan.services.notification_service import NotificationService

        return await NotificationService(self.session).matching_stakeholders(incident.application_id, "incident_detected", "teams_incident_chat", priority=incident.keigan_priority or "P3", service_ids=incident.affected_service_ids_json)

    # ── Creation ───────────────────────────────────────────────────────────────
    async def create_incident_chat(self, incident_id: str) -> dict[str, Any] | None:
        incident = await self.session.get(Incident, incident_id)
        if incident is None or self.settings.teams_mode == IntegrationMode.DISABLED:
            return None
        existing_chat = await self._chat_for_incident(incident_id)
        if existing_chat is not None:
            return {"chatId": existing_chat.teams_incident_chat_id, "created": False}
        stakeholders = await self._chat_stakeholders(incident)
        if not stakeholders:
            return {"created": False, "reason": "no chat-subscribed stakeholders"}
        topic = f"[{incident.keigan_priority or 'P3'}] {incident.external_incident_number or ''} {incident.incident_title}".replace("  ", " ").strip()[:250]
        member_names = sorted({stakeholder.user_principal_name or stakeholder.email_address or stakeholder.display_name for stakeholder in stakeholders})
        chat_web_url, conversation_reference = None, None
        if self.is_live:
            chat_identifier, chat_web_url = await self._create_live_chat(topic, stakeholders)
        else:
            chat_identifier = f"simulated:{uuid.uuid4()}"
        investigation = await self._latest_investigation(incident_id)
        conversation = Conversation(
            conversation_scope=CHAT_SCOPE, application_ids_json=[incident.application_id], incident_id=incident_id, investigation_id=investigation.investigation_id if investigation else None,
            owner_user_principal_name=None, conversation_title=topic[:300], created_by_user_principal_name="system:worker", updated_by_user_principal_name="system:worker",
        )
        self.session.add(conversation)
        await self.session.flush()
        chat = TeamsIncidentChat(
            incident_id=incident_id, application_id=incident.application_id, teams_chat_identifier=chat_identifier, bot_conversation_reference_json=conversation_reference, chat_topic=topic,
            chat_web_url=chat_web_url, member_user_principal_names_json=member_names, conversation_id=conversation.conversation_id, last_polled_at=utc_now(),
        )
        self.session.add(chat)
        await self.session.flush()
        application = await self.session.get(Application, incident.application_id)
        language = application.primary_locale if application else "en"
        await self._post_keigan_message(chat, translate(language, "chat.welcome"), None, notification_type="incident_detected")
        if investigation is not None and investigation.investigation_status.startswith("completed"):
            card = self.renderer.render_card(
                "preliminary_report", language, "preliminary_report", incident.incident_title, investigation.executive_summary or "",
                [("Incident", incident.external_incident_number or ""), ("Priority", incident.keigan_priority or "")], f"/incidents/{incident_id}",
            )
            await self._post_keigan_message(chat, investigation.executive_summary or incident.incident_title, card, notification_type="preliminary_report")
        return {"chatId": chat.teams_incident_chat_id, "created": True, "simulated": not self.is_live}

    async def _create_live_chat(self, topic: str, stakeholders: list[Stakeholder]) -> tuple[str, str | None]:
        graph_client = MicrosoftGraphClient(application_context.azure_credential_provider())
        object_ids: list[str] = []
        for stakeholder in stakeholders:
            object_id = stakeholder.entra_object_id
            if not object_id and stakeholder.user_principal_name:
                directory_user = await graph_client.get_user_by_principal_name(stakeholder.user_principal_name)
                object_id = directory_user.get("id") if directory_user else None
            if object_id:
                object_ids.append(object_id)
        if len(object_ids) < 2:
            raise IntegrationException("A Teams group chat needs at least two members with Entra object ids.", error_code="teams_chat_members_missing")
        chat = await graph_client.create_group_chat(topic, sorted(set(object_ids)))
        if self.settings.teams_app_catalog_id:
            try:
                await graph_client.install_app_in_chat(chat["id"], self.settings.teams_app_catalog_id)
            except IntegrationException:
                logger.warning("Could not install the Keigan app in chat %s; the bot cannot post until it is installed.", chat["id"])
        return chat["id"], chat.get("webUrl")

    # ── Posting ────────────────────────────────────────────────────────────────
    async def post_card_if_chat_exists(self, incident_id: str, subject_text: str, message_markdown: str, adaptive_card: dict[str, Any] | None) -> bool:
        chat = await self._chat_for_incident(incident_id)
        if chat is None or chat.chat_status != "active":
            return False
        message_text = message_markdown or subject_text
        already_posted = await self.session.scalar(
            select(func.count()).select_from(ConversationMessage).where(
                ConversationMessage.conversation_id == chat.conversation_id, ConversationMessage.author_role == "assistant",
                ConversationMessage.message_text == self._outgoing_text(message_text),
            )
        )
        if already_posted:  # chat creation may already have posted this report (alerts often arrive before the ticket)
            return False
        await self._post_keigan_message(chat, message_text, adaptive_card, notification_type="progress_update")
        return True

    @staticmethod
    def _outgoing_text(message_text: str) -> str:
        """Everything Keigan posts into a chat is masked and sanitised (no links to other hosts, no images, no HTML), whoever wrote it (V8)."""
        return sanitize_ai_markdown(PiiMasker().mask_text(message_text))

    async def _post_keigan_message(self, chat: TeamsIncidentChat, message_text: str, adaptive_card: dict[str, Any] | None, *, notification_type: str = "progress_update") -> None:
        from keigan.services.notification_service import NotificationService

        masked_text = self._outgoing_text(message_text)
        self.session.add(ConversationMessage(
            conversation_id=chat.conversation_id, author_role="assistant", author_display_name=KEIGAN_DISPLAY_NAME, message_text=masked_text, message_payload_json={"adaptiveCard": adaptive_card} if adaptive_card else None,
        ))
        status, error_message = "simulated", None
        if self.is_live:
            try:
                await self._send_live_activity(chat, masked_text, adaptive_card)
                status = "sent"
            except IntegrationException as send_error:
                status, error_message = "failed", send_error.detail
        await NotificationService(self.session).record_chat_delivery(chat.application_id, chat.incident_id, notification_type, chat.teams_chat_identifier, masked_text.splitlines()[0] if masked_text else "Keigan message", masked_text, status, error_message)
        await self.session.flush()

    async def _send_live_activity(self, chat: TeamsIncidentChat, message_text: str, adaptive_card: dict[str, Any] | None) -> None:
        reference = chat.bot_conversation_reference_json or {}
        service_url = reference.get("serviceUrl") or DEFAULT_BOT_SERVICE_URL
        activity: dict[str, Any] = {"type": "message", "text": message_text}
        if adaptive_card:
            activity["attachments"] = [{"contentType": "application/vnd.microsoft.card.adaptive", "content": adaptive_card}]
        await BotFrameworkClient(self.settings, application_context.secret_store()).send_activity(service_url, reference.get("conversationId") or chat.teams_chat_identifier, activity)

    async def send_to_channel(self, recipient_address: str, subject_line: str, body_text: str) -> str | None:
        team_identifier, _, channel_identifier = recipient_address.partition("/")
        activity = {"type": "message", "text": f"**{subject_line}**\n\n{body_text}"}
        return await BotFrameworkClient(self.settings, application_context.secret_store()).send_activity(DEFAULT_BOT_SERVICE_URL, channel_identifier or team_identifier, activity)

    # ── Read model for the UI ──────────────────────────────────────────────────
    async def get_chat_view(self, incident_id: str) -> TeamsChatResponse:
        chat = await self._chat_for_incident(incident_id)
        if chat is None:
            return TeamsChatResponse(incident_id=incident_id, chat_exists=False, is_simulated=not self.is_live)
        is_simulated = chat.teams_chat_identifier.startswith("simulated:")
        message_rows = (await self.session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == chat.conversation_id).order_by(ConversationMessage.created_at, ConversationMessage.message_id))).all()
        messages = [
            TeamsChatMessageResponse(
                message_id=row.message_id, author_role=row.author_role, author_display_name=row.author_display_name, author_user_principal_name=row.author_user_principal_name, message_text=row.message_text,
                adaptive_card=(row.message_payload_json or {}).get("adaptiveCard"), created_at=row.created_at,
            ) for row in message_rows
        ]
        fact_rows = (await self.session.scalars(select(InvestigationTimelineEvent).where(InvestigationTimelineEvent.incident_id == incident_id, InvestigationTimelineEvent.event_type == "chat_fact").order_by(InvestigationTimelineEvent.event_occurred_at))).all()
        stakeholder_names = {(row.user_principal_name or row.email_address or "").lower(): row.display_name for row in (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == chat.application_id))).all()}
        participants = [TeamsChatParticipant(display_name=stakeholder_names.get(name.lower(), name), user_principal_name=name) for name in (chat.member_user_principal_names_json or [])]
        participants.append(TeamsChatParticipant(display_name=KEIGAN_DISPLAY_NAME, role="bot"))
        return TeamsChatResponse(
            incident_id=incident_id, chat_exists=True, is_simulated=is_simulated, chat_topic=chat.chat_topic, chat_web_url=chat.chat_web_url, chat_status=chat.chat_status, participants=participants, messages=messages,
            facts=[TeamsChatFactResponse(timeline_event_id=row.timeline_event_id, event_title=row.event_title, event_details_markdown=row.event_details_markdown, event_occurred_at=row.event_occurred_at, actor_display_name=row.actor_display_name) for row in fact_rows],
            can_post=is_simulated and chat.chat_status == "active",
        )

    async def post_user_message(self, incident_id: str, current_user: CurrentUser, message_text: str) -> TeamsChatResponse:
        chat = await self._chat_for_incident(incident_id)
        if chat is None:
            raise NotFoundException("This incident has no Teams chat yet.")
        if not chat.teams_chat_identifier.startswith("simulated:"):
            raise BusinessValidationException("Messages can only be posted from Keigan in the simulated Teams mode. Write in Teams instead.")
        masked_text = PiiMasker().mask_text(message_text)
        message = ConversationMessage(
            conversation_id=chat.conversation_id, author_role="teams_participant", author_display_name=current_user.display_name, author_user_principal_name=current_user.user_principal_name, message_text=masked_text,
        )
        self.session.add(message)
        await self.session.flush()
        members = set(chat.member_user_principal_names_json or [])
        if current_user.user_principal_name not in members:
            chat.member_user_principal_names_json = sorted(members | {current_user.user_principal_name})
        await self._process_messages(chat, [(current_user.display_name, current_user.user_principal_name, masked_text, message.message_id)], authenticated_user=current_user)
        chat.last_processed_message_identifier = message.message_id
        await self.session.flush()
        return await self.get_chat_view(incident_id)

    # ── Polling and processing ─────────────────────────────────────────────────
    async def poll_incident_chat(self, teams_incident_chat_id: str) -> dict[str, Any] | None:
        chat = await self.session.get(TeamsIncidentChat, teams_incident_chat_id)
        if chat is None or chat.chat_status != "active":
            return None
        incident = await self.session.get(Incident, chat.incident_id)
        if incident is not None and incident.incident_status in ("closed",) and incident.closed_at and incident.closed_at < utc_now() - timedelta(hours=24):
            chat.chat_status = "closed"
            return {"closed": True}
        incoming: list[tuple[str, str | None, str, str]] = []
        if chat.teams_chat_identifier.startswith("simulated:"):
            incoming = await self._unprocessed_simulated_messages(chat)
        elif self.is_live:
            incoming = await self._fetch_live_messages(chat)
        chat.last_polled_at = utc_now()
        if incoming:
            await self._process_messages(chat, incoming)
        await self.session.flush()
        return {"processed": len(incoming)}

    async def _unprocessed_simulated_messages(self, chat: TeamsIncidentChat) -> list[tuple[str, str | None, str, str]]:
        conditions = [ConversationMessage.conversation_id == chat.conversation_id, ConversationMessage.author_role == "teams_participant"]
        if chat.last_processed_message_identifier:
            last_message = await self.session.get(ConversationMessage, chat.last_processed_message_identifier)
            if last_message is not None:
                conditions.append(ConversationMessage.created_at > last_message.created_at)
        rows = (await self.session.scalars(select(ConversationMessage).where(*conditions).order_by(ConversationMessage.created_at))).all()
        if rows:
            chat.last_processed_message_identifier = rows[-1].message_id
        return [(row.author_display_name or "Participant", row.author_user_principal_name, row.message_text, row.message_id) for row in rows]

    async def _fetch_live_messages(self, chat: TeamsIncidentChat) -> list[tuple[str, str | None, str, str]]:
        graph_messages = await MicrosoftGraphClient(application_context.azure_credential_provider()).list_chat_messages_since(chat.teams_chat_identifier, chat.last_polled_at)
        known_identifiers = set((await self.session.scalars(select(ConversationMessage.external_message_identifier).where(ConversationMessage.conversation_id == chat.conversation_id, ConversationMessage.external_message_identifier.is_not(None)))).all())
        masker = PiiMasker()
        incoming: list[tuple[str, str | None, str, str]] = []
        for graph_message in graph_messages:
            message_identifier = graph_message.get("id", "")
            sender = (graph_message.get("from") or {}).get("user")
            if message_identifier in known_identifiers or not sender or graph_message.get("messageType") != "message":
                continue
            if not (await TeamsSenderAuthorizer(self.session).access_for(chat.application_id, sender.get("id"), sender.get("displayName"))).can_read:
                chat.last_processed_message_identifier = message_identifier  # not kept and not processed: only people who may read the application are heard (V13)
                continue
            plain_text = HTML_TAG_PATTERN.sub(" ", (graph_message.get("body") or {}).get("content", "")).strip()
            masked_text = masker.mask_text(plain_text)
            row = ConversationMessage(
                conversation_id=chat.conversation_id, author_role="teams_participant", author_display_name=sender.get("displayName"), message_text=masked_text, external_message_identifier=message_identifier,
                created_at=self._parse_graph_time(graph_message.get("createdDateTime")),
            )
            self.session.add(row)
            await self.session.flush()
            chat.last_processed_message_identifier = message_identifier
            incoming.append((sender.get("displayName") or "Participant", sender.get("id"), masked_text, row.message_id))
        return incoming

    @staticmethod
    def _parse_graph_time(value: str | None) -> datetime:
        try:
            return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return utc_now()

    async def _process_messages(
        self, chat: TeamsIncidentChat, messages: list[tuple[str, str | None, str, str]], authenticated_user: CurrentUser | None = None
    ) -> None:
        """Milestone phrase → postmortem; question to Keigan → answer; everything else → digest into chat facts.

        Only people who may read the application are heard (V13): messages of anyone else are ignored, and a person who addresses Keigan is told why.
        """
        incident = await self.session.get(Incident, chat.incident_id)
        investigation = await self._latest_investigation(chat.incident_id)
        application = await self.session.get(Application, chat.application_id)
        language = application.primary_locale if application else "en"
        author_aliases = AuthorAliases(PiiMasker())
        digest_lines: list[str] = []
        for author_name, author_identity, message_text, message_identifier in messages:
            access = await TeamsSenderAuthorizer(self.session).access_for(chat.application_id, author_identity, author_name, authenticated_user)
            if not access.can_read:
                logger.info("Ignored a Teams message from a sender without access to application %s", chat.application_id)
                if is_message_for_keigan(message_text):
                    await self._post_keigan_message(chat, NOT_AUTHORIZED_REPLY, None)
                continue
            lowered = message_text.lower().strip()
            if any(phrase in lowered for phrase in self.settings.teams_milestone_phrase_list):
                await self._handle_milestone(chat, author_name, author_identity, language)
            elif is_message_for_keigan(message_text):
                await self._answer_question(chat, investigation, author_name, author_identity, strip_keigan_address(message_text), allow_log_queries=access.is_application_admin)
            else:
                digest_lines.append(f"{author_aliases.alias(author_name)}: {message_text}")
        if digest_lines and incident is not None:
            await self._digest_messages(chat, incident, investigation, digest_lines, author_aliases)

    async def _handle_milestone(self, chat: TeamsIncidentChat, author_name: str, author_upn: str | None, language: str) -> None:
        from keigan.workers.job_queue import JobQueue

        await JobQueue(self.session).enqueue(
            "generate_postmortem", {"incident_id": chat.incident_id, "generation_trigger": "teams_phrase", "requested_by_user_principal_name": author_upn}, deduplication_key=f"postmortem:{chat.incident_id}:teams",
        )
        self.session.add(InvestigationTimelineEvent(  # the title names a role, not the person (the name is kept separately for the UI)
            incident_id=chat.incident_id, event_type="action_taken", event_title="A responder declared the incident finished in Teams", event_source="teams_chat", actor_display_name=author_name,
        ))
        await self._post_keigan_message(chat, translate(language, "chat.milestone_ack"), None)

    async def _answer_question(
        self, chat: TeamsIncidentChat, investigation: Investigation | None, author_name: str, author_upn: str | None, question_text: str, *, allow_log_queries: bool = False
    ) -> None:
        """``allow_log_queries`` is true only for application admins: a log query runs with Keigan's identity and returns sample rows into the chat."""
        answer_text = None
        if investigation is not None and question_text:
            try:
                from keigan.services.chat_service import ChatService

                answer = await ChatService(self.session).answer_investigation_question(
                    investigation.investigation_id, question_text, asked_by_user_principal_name=author_upn, asked_by_display_name=author_name, allow_log_queries=allow_log_queries
                )
                answer_text = answer.answer_markdown
            except (NotImplementedError, KeiganException):
                answer_text = None
            except Exception:  # noqa: BLE001 - a chat answer must never break the poller
                logger.exception("Answering a Teams question failed")
        if not answer_text:
            answer_text = self._fallback_answer(investigation)
        await self._post_keigan_message(chat, answer_text, None)

    @staticmethod
    def _fallback_answer(investigation: Investigation | None) -> str:
        if investigation is None or not investigation.executive_summary:
            return translate(None, "chat.no_answer")
        parts = [f"Here is what the investigation currently says:\n\n{investigation.executive_summary}"]
        if investigation.how_to_fix_markdown:
            parts.append(f"**Suggested fix**\n{investigation.how_to_fix_markdown}")
        return "\n\n".join(parts)

    async def _digest_messages(
        self, chat: TeamsIncidentChat, incident: Incident, investigation: Investigation | None, message_lines: list[str], author_aliases: AuthorAliases
    ) -> None:
        """``message_lines`` already carry author placeholders instead of names; the names are restored only for the timeline shown to responders."""
        digest: TeamsChatDigestResult
        application = await self.session.get(Application, incident.application_id)
        try:
            gateway = application_context.llm_gateway()
            system_prompt = application_context.prompt_library().render("teams_chat_digest", application_name=application.application_name if application else "the application")
            digest = await gateway.generate_structured(
                feature_name="teams_chat_digest", model_tier=ModelTier.FAST, system_prompt=system_prompt,
                prompt_sections=[
                    # The summary is earlier AI output derived from tickets and logs, so it is data, not instructions (V7).
                    PromptSection("Investigation summary", (investigation.executive_summary or "No summary yet.") if investigation else "No investigation yet.", is_untrusted=True, source_label="investigation summary"),
                    PromptSection("New chat messages (author: text)", "\n".join(message_lines), is_untrusted=True, source_label=f"teams-chat:{chat.teams_incident_chat_id}"),
                ],
                output_schema=TeamsChatDigestResult, usage_context=LlmUsageContext(application_id=incident.application_id, investigation_id=investigation.investigation_id if investigation else None),
            )
        except Exception as digest_error:  # noqa: BLE001 - AI is optional here: fall back to deterministic facts
            logger.info("Teams chat digest fell back to deterministic facts: %s", digest_error)
            digest = TeamsChatDigestResult(facts=deterministic_chat_facts(message_lines), confidence=0.5)
        for fact in digest.facts:
            self.session.add(InvestigationTimelineEvent(
                incident_id=incident.incident_id, investigation_id=investigation.investigation_id if investigation else None, event_type="chat_fact",
                event_title=sanitize_ai_line(author_aliases.restore_names(fact.fact_title), maximum_characters=400),
                event_details_markdown=sanitize_ai_markdown(author_aliases.restore_names(fact.fact_details)) or None, event_source="teams_chat", source_reference=chat.teams_incident_chat_id,
            ))
        minimum_gap = timedelta(minutes=self.settings.teams_unprompted_comment_minimum_interval_minutes)
        gap_elapsed = chat.last_unprompted_comment_at is None or utc_now() - chat.last_unprompted_comment_at >= minimum_gap
        if digest.should_comment and digest.confidence >= 0.7 and digest.comment_markdown.strip() and gap_elapsed:
            await self._post_keigan_message(chat, author_aliases.restore_names(digest.comment_markdown.strip()), None)
            chat.last_unprompted_comment_at = utc_now()
        await self.session.flush()

    # ── Bot Framework inbound ──────────────────────────────────────────────────
    def _ensure_expected_tenant(self, activity: dict[str, Any]) -> None:
        """Only activities from Keigan's own Entra tenant are accepted (V13); without a configured tenant a live bot accepts nothing."""
        expected_tenant = self.settings.entra_tenant_id.strip().lower()
        if not expected_tenant:
            if self.is_live:
                logger.warning("A Teams activity was rejected because ENTRA_TENANT_ID is not configured")
                raise ForbiddenException("The Teams bot is not set up for a tenant yet. Ask a Keigan admin to configure ENTRA_TENANT_ID.")
            return
        tenant = ((activity.get("channelData") or {}).get("tenant") or {}).get("id") or (activity.get("conversation") or {}).get("tenantId") or ""
        if str(tenant).strip().lower() != expected_tenant:
            logger.warning("A Teams activity from tenant %s was rejected", tenant or "(none)")
            raise ForbiddenException("This Teams tenant is not allowed to use Keigan.")

    async def handle_bot_activity(self, activity: dict[str, Any]) -> None:
        self._ensure_expected_tenant(activity)
        conversation_id = (activity.get("conversation") or {}).get("id")
        if not conversation_id:
            return
        chat = await self.session.scalar(select(TeamsIncidentChat).where(TeamsIncidentChat.teams_chat_identifier == conversation_id))
        if chat is None:
            return  # unknown chats are ignored
        activity_type = activity.get("type")
        if activity_type in ("installationUpdate", "conversationUpdate", "message"):
            chat.bot_conversation_reference_json = {
                "serviceUrl": activity.get("serviceUrl"), "conversationId": conversation_id, "botId": (activity.get("recipient") or {}).get("id"), "tenantId": ((activity.get("conversation") or {}).get("tenantId")),
            }
        if activity_type == "message":
            sender = activity.get("from") or {}
            plain_text = PiiMasker().mask_text(HTML_TAG_PATTERN.sub(" ", activity.get("text") or "").strip())
            if not plain_text:
                return
            if not (await TeamsSenderAuthorizer(self.session).access_for(chat.application_id, sender.get("aadObjectId"), sender.get("name"))).can_read:
                logger.info("Ignored a Teams message from a sender without access to application %s", chat.application_id)
                await self._post_keigan_message(chat, NOT_AUTHORIZED_REPLY, None)  # the bot only receives messages that address it
                return
            message = ConversationMessage(
                conversation_id=chat.conversation_id, author_role="teams_participant", author_display_name=sender.get("name"), message_text=plain_text, external_message_identifier=activity.get("id"),
            )
            self.session.add(message)
            await self.session.flush()
            addressed_text = plain_text if is_message_for_keigan(plain_text) else f"Keigan, {plain_text}"  # the bot only receives messages that mention it
            await self._process_messages(chat, [(sender.get("name") or "Participant", sender.get("aadObjectId"), addressed_text, message.message_id)])
        await self.session.flush()

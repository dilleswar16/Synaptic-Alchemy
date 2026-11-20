"""Investigation chat and Keigan AI chat (natural language → query → answer / chart).

Keigan AI chat per message: mask PII → intent → resolve application/service → time range (or clarification) →
generate query → validate → execute → mask → answer. Knowledge questions are grounded in the application knowledge base.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.chat_ai_schemas import DATA_INTENTS, ChatAnswerResult, ChatIntentResult, build_answer_offline, plan_intent_offline
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection, estimate_token_count
from keigan.ai.output_sanitizer import sanitize_ai_markdown
from keigan.ai.prompt_safety import find_citation_codes, remove_invalid_citations
from keigan.ai.user_facing_errors import describe_failure_for_user
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.dtos.chat_dtos import (
    ChatMessageResponse, ConversationCreateRequest, ConversationDetailResponse, ConversationResponse, ConversationUpdateRequest, SendMessageRequest, SuggestedPromptResponse,
)
from keigan.entities.all_entities import Application, Conversation, ConversationMessage, Investigation, MonitoredService
from keigan.entities.status_values import MessageAuthorRole
from keigan.exceptions.keigan_exceptions import (
    BusinessValidationException, ForbiddenException, IntegrationException, KeiganException, LlmOutputValidationException, NotFoundException,
)
from keigan.security.current_user import CurrentUser
from keigan.security.security_middleware import rate_limiter
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.chat_data_query_service import ChatDataQueryService, DataQueryOutcome, QueryNotAnswerableError
from keigan.services.investigation_chat_service import InvestigationChatService
from keigan.services.knowledge_service import KnowledgeService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)

KEIGAN_SCOPE = "keigan_ai_chat"
INVESTIGATION_SCOPE = "investigation"
DEFAULT_TITLE = "New conversation"
MAXIMUM_LOOKBACK_MINUTES = 30 * 1440
CLARIFICATION_OPTIONS = [{"label": "Last hour", "value": "60"}, {"label": "Last 24 hours", "value": "1440"}, {"label": "Last 7 days", "value": "10080"}, {"label": "Last 30 days", "value": "43200"}]
_UNIT_MINUTES = {"m": 1, "min": 1, "mins": 1, "minute": 1, "minutes": 1, "h": 60, "hr": 60, "hrs": 60, "hour": 60, "hours": 60, "d": 1440, "day": 1440, "days": 1440, "w": 10080, "week": 10080, "weeks": 10080}
_RELATIVE_WINDOW = re.compile(r"\b(?:last|past|previous|in the last|over the last)\s+(\d+(?:\.\d+)?)?\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|[mhdw])\b", re.I)
_SELF_HANDLED_ERRORS = (KeiganException,)


@dataclass
class AssistantAnswer:
    answer_markdown: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    message_payload: dict[str, Any] = field(default_factory=dict)
    input_token_count: int = 0
    output_token_count: int = 0


def parse_time_window(question: str, now: datetime) -> tuple[datetime, datetime] | None:
    """"last 17 hours", "past 7 days", "yesterday", "today", "last hour" → (start, end); None when no time frame is given."""
    lowered = question.lower()
    if "yesterday" in lowered:
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=1), midnight
    if re.search(r"\btoday\b", lowered):
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    match = _RELATIVE_WINDOW.search(question)
    if match is None:
        return None
    minutes = float(match.group(1) or 1) * _UNIT_MINUTES[match.group(2).lower()]
    minutes = min(max(minutes, 5), MAXIMUM_LOOKBACK_MINUTES)
    return now - timedelta(minutes=minutes), now


def describe_window(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "the last day" if days == 1 else f"the last {days} days"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "the last hour" if hours == 1 else f"the last {hours} hours"
    return f"the last {minutes} minutes"


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.gateway = application_context.llm_gateway()

    # ── Contract used by the Teams bot ───────────────────────────────────────────────────────────────────────────────
    async def answer_investigation_question(
        self,
        investigation_id: str,
        question_text: str,
        *,
        asked_by_user_principal_name: str | None = None,
        asked_by_display_name: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        allow_log_queries: bool = True,
    ) -> AssistantAnswer:
        """Grounded answer about one investigation (may run read-only follow-up queries unless ``allow_log_queries`` is False). Used by the Teams bot (S4)."""
        answer_text, citations, input_tokens, output_tokens = await InvestigationChatService(self.session).answer(
            investigation_id, question_text, asked_by_user_principal_name, conversation_history, allow_log_queries=allow_log_queries
        )
        return AssistantAnswer(answer_text, citations, {"answerKind": "text", "citations": citations}, input_tokens, output_tokens)

    # ── Conversations ────────────────────────────────────────────────────────────────────────────────────────────────
    async def list_conversations(self, current_user: CurrentUser, scope: str | None) -> list[ConversationResponse]:
        conditions = [Conversation.owner_user_principal_name == current_user.user_principal_name]
        if scope:
            conditions.append(Conversation.conversation_scope == scope)
        conversations = (await self.session.scalars(select(Conversation).where(*conditions).order_by(Conversation.updated_at.desc()).limit(200))).all()
        counts = dict((await self.session.execute(
            select(ConversationMessage.conversation_id, func.count()).where(ConversationMessage.conversation_id.in_([item.conversation_id for item in conversations])).group_by(ConversationMessage.conversation_id)
        )).all()) if conversations else {}
        return [self._to_response(item, counts.get(item.conversation_id, 0)) for item in conversations]

    async def create_conversation(self, current_user: CurrentUser, request: ConversationCreateRequest) -> ConversationDetailResponse:
        authorization = AuthorizationService(self.session)
        if request.conversation_scope == INVESTIGATION_SCOPE:
            if not request.investigation_id:
                raise BusinessValidationException("An investigation conversation needs an investigationId.")
            investigation = await self.session.get(Investigation, request.investigation_id)
            if investigation is None:
                raise NotFoundException("That investigation does not exist.")
            await authorization.ensure_application_reader(current_user, investigation.application_id)
            existing = await self.session.scalar(select(Conversation).where(
                Conversation.conversation_scope == INVESTIGATION_SCOPE, Conversation.investigation_id == request.investigation_id,
                Conversation.owner_user_principal_name == current_user.user_principal_name).limit(1))
            if existing is not None:
                return await self._to_detail(existing)
            conversation = Conversation(conversation_scope=INVESTIGATION_SCOPE, investigation_id=request.investigation_id, incident_id=investigation.incident_id,
                                        owner_user_principal_name=current_user.user_principal_name, conversation_title="Investigation chat",
                                        created_by_user_principal_name=current_user.user_principal_name)
            conversation.replace_linked_ids("application_links", [investigation.application_id])
        elif request.conversation_scope == KEIGAN_SCOPE:
            application_ids = await authorization.scoped_application_ids(current_user, request.application_ids) if request.application_ids else []
            conversation = Conversation(conversation_scope=KEIGAN_SCOPE, owner_user_principal_name=current_user.user_principal_name,
                                        conversation_title=DEFAULT_TITLE, created_by_user_principal_name=current_user.user_principal_name)
            conversation.replace_linked_ids("application_links", application_ids)
        else:
            raise BusinessValidationException("conversationScope must be keigan_ai_chat or investigation.")
        self.session.add(conversation)
        await self.session.flush()
        return await self._to_detail(conversation)

    async def get_conversation(self, current_user: CurrentUser, conversation_id: str) -> ConversationDetailResponse:
        return await self._to_detail(await self._owned_conversation(current_user, conversation_id))

    async def update_conversation(self, current_user: CurrentUser, conversation_id: str, request: ConversationUpdateRequest) -> ConversationResponse:
        conversation = await self._owned_conversation(current_user, conversation_id)
        if request.conversation_title is not None:
            conversation.conversation_title = PiiMasker().mask_text(request.conversation_title).strip() or DEFAULT_TITLE
        if request.application_ids is not None and conversation.conversation_scope == KEIGAN_SCOPE:
            conversation.replace_linked_ids("application_links", await AuthorizationService(self.session).scoped_application_ids(current_user, request.application_ids) if request.application_ids else [])
        conversation.updated_by_user_principal_name = current_user.user_principal_name
        return self._to_response(conversation, 0)

    async def delete_conversation(self, current_user: CurrentUser, conversation_id: str) -> None:
        conversation = await self._owned_conversation(current_user, conversation_id)
        await self.session.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))
        await self.session.delete(conversation)

    async def suggested_prompts(self, current_user: CurrentUser, application_id: str | None) -> list[SuggestedPromptResponse]:
        readable = await AuthorizationService(self.session).readable_application_ids(current_user)
        scoped = [application_id] if application_id and application_id in readable else sorted(readable)[:1]
        service_name = "claims-api"
        if scoped:
            service = await self.session.scalar(select(MonitoredService).where(MonitoredService.application_id == scoped[0]).order_by(MonitoredService.service_name).limit(1))
            service_name = service.service_name if service else service_name
        return [
            SuggestedPromptResponse(prompt_text=f"How many requests failed in the last 24 hours on {service_name}?", category="data"),
            SuggestedPromptResponse(prompt_text=f"Show me the pattern of errors on {service_name} over the last 7 days", category="data"),
            SuggestedPromptResponse(prompt_text="Which services does this application depend on?", category="knowledge"),
            SuggestedPromptResponse(prompt_text="What is the runbook for a database connection failure?", category="knowledge"),
            SuggestedPromptResponse(prompt_text=f"Is {service_name} slower than usual today?", category="data"),
            SuggestedPromptResponse(prompt_text="Summarise what changed in the last day", category="knowledge"),
        ]

    # ── Messages ─────────────────────────────────────────────────────────────────────────────────────────────────────
    async def send_message(self, current_user: CurrentUser, conversation_id: str, request: SendMessageRequest) -> ChatMessageResponse:
        conversation = await self._owned_conversation(current_user, conversation_id)
        rate_limiter.check(f"chat:{current_user.user_principal_name}", self.settings.chat_rate_limit_per_minute)
        history = await self._messages(conversation_id)
        masker = PiiMasker()
        masked_message_text = masker.mask_text(request.message_text)  # personal data is masked before it is stored, not only before the model call (V12)
        self.session.add(ConversationMessage(
            conversation_id=conversation_id, author_role=MessageAuthorRole.USER, author_display_name=current_user.display_name, author_user_principal_name=current_user.user_principal_name,
            message_text=masked_message_text, input_token_count=estimate_token_count(masked_message_text), output_token_count=0, created_at=utc_now()))
        await self.session.flush()
        try:
            if conversation.conversation_scope == INVESTIGATION_SCOPE:
                answer = await self.answer_investigation_question(
                    conversation.investigation_id or "", masked_message_text, asked_by_user_principal_name=current_user.user_principal_name,
                    asked_by_display_name=current_user.display_name,
                    conversation_history=[{"role": "user" if item.author_role == MessageAuthorRole.USER else "assistant", "content": masker.mask_text(item.message_text)} for item in history])
            else:
                answer = await self._answer_keigan_question(current_user, conversation, request, history)
        except _SELF_HANDLED_ERRORS as chat_error:
            if isinstance(chat_error, (ForbiddenException, NotFoundException)):
                raise
            answer = AssistantAnswer(f"I couldn't complete that. {describe_failure_for_user(chat_error)}", message_payload={"answerKind": "text", "failed": True})
        assistant_message = ConversationMessage(
            conversation_id=conversation_id, author_role=MessageAuthorRole.ASSISTANT, author_display_name="Keigan", message_text=answer.answer_markdown,
            message_payload_json=answer.message_payload or {"answerKind": "text", "citations": answer.citations}, input_token_count=answer.input_token_count,
            output_token_count=answer.output_token_count, created_at=utc_now() + timedelta(milliseconds=1))
        self.session.add(assistant_message)
        if conversation.conversation_title == DEFAULT_TITLE:
            conversation.conversation_title = truncate_text(masked_message_text.strip(), 60)
        conversation.updated_by_user_principal_name = current_user.user_principal_name
        conversation.updated_at = utc_now()
        await self.session.flush()
        return self._to_message_response(assistant_message)

    # ── Keigan AI chat engine ────────────────────────────────────────────────────────────────────────────────────────
    async def _answer_keigan_question(self, current_user: CurrentUser, conversation: Conversation, request: SendMessageRequest, history: list[ConversationMessage]) -> AssistantAnswer:
        authorization = AuthorizationService(self.session)
        readable_ids = await authorization.readable_application_ids(current_user)
        scope_ids = [identifier for identifier in conversation.application_ids if identifier in readable_ids] or sorted(readable_ids)
        applications = list((await self.session.scalars(select(Application).where(Application.application_id.in_(scope_ids)))).all()) if scope_ids else []
        if not applications:
            return AssistantAnswer("You don't have access to any applications yet, so there is nothing for me to look at.", message_payload={"answerKind": "text"})
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id.in_(scope_ids), MonitoredService.is_monitoring_enabled.is_(True)))).all())
        previous = next((item.message_payload_json.get("conversationContext") for item in reversed(history) if item.author_role == MessageAuthorRole.ASSISTANT and (item.message_payload_json or {}).get("conversationContext")), None)

        question_text = request.message_text
        forced_minutes: int | None = None
        if request.clarification_response:
            forced_minutes = int(re.sub(r"\D", "", request.clarification_response) or 1440)
            question_text = next((item.message_text for item in reversed(history) if item.author_role == MessageAuthorRole.USER), request.message_text)
        masked_question = PiiMasker().mask_text(question_text)
        usage_context = LlmUsageContext(application_id=applications[0].application_id if len(applications) == 1 else None, conversation_id=conversation.conversation_id, requested_by_user_principal_name=current_user.user_principal_name)

        intent = await self._classify(masked_question, applications, services, previous, usage_context)
        if intent.intent == "out_of_scope":
            return AssistantAnswer("I can answer questions about your monitored applications: their logs and error patterns, architecture, runbooks and incidents. That one is outside what I can help with.", message_payload={"answerKind": "text"})
        application = self._resolve_application(intent, masked_question, applications, services, previous)
        if intent.intent == "knowledge":
            return await self._answer_knowledge(masked_question, application, applications, usage_context)
        return await self._answer_data(current_user, conversation, intent, masked_question, application, services, previous, forced_minutes, usage_context)

    async def _classify(self, question: str, applications: list[Application], services: list[MonitoredService], previous: dict[str, Any] | None, usage_context: LlmUsageContext) -> ChatIntentResult:
        candidates = {"applicationNames": [item.application_name for item in applications], "serviceNames": [item.service_name for item in services], "hasPreviousContext": previous is not None}
        try:
            return await self.gateway.generate_structured(
                feature_name="ai_chat_intent", model_tier=ModelTier.FAST, system_prompt=application_context.prompt_library().render("ai_chat_intent"),
                prompt_sections=[PromptSection("Candidates", json.dumps(candidates)), PromptSection("Question", question, is_untrusted=True, source_label="chat:user-question")],
                output_schema=ChatIntentResult, usage_context=usage_context)
        except (LlmOutputValidationException, IntegrationException) as classification_error:
            logger.warning("Intent classification fell back to rules: %s", classification_error)
            return plan_intent_offline(question, candidates["serviceNames"], previous is not None)

    @staticmethod
    def _resolve_application(intent: ChatIntentResult, question: str, applications: list[Application], services: list[MonitoredService], previous: dict[str, Any] | None) -> Application | None:
        lowered = question.lower()
        named = next((item for item in applications if item.application_name.lower() in lowered or item.application_code.lower() in lowered or item.application_name == intent.application_name), None)
        if named:
            return named
        named_service = next((item for item in services if item.service_name == intent.service_name or item.service_name.lower() in lowered), None)
        if named_service:
            return next(item for item in applications if item.application_id == named_service.application_id)
        if previous:
            return next((item for item in applications if item.application_id == previous.get("applicationId")), None)
        return applications[0] if len(applications) == 1 else None

    async def _answer_knowledge(self, question: str, application: Application | None, applications: list[Application], usage_context: LlmUsageContext) -> AssistantAnswer:
        knowledge_service = KnowledgeService(self.session)
        targets = [application] if application else applications[:3]
        markdown_parts: list[str] = []
        references: dict[str, str] = {}
        contains_flagged_content = False
        for target in targets:
            try:
                grounding = await knowledge_service.build_grounding_context(target.application_id, question, token_budget=3000)
            except Exception as grounding_error:  # noqa: BLE001 — knowledge is optional context
                logger.info("Knowledge grounding unavailable for %s: %s", target.application_id, grounding_error)
                continue
            if grounding.knowledge_markdown.strip() or grounding.topology_summary_markdown.strip():
                # Every application numbers its knowledge from K1, so codes are shifted to stay unique across applications.
                offset = len(references)
                shift = lambda text: re.sub(r"\[K(\d+)\]", lambda match: f"[K{int(match.group(1)) + offset}]", text)  # noqa: E731
                markdown_parts.append(f"## {target.application_name}\n{shift(grounding.topology_summary_markdown)}\n{shift(grounding.knowledge_markdown)}")
                references.update({f"K{int(reference.reference_code[1:]) + offset}": reference.title for reference in grounding.references})
                contains_flagged_content = contains_flagged_content or grounding.contains_flagged_content
        if not markdown_parts:
            return AssistantAnswer("I couldn't find anything about that in the knowledge Keigan holds for your applications. Uploading the relevant document or runbook to the application's knowledge base would let me answer it.", message_payload={"answerKind": "text"})
        knowledge_markdown = "\n\n".join(markdown_parts)
        if self.gateway.is_mock:
            answer_text = "Here is what the application knowledge says:\n\n" + truncate_text(knowledge_markdown.replace("## ", "**").strip(), 900)
        else:
            result = await self.gateway.generate_text(
                feature_name="ai_chat_knowledge_answer", model_tier=ModelTier(application_context.prompt_library().model_tier_for_call("ai_chat_knowledge_answer")),
                system_prompt=application_context.prompt_library().render("ai_chat_knowledge_answer"),
                prompt_sections=[
                    PromptSection("Application knowledge", knowledge_markdown, is_untrusted=True, source_label="knowledge documents", is_flagged=contains_flagged_content),
                    PromptSection("Question", question, is_untrusted=True, source_label="chat:user-question"),
                ], usage_context=usage_context)
            answer_text = remove_invalid_citations(result.text, set(references))
        answer_text = sanitize_ai_markdown(answer_text)
        citations = [{"kind": "knowledge", "title": references[code], "reference": code} for code in sorted(find_citation_codes(answer_text)) if code in references]
        context = {"applicationId": application.application_id} if application else None
        return AssistantAnswer(answer_text, citations, {"answerKind": "text", "citations": citations, "conversationContext": context}, estimate_token_count(knowledge_markdown + question), estimate_token_count(answer_text))

    async def _answer_data(self, current_user: CurrentUser, conversation: Conversation, intent: ChatIntentResult, question: str, application: Application | None, services: list[MonitoredService],
                           previous: dict[str, Any] | None, forced_minutes: int | None, usage_context: LlmUsageContext) -> AssistantAnswer:
        lowered = question.lower()
        pool = [item for item in services if application is None or item.application_id == application.application_id]
        service = next((item for item in pool if item.service_name == intent.service_name), None) or next((item for item in sorted(pool, key=lambda item: -len(item.service_name)) if item.service_name.lower() in lowered), None)
        if service is None and previous:
            service = next((item for item in pool if item.service_id == previous.get("serviceId")), None)
        if service is None and len(pool) == 1:
            service = pool[0]
        if service is None:
            names = ", ".join(sorted(item.service_name for item in pool)[:10])
            return AssistantAnswer(f"Which service do you mean? I can look at: {names}.", message_payload={"answerKind": "text"})
        wants_pattern = intent.intent in ("data_pattern", "mixed")
        wants_failures = intent.wants_failures_only or bool(re.search(r"\b(fail\w*|error\w*|exception\w*|5xx)\b", lowered)) or (previous or {}).get("wantsFailures", False) and not re.search(r"\b(request|traffic)s?\b", lowered)

        now = utc_now()
        window = (now - timedelta(minutes=forced_minutes), now) if forced_minutes else parse_time_window(question, now)
        if window is None and previous and previous.get("lookbackMinutes"):
            window = (now - timedelta(minutes=int(previous["lookbackMinutes"])), now)
        if window is None and wants_pattern:
            return AssistantAnswer("Over what time frame should I look?", message_payload={"answerKind": "clarification", "clarificationOptions": CLARIFICATION_OPTIONS})
        start, end = window or (now - timedelta(hours=24), now)
        lookback_minutes = max(5, int((end - start).total_seconds() // 60))

        try:
            outcome = await ChatDataQueryService(self.session).run(
                service=service, question_text=question, wants_failures=wants_failures, wants_pattern=wants_pattern, time_range_start=start, time_range_end=end,
                requested_by=current_user.user_principal_name, usage_context=usage_context)
        except QueryNotAnswerableError as cannot_answer:
            return AssistantAnswer(cannot_answer.detail, message_payload={"answerKind": "text"})
        except KeiganException as query_error:
            return AssistantAnswer(f"I couldn't query {service.service_name}. {describe_failure_for_user(query_error)}", message_payload={"answerKind": "text", "failed": True})
        return await self._compose_data_answer(service, outcome, wants_pattern, wants_failures, lookback_minutes, usage_context, question)

    async def _compose_data_answer(self, service: MonitoredService, outcome: DataQueryOutcome, wants_pattern: bool, wants_failures: bool, lookback_minutes: int, usage_context: LlmUsageContext, question: str) -> AssistantAnswer:
        series = outcome.series if wants_pattern else []
        peak = max(series, key=lambda point: point[1], default=None)
        facts = {"kind": "chart" if series else "number", "serviceName": service.service_name, "windowText": describe_window(lookback_minutes), "wantsFailures": wants_failures,
                 "total": outcome.total, "rowCount": outcome.row_count, "peakLabel": peak[0][:16].replace("T", " ") if peak else None, "peakValue": int(peak[1]) if peak else None}
        try:
            answer_text = (await self.gateway.generate_structured(
                feature_name="ai_chat_answer", model_tier=ModelTier.FAST, system_prompt=application_context.prompt_library().render("ai_chat_answer"),
                prompt_sections=[PromptSection("Facts", json.dumps(facts)), PromptSection("Question", question, is_untrusted=True, source_label="chat:user-question")],
                output_schema=ChatAnswerResult, usage_context=usage_context)).answer_text
        except KeiganException:
            answer_text = build_answer_offline(facts)
        answer_text = sanitize_ai_markdown(answer_text)
        payload: dict[str, Any] = {
            "answerKind": "chart" if series else "number", "numberValue": outcome.total,
            "queryDetails": {"serviceName": service.service_name, "sourceKind": outcome.source_kind, "queryLanguage": outcome.query_language, "queryText": outcome.query_text,
                             "timeRange": {"start": outcome.time_range_start.isoformat(), "end": outcome.time_range_end.isoformat()}, "rowCount": outcome.row_count, "isSimulated": outcome.is_simulated},
            "conversationContext": {"applicationId": service.application_id, "serviceId": service.service_id, "lookbackMinutes": lookback_minutes, "wantsFailures": wants_failures},
        }
        if series:
            label = "Failed" if wants_failures else "Requests"
            payload["chartSpecification"] = {
                "chartType": "bar" if lookback_minutes > 2880 and len(series) <= 14 else "area", "title": f"{'Failed requests' if wants_failures else 'Requests'} on {service.service_name}",
                "xField": "timestamp", "xFieldKind": "time", "series": [{"field": "count", "label": label, "colorToken": "danger" if wants_failures else "primary"}], "unit": "count",
                "rows": [{"timestamp": timestamp, "count": int(value)} for timestamp, value in series]}
        return AssistantAnswer(answer_text, [], payload, estimate_token_count(question) + 200, estimate_token_count(answer_text))

    # ── Helpers ──────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _owned_conversation(self, current_user: CurrentUser, conversation_id: str) -> Conversation:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundException("That conversation does not exist.")
        if conversation.owner_user_principal_name != current_user.user_principal_name:
            raise ForbiddenException("This conversation belongs to someone else.")
        return conversation

    async def _messages(self, conversation_id: str) -> list[ConversationMessage]:
        return list((await self.session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.created_at))).all())

    async def _to_detail(self, conversation: Conversation) -> ConversationDetailResponse:
        messages = await self._messages(conversation.conversation_id)
        base = self._to_response(conversation, len(messages))
        return ConversationDetailResponse(**base.model_dump(), messages=[self._to_message_response(item) for item in messages])

    @staticmethod
    def _to_response(conversation: Conversation, message_count: int) -> ConversationResponse:
        return ConversationResponse(
            conversation_id=conversation.conversation_id, conversation_scope=conversation.conversation_scope, application_ids=conversation.application_ids,
            investigation_id=conversation.investigation_id, conversation_title=conversation.conversation_title, message_count=message_count,
            created_at=conversation.created_at, updated_at=conversation.updated_at)

    @staticmethod
    def _to_message_response(message: ConversationMessage) -> ChatMessageResponse:
        return ChatMessageResponse(
            message_id=message.message_id, conversation_id=message.conversation_id, author_role=message.author_role, author_display_name=message.author_display_name,
            message_text=message.message_text, message_payload=message.message_payload_json, created_at=message.created_at)

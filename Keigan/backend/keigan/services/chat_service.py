"""Conversations of the Keigan AI chat and of the investigation chat, and the investigation answer the Teams bot gets.

Keigan AI chat questions are answered by ``ask_keigan_service``; this module keeps the conversation records (create, list, read, rename, delete).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.llm_gateway import estimate_token_count
from keigan.ai.user_facing_errors import describe_failure_for_user
from keigan.config.settings import get_settings
from keigan.dtos.chat_dtos import (
    ChatMessageResponse, ConversationCreateRequest, ConversationDetailResponse, ConversationResponse, ConversationUpdateRequest, SendMessageRequest, SuggestedPromptResponse,
)
from keigan.entities.all_entities import Application, Conversation, ConversationMessage, Investigation, MonitoredService
from keigan.entities.incident_entities import ChatAnswerRun
from keigan.entities.status_values import MessageAuthorRole
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, KeiganException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.security.security_middleware import rate_limiter
from keigan.services.answer_run_retention import delete_answer_runs
from keigan.services.ask_keigan_answer_access import AnswerAccess, WithheldAnswer
from keigan.services.authorization_service import AuthorizationService
from keigan.services.conversation_titles import DEFAULT_CONVERSATION_TITLE, title_after_question
from keigan.services.investigation_chat_service import InvestigationChatService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now

KEIGAN_SCOPE = "keigan_ai_chat"
INVESTIGATION_SCOPE = "investigation"
_SELF_HANDLED_ERRORS = (KeiganException,)


@dataclass
class AssistantAnswer:
    answer_markdown: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    message_payload: dict[str, Any] = field(default_factory=dict)
    input_token_count: int = 0
    output_token_count: int = 0


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

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
                return await self._to_detail(existing, current_user)
            conversation = Conversation(conversation_scope=INVESTIGATION_SCOPE, investigation_id=request.investigation_id, incident_id=investigation.incident_id,
                                        owner_user_principal_name=current_user.user_principal_name, conversation_title="Investigation chat",
                                        created_by_user_principal_name=current_user.user_principal_name)
            conversation.replace_linked_ids("application_links", [investigation.application_id])
        elif request.conversation_scope == KEIGAN_SCOPE:
            application_ids = await authorization.scoped_application_ids(current_user, request.application_ids) if request.application_ids else []
            conversation = Conversation(conversation_scope=KEIGAN_SCOPE, owner_user_principal_name=current_user.user_principal_name,
                                        conversation_title=DEFAULT_CONVERSATION_TITLE, created_by_user_principal_name=current_user.user_principal_name)
            conversation.replace_linked_ids("application_links", application_ids)
        else:
            raise BusinessValidationException("conversationScope must be keigan_ai_chat or investigation.")
        self.session.add(conversation)
        await self.session.flush()
        return await self._to_detail(conversation, current_user)

    async def get_conversation(self, current_user: CurrentUser, conversation_id: str) -> ConversationDetailResponse:
        return await self._to_detail(await self.open_conversation(current_user, conversation_id), current_user)

    async def update_conversation(self, current_user: CurrentUser, conversation_id: str, request: ConversationUpdateRequest) -> ConversationResponse:
        conversation = await self.owned_conversation(current_user, conversation_id)
        if request.conversation_title is not None:
            conversation.conversation_title = PiiMasker().mask_text(request.conversation_title).strip() or DEFAULT_CONVERSATION_TITLE
        if request.application_ids is not None and conversation.conversation_scope == KEIGAN_SCOPE:
            conversation.replace_linked_ids("application_links", await AuthorizationService(self.session).scoped_application_ids(current_user, request.application_ids) if request.application_ids else [])
        conversation.updated_by_user_principal_name = current_user.user_principal_name
        return self._to_response(conversation, 0)

    async def delete_conversation(self, current_user: CurrentUser, conversation_id: str) -> None:
        conversation = await self.owned_conversation(current_user, conversation_id)
        await delete_answer_runs(self.session, ChatAnswerRun.conversation_id == conversation_id)
        await self.session.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))
        await self.session.delete(conversation)

    async def suggested_prompts(self, current_user: CurrentUser, application_id: str | None) -> list[SuggestedPromptResponse]:
        readable = await AuthorizationService(self.session).readable_application_ids(current_user)
        scoped = [application_id] if application_id and application_id in readable else sorted(readable)[:1]
        application_name, service_name = "my application", "claims-api"
        if scoped:
            application = await self.session.get(Application, scoped[0])
            application_name = application.application_name if application else application_name
            service = await self.session.scalar(select(MonitoredService).where(MonitoredService.application_id == scoped[0]).order_by(MonitoredService.service_name).limit(1))
            service_name = service.service_name if service else service_name
        return [  # one for each kind of question the tools can answer: SLOs, incidents, changes, logs, predictive signals, runbooks
            SuggestedPromptResponse(prompt_text="Which SLOs are at risk right now?", category="data"),
            SuggestedPromptResponse(prompt_text="Are there open P1 or P2 incidents?", category="data"),
            SuggestedPromptResponse(prompt_text=f"What changed on {application_name} in the last day?", category="data"),
            SuggestedPromptResponse(prompt_text=f"Show failed requests on {service_name} in the last 24 hours", category="data"),
            SuggestedPromptResponse(prompt_text="Which predictive signals are open?", category="data"),
            SuggestedPromptResponse(prompt_text="What is the runbook for a database connection failure?", category="knowledge"),
        ]

    # ── Messages ─────────────────────────────────────────────────────────────────────────────────────────────────────
    async def send_message(self, current_user: CurrentUser, conversation_id: str, request: SendMessageRequest) -> ChatMessageResponse:
        conversation = await self.open_conversation(current_user, conversation_id)
        if conversation.conversation_scope != INVESTIGATION_SCOPE:
            raise BusinessValidationException("A Keigan AI chat is answered through POST /api/chat/conversations/{conversationId}/answers.")
        rate_limiter.check(f"chat:{current_user.user_principal_name}", self.settings.chat_rate_limit_per_minute)
        history = await self.conversation_messages(conversation_id)
        masker = PiiMasker()
        masked_message_text = masker.mask_text(request.message_text)  # personal data is masked before it is stored, not only before the model call (V12)
        self.session.add(ConversationMessage(
            conversation_id=conversation_id, author_role=MessageAuthorRole.USER, author_display_name=current_user.display_name, author_user_principal_name=current_user.user_principal_name,
            message_text=masked_message_text, input_token_count=estimate_token_count(masked_message_text), output_token_count=0, created_at=utc_now()))
        await self.session.flush()
        try:
            answer = await self.answer_investigation_question(
                conversation.investigation_id or "", masked_message_text, asked_by_user_principal_name=current_user.user_principal_name,
                asked_by_display_name=current_user.display_name,
                conversation_history=[{"role": "user" if item.author_role == MessageAuthorRole.USER else "assistant", "content": masker.mask_text(item.message_text)} for item in history])
        except _SELF_HANDLED_ERRORS as chat_error:
            if isinstance(chat_error, (ForbiddenException, NotFoundException)):
                raise
            answer = AssistantAnswer(f"I couldn't complete that. {describe_failure_for_user(chat_error)}", message_payload={"answerKind": "text", "failed": True})
        assistant_message = ConversationMessage(
            conversation_id=conversation_id, author_role=MessageAuthorRole.ASSISTANT, author_display_name="Keigan", message_text=answer.answer_markdown,
            message_payload_json=answer.message_payload or {"answerKind": "text", "citations": answer.citations}, input_token_count=answer.input_token_count,
            output_token_count=answer.output_token_count, created_at=utc_now() + timedelta(milliseconds=1))
        self.session.add(assistant_message)
        conversation.conversation_title = title_after_question(conversation.conversation_title, masked_message_text)
        conversation.updated_by_user_principal_name = current_user.user_principal_name
        conversation.updated_at = utc_now()
        await self.session.flush()
        return self._to_message_response(assistant_message)

    # ── Helpers ──────────────────────────────────────────────────────────────────────────────────────────────────────
    async def owned_conversation(self, current_user: CurrentUser, conversation_id: str) -> Conversation:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundException("That conversation does not exist.")
        if conversation.owner_user_principal_name != current_user.user_principal_name:
            raise ForbiddenException("This conversation belongs to someone else.")
        return conversation

    async def open_conversation(self, current_user: CurrentUser, conversation_id: str) -> Conversation:
        """The conversation of ``current_user``, when they still may use it: they own it and (for an investigation chat) can still read its application."""
        conversation = await self.owned_conversation(current_user, conversation_id)
        await self._ensure_still_allowed(current_user, conversation)
        return conversation

    async def _ensure_still_allowed(self, current_user: CurrentUser, conversation: Conversation) -> None:
        """Owning a conversation is not access: an investigation chat shows the application's data, so the owner must still be able to read that application.

        Access is checked when the chat is opened and again on every read and send, so removing someone's access takes effect at once.
        Renaming or deleting one's own chat stays allowed (it is the person's own record and shows no application data).
        """
        if conversation.conversation_scope != INVESTIGATION_SCOPE:
            return  # a Keigan AI chat re-checks readable applications on every question
        investigation = await self.session.get(Investigation, conversation.investigation_id) if conversation.investigation_id else None
        if investigation is None:
            raise NotFoundException("That investigation no longer exists.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, investigation.application_id)

    async def conversation_messages(self, conversation_id: str) -> list[ConversationMessage]:
        return list((await self.session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.created_at))).all())

    async def _to_detail(self, conversation: Conversation, current_user: CurrentUser) -> ConversationDetailResponse:
        """The conversation with its messages, where an answer that used an application the person can no longer read is replaced by a notice (``AnswerAccess``)."""
        messages = await self.conversation_messages(conversation.conversation_id)
        withheld = await AnswerAccess(self.session).withheld_answers(current_user, conversation.conversation_id, messages)
        base = self._to_response(conversation, len(messages))
        return ConversationDetailResponse(**base.model_dump(), messages=[self._to_message_response(item, withheld.get(item.message_id)) for item in messages])

    @staticmethod
    def _to_response(conversation: Conversation, message_count: int) -> ConversationResponse:
        return ConversationResponse(
            conversation_id=conversation.conversation_id, conversation_scope=conversation.conversation_scope, application_ids=conversation.application_ids,
            investigation_id=conversation.investigation_id, conversation_title=conversation.conversation_title, message_count=message_count,
            created_at=conversation.created_at, updated_at=conversation.updated_at)

    @staticmethod
    def _to_message_response(message: ConversationMessage, withheld: WithheldAnswer | None = None) -> ChatMessageResponse:
        return ChatMessageResponse(
            message_id=message.message_id, conversation_id=message.conversation_id, author_role=message.author_role, author_display_name=message.author_display_name,
            message_text=withheld.message_text if withheld else message.message_text, message_payload=withheld.message_payload if withheld else message.message_payload_json,
            created_at=message.created_at)

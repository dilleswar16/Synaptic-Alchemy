"""Answers one question asked to Keigan in an incident's Teams chat, through the Ask Keigan engine (spec 23, 4.4 and phase 4).

The answer runs as the person who asked: ``TeamsSenderAuthorizer`` resolves the Teams sender to a Keigan user (and has already refused anyone it cannot), and the engine checks
that user's access to the application on every tool call, so an answer never reads more than its author may. The scope is the incident's investigation, so nothing else is
reachable. ``query_logs`` returns sample rows into a room, so it is withheld unless the author is an application admin (V13). What the room said is only ever the question: the
text reaches the engine as the user's question, untrusted like every question.

The trace of the answer (run and steps) is kept in a conversation of the author's own (``ChatService.open_teams_conversation``), apart from the room's messages and from their
investigation chat on the web. The caller has no stream to read, so it awaits the run's outcome and posts the stored answer.

``answer`` returns None when no answer was produced (the engine refused or the run failed; the reason is logged with its catalogue code), and the caller posts the
investigation's own findings instead. It raises ``ForbiddenException`` when the author no longer has access: the caller must not show them the investigation then.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ask_keigan_errors import INTERNAL_ERROR, AskKeiganErrorCatalogue
from keigan.dtos.ask_keigan_dtos import AnswerRequest
from keigan.dtos.chat_dtos import MESSAGE_TEXT_MAXIMUM_CHARACTERS
from keigan.entities.incident_entities import ConversationMessage
from keigan.entities.status_values import ChatAnswerRunStatus
from keigan.exceptions.keigan_exceptions import ForbiddenException, KeiganException
from keigan.services.ask_keigan_engine import AnswerOutcome
from keigan.services.ask_keigan_service import AskKeiganService
from keigan.services.chat_service import ChatService
from keigan.services.teams_sender_authorizer import TeamsSenderAccess
from keigan.utils.string_table import translate
from keigan.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)
LOG_QUERY_TOOL_NAME = "query_logs"
_CITATIONS_KEY, _UNVERIFIED_KEY = "citations", "isUnverified"  # the keys of the stored answer's payload (``TraceRecorder.complete_run``)


class TeamsQuestionAnswerer:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def answer(self, investigation_id: str, access: TeamsSenderAccess, question_text: str, language_code: str | None) -> str | None:
        """The text to post for ``question_text`` asked by the sender ``access`` describes. ``language_code`` is the room's: it speaks for an author whose own language is unknown."""
        if access.user is None:
            raise ForbiddenException("Keigan could not tell who asked, so it does not answer.")  # fail closed: ``can_read`` always comes with its user
        author = replace(access.user, preferred_locale=access.user.preferred_locale or language_code)
        withheld_tool_names = frozenset() if access.is_application_admin else frozenset({LOG_QUERY_TOOL_NAME})
        try:
            conversation_id = await ChatService(self.session).open_teams_conversation(author, investigation_id)
            # The run writes its trace through sessions of its own, so this one must hold no write lock (SQLite has one writer) and the conversation must be committed (its foreign key).
            await self.session.commit()
            request = AnswerRequest(message_text=truncate_text(question_text, MESSAGE_TEXT_MAXIMUM_CHARACTERS), client_request_id=uuid.uuid4())
            started = await AskKeiganService(self.session).start(author, conversation_id, request, withheld_tool_names)
            outcome = await started.task
            await self.session.commit()  # ends the read transaction that began before the run: the run has written since, and a stale snapshot may not write
            return await self._text_to_post(outcome, author.preferred_locale)  # the language the run answered in
        except ForbiddenException:
            raise
        except KeiganException as refusal:
            logger.warning("Keigan did not answer a Teams question (%s); the room gets the investigation's own findings.", AskKeiganErrorCatalogue.code_for_exception(refusal))
        except Exception:  # noqa: BLE001 - a chat answer must never break the poller
            logger.exception("Answering a Teams question failed (%s); the room gets the investigation's own findings.", INTERNAL_ERROR)
        return None

    async def _text_to_post(self, outcome: AnswerOutcome, language_code: str | None) -> str | None:
        if outcome.status is not ChatAnswerRunStatus.COMPLETED or outcome.assistant_message_id is None:
            logger.warning("Keigan did not answer a Teams question (%s); the room gets the investigation's own findings.", outcome.error_code or outcome.stop_reason.value)
            return None
        message = await self.session.get(ConversationMessage, outcome.assistant_message_id)
        return None if message is None else self._with_sources_and_caution(message, language_code)

    @staticmethod
    def _with_sources_and_caution(message: ConversationMessage, language_code: str | None) -> str:
        """A citation code means nothing in a room that cannot open the trace, so the answer names its sources; one that checked nothing says so, as the web page does."""
        payload = message.message_payload_json or {}
        parts = [message.message_text]
        if payload.get(_UNVERIFIED_KEY):
            parts.append(translate(language_code, "chat.unverified_notice"))
        sources = "; ".join(f"[{citation['code']}] {citation['title']}" for citation in payload.get(_CITATIONS_KEY, []))
        if sources:
            parts.append(f"{translate(language_code, 'chat.sources_label')}: {sources}")
        return "\n\n".join(parts)

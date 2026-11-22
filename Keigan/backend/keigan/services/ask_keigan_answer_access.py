"""Who may still see an answer of Ask Keigan (spec 23, 6.6).

A run records the applications whose data reached the model (``ChatAnswerRun.used_application_ids_json``). A person who can no longer read any one of them sees none of the
run: not its answer, notes, citation titles, follow-ups, steps or step outputs, even the steps on an application they can still read, because the answer joins them.
Two places ask: one run (the snapshot, the output of a step) and the messages of a conversation.

A withheld answer is replaced by one sentence in the person's language and keeps only its link to its run. The screen then asks for the run, is refused, and shows the same
caption it shows for any run it may not show (``trace.redacted``). The question stays: it is the person's own words.

An answer of the old chat router has no run. It is tied to an application only when its payload names one (``conversationContext.applicationId``); a knowledge answer over
several applications names none and stays visible, as it was.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.incident_entities import ChatAnswerRun, ConversationMessage
from keigan.entities.status_values import MessageAuthorRole
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_trace import ANSWER_RUN_ID_KEY
from keigan.services.authorization_service import AuthorizationService
from keigan.utils.string_table import translate

_ACCESS_LOST_NOTICE = "ask_keigan_answers.access_lost"


@dataclass(frozen=True)
class WithheldAnswer:
    """What replaces an answer the person may no longer see: ``message_payload`` is only the link to its run (None for an answer that has no run)."""

    message_text: str
    message_payload: dict[str, Any] | None


class AnswerAccess:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_run_readable(self, current_user: CurrentUser, run: ChatAnswerRun) -> None:
        """Raises ``ForbiddenException`` when the run used an application the person can no longer read."""
        used_application_ids = set(run.used_application_ids_json or ())
        if used_application_ids and not used_application_ids <= await AuthorizationService(self.session).readable_application_ids(current_user):
            raise ForbiddenException(_notice(current_user))

    async def withheld_answers(self, current_user: CurrentUser, conversation_id: str, messages: Sequence[ConversationMessage]) -> dict[str, WithheldAnswer]:
        """The answers among ``messages`` (all of one conversation) that the person may no longer see, by message id."""
        runs = (await self.session.execute(
            select(ChatAnswerRun.answer_run_id, ChatAnswerRun.assistant_message_id, ChatAnswerRun.used_application_ids_json)
            .where(ChatAnswerRun.conversation_id == conversation_id, ChatAnswerRun.assistant_message_id.is_not(None))
        )).all()
        run_by_answer_message_id = {run.assistant_message_id: run for run in runs}
        answers_by_message_id: dict[str, tuple[str | None, set[str]]] = {}
        for message in messages:
            if message.author_role != MessageAuthorRole.ASSISTANT:
                continue
            run = run_by_answer_message_id.get(message.message_id)
            used_application_ids = set(run.used_application_ids_json or ()) if run else _application_of_an_old_answer(message)
            if used_application_ids:
                answers_by_message_id[message.message_id] = (run.answer_run_id if run else None, used_application_ids)
        if not answers_by_message_id:
            return {}
        readable_application_ids = await AuthorizationService(self.session).readable_application_ids(current_user)
        notice = _notice(current_user)
        return {
            message_id: WithheldAnswer(notice, {ANSWER_RUN_ID_KEY: answer_run_id} if answer_run_id else None)
            for message_id, (answer_run_id, used_application_ids) in answers_by_message_id.items()
            if not used_application_ids <= readable_application_ids
        }


def _notice(current_user: CurrentUser) -> str:
    return translate(current_user.preferred_locale, _ACCESS_LOST_NOTICE)


def _application_of_an_old_answer(message: ConversationMessage) -> set[str]:
    context = (message.message_payload_json or {}).get("conversationContext") or {}
    application_id = context.get("applicationId")
    return {application_id} if application_id else set()

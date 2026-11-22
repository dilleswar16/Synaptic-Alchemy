"""keigan/services/ask_keigan_answer_access.py: a person who can no longer read an application an answer used does not see that answer (spec 23, 6.6)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import ChatAnswerRun, ConversationMessage
from keigan.entities.status_values import ChatAnswerRunStatus, MessageAuthorRole
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_answer_access import AnswerAccess
from support.chat_answer_runs import StoredAnswerRun, store_answer_run

pytestmark = pytest.mark.usefixtures("seed_context")

OWNER = "access.owner@keigan.local"
NOTICE = "You no longer have access to an application this answer used."


def person(*group_names: str, locale: str | None = None) -> CurrentUser:
    return CurrentUser(OWNER, OWNER, OWNER, frozenset(group_names), frozenset(), False, preferred_locale=locale)


READS_CLMJP_AND_PAYAU = person("CLMJP_reader", "PAYAU_reader")
READS_CLMJP_ONLY = person("CLMJP_reader")
READS_PAYAU_ONLY = person("PAYAU_reader")
READS_NOTHING = person()


async def stored(used: list[str] | None, *, answer_text: str | None = "CLMJP has 2 SLOs at risk [T1].") -> StoredAnswerRun:
    async with open_session() as session:
        return await store_answer_run(session, owner=OWNER, used_application_ids=used, answer_text=answer_text, run_status=ChatAnswerRunStatus.COMPLETED)


async def withheld_for(current_user: CurrentUser, stored_run: StoredAnswerRun):
    async with open_session() as session:
        messages = list((await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == stored_run.conversation_id).order_by(ConversationMessage.created_at))).all())
        return await AnswerAccess(session).withheld_answers(current_user, stored_run.conversation_id, messages)


async def ensure_run_readable(current_user: CurrentUser, stored_run: StoredAnswerRun) -> None:
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, stored_run.answer_run_id)
        await AnswerAccess(session).ensure_run_readable(current_user, run)


# ── One run: the snapshot and the output of a step ─────────────────────────────────────────────────────────────────────────────
async def test_a_person_who_can_still_read_every_application_the_run_used_may_read_it(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]])
    await ensure_run_readable(READS_CLMJP_AND_PAYAU, run)


async def test_a_person_who_lost_one_of_the_applications_the_run_used_may_not_read_it(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]])
    for person_who_lost_one in (READS_CLMJP_ONLY, READS_PAYAU_ONLY, READS_NOTHING):
        with pytest.raises(ForbiddenException, match="no longer have access"):
            await ensure_run_readable(person_who_lost_one, run)


async def test_losing_an_application_the_run_did_not_use_changes_nothing(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"]])
    await ensure_run_readable(READS_CLMJP_ONLY, run)


async def test_a_run_that_used_no_application_is_never_withheld() -> None:
    run = await stored([])
    await ensure_run_readable(READS_NOTHING, run)
    assert await withheld_for(READS_NOTHING, run) == {}


async def test_a_run_stored_before_the_applications_were_recorded_is_left_to_the_guard_of_its_conversation() -> None:
    run = await stored(None)
    await ensure_run_readable(READS_NOTHING, run)
    assert await withheld_for(READS_NOTHING, run) == {}


async def test_the_refusal_is_in_the_language_of_the_person(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"]])
    with pytest.raises(ForbiddenException) as english:
        await ensure_run_readable(person(locale="en"), run)
    with pytest.raises(ForbiddenException) as japanese:
        await ensure_run_readable(person(locale="ja"), run)
    assert english.value.detail == NOTICE
    assert japanese.value.detail != english.value.detail and "アクセス" in japanese.value.detail


# ── One conversation: which answers are withheld, and what replaces them ──────────────────────────────────────────────────────
async def test_the_answer_of_a_run_that_used_a_lost_application_is_withheld_and_keeps_only_its_link_to_the_run(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]])
    withheld = await withheld_for(READS_CLMJP_ONLY, run)
    assert set(withheld) == {run.assistant_message_id}
    answer = withheld[run.assistant_message_id]
    assert answer.message_text == NOTICE
    assert answer.message_payload == {"answerRunId": run.answer_run_id}


async def test_nothing_is_withheld_from_a_person_who_can_read_what_the_answer_used(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]])
    assert await withheld_for(READS_CLMJP_AND_PAYAU, run) == {}


async def test_the_question_of_a_withheld_answer_stays_because_it_is_the_persons_own_words(seed_context) -> None:
    run = await stored([seed_context.application_ids_by_code["CLMJP"]])
    assert run.user_message_id not in await withheld_for(READS_NOTHING, run)


async def test_a_conversation_keeps_the_answers_the_person_may_still_read_and_withholds_the_others(seed_context) -> None:
    clmjp, payau = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    first = await stored([clmjp])
    async with open_session() as session:
        second = await store_answer_run(session, conversation_id=first.conversation_id, used_application_ids=[clmjp, payau], answer_text="PAYAU is burning budget [T1].", run_status=ChatAnswerRunStatus.COMPLETED)
        messages = list((await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == first.conversation_id))).all())
        withheld = await AnswerAccess(session).withheld_answers(READS_CLMJP_ONLY, first.conversation_id, messages)
    assert set(withheld) == {second.assistant_message_id}


# ── Answers of the old router (no run row) ────────────────────────────────────────────────────────────────────────────────────
async def old_router_answer(payload: dict | None) -> StoredAnswerRun:
    async with open_session() as session:
        run = await store_answer_run(session, owner=OWNER, used_application_ids=[])
        message = ConversationMessage(conversation_id=run.conversation_id, author_role=MessageAuthorRole.ASSISTANT, message_text="42 requests failed on claims-api.", message_payload_json=payload)
        session.add(message)
        await session.flush()
        return StoredAnswerRun(run.conversation_id, run.user_message_id, "", message.message_id)


async def test_an_old_answer_that_is_tied_to_one_application_is_withheld_from_a_person_who_lost_it(seed_context) -> None:
    old = await old_router_answer({"answerKind": "number", "numberValue": 42, "conversationContext": {"applicationId": seed_context.application_ids_by_code["CLMJP"]}})
    withheld = await withheld_for(READS_PAYAU_ONLY, old)
    assert withheld[old.assistant_message_id].message_payload is None and withheld[old.assistant_message_id].message_text == NOTICE
    assert await withheld_for(READS_CLMJP_ONLY, old) == {}


async def test_an_old_answer_that_cannot_be_tied_to_an_application_is_left_as_it_was() -> None:
    for payload in ({"answerKind": "text"}, {"answerKind": "text", "conversationContext": None}, None):
        old = await old_router_answer(payload)
        assert await withheld_for(READS_NOTHING, old) == {}

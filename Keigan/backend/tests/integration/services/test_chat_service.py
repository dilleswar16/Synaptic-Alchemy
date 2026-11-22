"""keigan/services/chat_service.py: investigation chats (masking before storage V12, access, the Teams answer contract), suggested prompts, and the access notice of older answers."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
from keigan.config.database_config import open_session
from keigan.entities.all_entities import Application, Conversation, ConversationMessage
from keigan.services.chat_service import ChatService
from keigan.utils.time_utils import utc_now
from support import users
from support.http import AuthHeaders
from support.chat_answer_runs import store_answer_run

EMAIL = "taro.yamada@example.co.jp"


async def new_conversation(client: httpx.AsyncClient, headers: dict[str, str], scope: str = "keigan_ai_chat", **extra: Any) -> str:
    response = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": scope, **extra})
    assert response.status_code == 201, response.text
    return response.json()["conversationId"]


async def test_a_users_message_of_an_investigation_chat_is_masked_before_it_is_stored(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.chat_service import AssistantAnswer

    async def fake_answer(self: ChatService, investigation_id: str, question_text: str, **kwargs: Any) -> AssistantAnswer:
        return AssistantAnswer("ok")

    monkeypatch.setattr(ChatService, "answer_investigation_question", fake_answer)
    conversation_id = await investigation_conversation_owned_by(seed_context, users.CLMJP_ADMIN_CHAD_READER)
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    response = await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": f"Why did {EMAIL} see errors?"})
    assert response.status_code == 200, response.text
    detail = (await client.get(f"/api/chat/conversations/{conversation_id}", headers=headers)).json()
    assert EMAIL not in str(detail)
    assert "<EMAIL_1>" in next(message["messageText"] for message in detail["messages"] if message["authorRole"] == "user")


async def test_stored_messages_of_an_investigation_conversation_are_masked_in_the_history(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_answer(self: ChatService, investigation_id: str, question_text: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        from keigan.services.chat_service import AssistantAnswer

        return AssistantAnswer("ok")

    monkeypatch.setattr(ChatService, "answer_investigation_question", fake_answer)
    async with open_session() as session:
        from keigan.entities.all_entities import Conversation, Investigation

        investigation = Investigation(application_id=seed_context.application_ids_by_code["CLMJP"])
        session.add(investigation)
        await session.flush()
        conversation = Conversation(conversation_scope="investigation", investigation_id=investigation.investigation_id, owner_user_principal_name="owner@keigan.local", conversation_title="Investigation chat")
        session.add(conversation)
        await session.flush()
        session.add(ConversationMessage(conversation_id=conversation.conversation_id, author_role="user", message_text=f"Old unmasked message from {EMAIL}"))
        conversation_id = conversation.conversation_id
    async with open_session() as session:
        from keigan.dtos.chat_dtos import SendMessageRequest
        from keigan.security.current_user import CurrentUser

        owner = CurrentUser("owner@keigan.local", "Owner", None, frozenset(), frozenset(), True)
        await ChatService(session).send_message(owner, conversation_id, SendMessageRequest(message_text="And now?"))
    assert EMAIL not in str(seen["conversation_history"])


async def investigation_conversation_owned_by(seed_context, owner_principal_name: str) -> str:
    """An investigation chat on CLMJP that already exists, as if the owner had access when it was opened."""
    from keigan.entities.all_entities import Conversation, Investigation

    async with open_session() as session:
        investigation = Investigation(application_id=seed_context.application_ids_by_code["CLMJP"])
        session.add(investigation)
        await session.flush()
        conversation = Conversation(conversation_scope="investigation", investigation_id=investigation.investigation_id, owner_user_principal_name=owner_principal_name, conversation_title="Investigation chat")
        session.add(conversation)
        await session.flush()
        session.add(ConversationMessage(conversation_id=conversation.conversation_id, author_role="assistant", message_text="Earlier answer about claims-api"))
        return conversation.conversation_id


async def test_a_person_whose_access_to_the_application_was_removed_cannot_send_to_their_investigation_chat(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    conversation_id = await investigation_conversation_owned_by(seed_context, users.NO_ACCESS)
    headers = await auth_headers(users.NO_ACCESS)
    response = await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": "What did you find?"})
    assert response.status_code == 403, response.text
    async with open_session() as session:
        from sqlalchemy import func, select

        stored = await session.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))
    assert stored == 1, "a refused message must not be stored"


async def test_a_person_whose_access_to_the_application_was_removed_cannot_read_their_earlier_investigation_chat(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    conversation_id = await investigation_conversation_owned_by(seed_context, users.NO_ACCESS)
    response = await client.get(f"/api/chat/conversations/{conversation_id}", headers=await auth_headers(users.NO_ACCESS))
    assert response.status_code == 403, response.text
    assert "Earlier answer" not in response.text


async def test_a_person_who_still_has_access_can_read_and_send_in_their_investigation_chat(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.services.chat_service import AssistantAnswer

    async def fake_answer(self: ChatService, investigation_id: str, question_text: str, **kwargs: Any) -> AssistantAnswer:
        return AssistantAnswer("ok")

    monkeypatch.setattr(ChatService, "answer_investigation_question", fake_answer)
    conversation_id = await investigation_conversation_owned_by(seed_context, users.CLMJP_ADMIN_CHAD_READER)
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    assert (await client.get(f"/api/chat/conversations/{conversation_id}", headers=headers)).status_code == 200
    assert (await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": "Anything new?"})).status_code == 200


async def test_a_person_without_access_can_still_delete_their_own_investigation_chat(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    conversation_id = await investigation_conversation_owned_by(seed_context, users.NO_ACCESS)
    response = await client.delete(f"/api/chat/conversations/{conversation_id}", headers=await auth_headers(users.NO_ACCESS))
    assert response.status_code in (200, 204), response.text


async def test_deleting_a_conversation_also_removes_the_answer_runs_and_steps_stored_for_its_questions(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    from sqlalchemy import func, select

    from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep
    from keigan.entities.status_values import ChatAnswerRunStatus

    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    conversation_id = await new_conversation(client, headers)
    async with open_session() as session:
        stored = await store_answer_run(session, conversation_id=conversation_id, run_status=ChatAnswerRunStatus.COMPLETED)
    response = await client.delete(f"/api/chat/conversations/{conversation_id}", headers=headers)
    assert response.status_code in (200, 204), response.text
    async with open_session() as session:
        assert await session.scalar(select(func.count()).select_from(ChatAnswerRun).where(ChatAnswerRun.answer_run_id == stored.answer_run_id)) == 0
        assert await session.scalar(select(func.count()).select_from(ChatRunStep).where(ChatRunStep.answer_run_id == stored.answer_run_id)) == 0
        assert await session.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id)) == 0


async def test_the_contract_the_teams_bot_uses_answers_from_the_investigation_with_its_citations(seed_context) -> None:
    from support.ask_keigan_conversations import seed_investigation

    investigation = await seed_investigation(seed_context.application_ids_by_code["CLMJP"])
    async with open_session() as session:
        answer = await ChatService(session).answer_investigation_question(investigation.investigation_id, "Which evidence did you collect?", asked_by_user_principal_name="teams.user@keigan.local")
    assert answer.answer_markdown == "Evidence collected:\n\n- [E1] Error spike on claims-api\n- [E2] Release 41 deployed"
    assert answer.citations == [
        {"kind": "evidence", "title": "Error spike on claims-api", "reference": "E1"}, {"kind": "evidence", "title": "Release 41 deployed", "reference": "E2"},
    ]
    assert answer.message_payload == {"answerKind": "text", "citations": answer.citations}
    assert answer.input_token_count > 0 and answer.output_token_count > 0


async def test_the_suggested_prompts_show_the_breadth_of_what_the_chat_can_answer_for_the_selected_application(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    from sqlalchemy import select

    from keigan.entities.all_entities import MonitoredService

    clmjp_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        application_name = (await session.get(Application, clmjp_id)).application_name
        service_name = (await session.scalar(select(MonitoredService.service_name).where(MonitoredService.application_id == clmjp_id).order_by(MonitoredService.service_name).limit(1)))
    response = await client.get("/api/chat/suggested-prompts", params={"applicationId": clmjp_id}, headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))
    assert response.status_code == 200, response.text
    assert [(prompt["promptText"], prompt["category"]) for prompt in response.json()] == [
        ("Which SLOs are at risk right now?", "data"), ("Are there open P1 or P2 incidents?", "data"), (f"What changed on {application_name} in the last day?", "data"),
        (f"Show failed requests on {service_name} in the last 24 hours", "data"), ("Which predictive signals are open?", "data"),
        ("What is the runbook for a database connection failure?", "knowledge"),
    ]


# ── A person who lost access to an application no longer re-reads the answers that used it (the access gap of the Keigan AI chat) ──
ACCESS_LOST_NOTICE = "You no longer have access to an application this answer used."


async def global_conversation_with_an_answer(seed_context, owner: str, used_codes: list[str], answer_text: str = "CLMJP and PAYAU both have SLOs at risk [T1] [T2].") -> Any:
    used_application_ids = [seed_context.application_ids_by_code[code] for code in used_codes]
    async with open_session() as session:
        return await store_answer_run(session, owner=owner, used_application_ids=used_application_ids, answer_text=answer_text, run_status="completed")


async def read_conversation(client: httpx.AsyncClient, headers: dict[str, str], conversation_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/chat/conversations/{conversation_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["messages"]


async def test_a_person_who_cannot_read_an_application_an_earlier_global_answer_used_sees_a_notice_instead_of_the_answer(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    owner = users.CLMJP_AND_PAYAU_READER  # reads CLMJP and PAYAU, not CHAD
    stored = await global_conversation_with_an_answer(seed_context, owner, ["CLMJP", "CHAD"])
    question, answer = await read_conversation(client, await auth_headers(owner), stored.conversation_id)
    assert question["messageText"] == "Which SLOs are at risk?" and question["authorRole"] == "user"
    assert answer["authorRole"] == "assistant" and answer["messageText"] == ACCESS_LOST_NOTICE
    assert answer["messagePayload"] == {"answerRunId": stored.answer_run_id}
    assert "SLOs at risk [T1]" not in str(answer) and "Checked SLO status" not in str(answer) and "Which alerts fired" not in str(answer)


async def test_a_person_who_can_still_read_every_application_the_answer_used_sees_the_whole_answer(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    owner = users.CLMJP_ADMIN_CHAD_READER  # reads CLMJP and CHAD
    stored = await global_conversation_with_an_answer(seed_context, owner, ["CLMJP", "CHAD"])
    _, answer = await read_conversation(client, await auth_headers(owner), stored.conversation_id)
    assert answer["messageText"] == "CLMJP and PAYAU both have SLOs at risk [T1] [T2]."
    assert answer["messagePayload"]["citations"] == [{"code": "T1", "title": "Checked SLO status"}] and answer["messagePayload"]["followUps"] == ["Which alerts fired?"]


async def test_an_answer_that_used_only_applications_the_person_can_read_stays_even_when_they_lost_others(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    owner = users.CLMJP_AND_PAYAU_READER
    stored = await global_conversation_with_an_answer(seed_context, owner, ["CLMJP"], "CLMJP has 2 SLOs at risk [T1].")
    _, answer = await read_conversation(client, await auth_headers(owner), stored.conversation_id)
    assert answer["messageText"] == "CLMJP has 2 SLOs at risk [T1]."


async def test_a_person_with_no_access_at_all_sees_a_notice_for_every_answer_that_used_an_application(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    stored = await global_conversation_with_an_answer(seed_context, users.NO_ACCESS, ["CLMJP"], "CLMJP has 2 SLOs at risk [T1].")
    _, answer = await read_conversation(client, await auth_headers(users.NO_ACCESS), stored.conversation_id)
    assert answer["messageText"] == ACCESS_LOST_NOTICE and "SLOs" not in str(answer["messagePayload"])


async def test_an_answer_of_the_old_router_that_was_about_a_lost_application_is_hidden_and_one_about_no_application_is_not(seed_context, client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    owner = users.CLMJP_AND_PAYAU_READER
    async with open_session() as session:
        conversation = Conversation(conversation_scope="keigan_ai_chat", owner_user_principal_name=owner)
        session.add(conversation)
        await session.flush()
        chad_id = seed_context.application_ids_by_code["CHAD"]
        session.add_all([
            ConversationMessage(conversation_id=conversation.conversation_id, author_role="assistant", message_text="CHAD served 4,100 requests.", created_at=utc_now(),
                                message_payload_json={"answerKind": "number", "numberValue": 4100, "conversationContext": {"applicationId": chad_id}}),
            ConversationMessage(conversation_id=conversation.conversation_id, author_role="assistant", message_text="Which service do you mean?", created_at=utc_now() + timedelta(milliseconds=1),
                                message_payload_json={"answerKind": "text"}),
        ])
        conversation_id = conversation.conversation_id
    hidden, kept = await read_conversation(client, await auth_headers(owner), conversation_id)
    assert (hidden["messageText"], hidden["messagePayload"]) == (ACCESS_LOST_NOTICE, None) and kept["messageText"] == "Which service do you mean?"

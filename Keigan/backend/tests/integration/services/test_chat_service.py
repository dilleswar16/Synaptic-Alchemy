"""keigan/services/chat_service.py: masking before storage (V12), sanitised and cited knowledge answers (V7, V8, V20), user-safe errors (V19)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from keigan.ai.chat_ai_schemas import ChatQueryResult
from keigan.ai.llm_gateway import LlmCallResult, LlmGateway, LlmUsageContext
from keigan.config.database_config import open_session
from keigan.entities.all_entities import Application, ConversationMessage
from keigan.entities.knowledge_entities import KnowledgeChunk, KnowledgeDocument
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.services.chat_service import ChatService
from keigan.utils.text_utils import term_frequencies
from support import users
from support.http import AuthHeaders
from support.chat_answer_runs import store_answer_run

EMAIL = "taro.yamada@example.co.jp"


async def new_conversation(client: httpx.AsyncClient, headers: dict[str, str], scope: str = "keigan_ai_chat", **extra: Any) -> str:
    response = await client.post("/api/chat/conversations", headers=headers, json={"conversationScope": scope, **extra})
    assert response.status_code == 201, response.text
    return response.json()["conversationId"]


async def test_a_users_message_and_the_conversation_title_are_masked_before_they_are_stored(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    conversation_id = await new_conversation(client, headers)
    response = await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": f"Why did {EMAIL} see errors on claims-api in the last hour?"})
    assert response.status_code == 200, response.text
    detail = (await client.get(f"/api/chat/conversations/{conversation_id}", headers=headers)).json()
    assert EMAIL not in str(detail)
    assert "<EMAIL_1>" in detail["messages"][0]["messageText"]
    assert "<EMAIL_1>" in detail["conversationTitle"]


async def test_a_failure_while_answering_shows_the_user_no_internal_error_text(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    async def explode(self: object, *args: object, **kwargs: object) -> None:
        raise IntegrationException("Elastic at es-prod.internal:9200 returned 500 for index claims-secret")

    monkeypatch.setattr(ChatService, "_answer_keigan_question", explode)
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    conversation_id = await new_conversation(client, headers)
    response = await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": "How many requests failed?"})
    assert response.status_code == 200
    assert "es-prod.internal" not in response.text and "claims-secret" not in response.text
    assert "reference" in response.json()["messageText"]


async def test_a_question_the_model_cannot_turn_into_a_query_shows_the_models_explanation(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    original_generate_structured = LlmGateway.generate_structured

    async def generate_structured_without_a_query(self: LlmGateway, **kwargs: Any) -> Any:
        if kwargs["feature_name"] == "ai_chat_query_generation":
            return ChatQueryResult(query_text="", explanation="Sign-up counts are not in the logs of this service.")
        return await original_generate_structured(self, **kwargs)

    monkeypatch.setattr(LlmGateway, "generate_structured", generate_structured_without_a_query)
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    conversation_id = await new_conversation(client, headers)
    response = await client.post(f"/api/chat/conversations/{conversation_id}/messages", headers=headers, json={"messageText": "How many requests failed on claims-api in the last 3 hours?"})
    assert response.status_code == 200, response.text
    assert response.json()["messageText"] == "I can't answer that from the logs of claims-api. Sign-up counts are not in the logs of this service."


async def add_document(application_id: str, marker: str, chunk_text: str) -> None:
    async with open_session() as session:
        document = KnowledgeDocument(
            application_id=application_id, document_title=f"Doc {marker}", document_category="architecture", original_file_name=f"{marker}.md", content_type="text/markdown", storage_path=f"x/{marker}.md",
            file_sha256_hash=uuid.uuid4().hex + uuid.uuid4().hex, ai_digest_markdown=f"Digest about {marker}", ai_digest_status="ready",
        )
        session.add(document)
        await session.flush()
        session.add(KnowledgeChunk(knowledge_document_id=document.knowledge_document_id, application_id=application_id, chunk_sequence_number=0, chunk_text=chunk_text, search_terms_json=term_frequencies(chunk_text)))


async def test_a_knowledge_answer_is_sanitised_and_keeps_only_real_citations(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = f"zq{uuid.uuid4().hex[:8]}"
    application_id = seed_context.application_ids_by_code["CLMJP"]
    await add_document(application_id, marker, f"The {marker} component handles settlement retries.")
    seen: dict[str, Any] = {}

    async def fake_generate_text(self: object, **kwargs: Any) -> LlmCallResult:
        seen.update(kwargs)
        return LlmCallResult(text="Settlement retries are handled [K1] and [K9]. See [more](https://evil.example/x) ![p](https://evil.example/p.png).")

    monkeypatch.setattr(LlmGateway, "is_mock", property(lambda self: False))
    monkeypatch.setattr(LlmGateway, "generate_text", fake_generate_text)
    async with open_session() as session:
        application = await session.get(Application, application_id)
        answer = await ChatService(session)._answer_knowledge(f"How are {marker} settlement retries handled?", application, [application], LlmUsageContext(application_id=application_id))
    assert "[K1]" in answer.answer_markdown and "[K9]" not in answer.answer_markdown
    assert "](https://evil.example" not in answer.answer_markdown and "![" not in answer.answer_markdown
    knowledge_section = next(section for section in seen["prompt_sections"] if section.title == "Application knowledge")
    assert knowledge_section.is_untrusted
    assert seen["feature_name"] == "ai_chat_knowledge_answer"


async def test_the_knowledge_answer_prompt_is_a_versioned_prompt_file() -> None:
    from keigan.config import application_context

    assert application_context.prompt_library().version_of("ai_chat_knowledge_answer") == "1"


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

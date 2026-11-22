"""Store one answered question of Ask Keigan (conversation, question, run and two steps) so a test can check how it is read or removed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.status_values import ChatAnswerRunStatus, ChatRunStepKind, ChatRunStepStatus, ConversationScope, MessageAuthorRole, ToolCallingMode

OWNER = "aiko.appadmin@keigan.local"


@dataclass(frozen=True)
class StoredAnswerRun:
    conversation_id: str
    user_message_id: str
    answer_run_id: str


async def store_answer_run(
    session: AsyncSession,
    *,
    conversation_id: str | None = None,
    conversation_scope: ConversationScope = ConversationScope.KEIGAN_AI_CHAT,
    investigation_id: str | None = None,
    client_request_id: str | None = None,
    started_at: datetime | None = None,
    run_status: ChatAnswerRunStatus = ChatAnswerRunStatus.RUNNING,
) -> StoredAnswerRun:
    """A run with one model turn and one tool call. Without ``conversation_id`` a new conversation is created for it. A ``running`` run counts as one another process is working on."""
    if conversation_id is None:
        conversation = Conversation(conversation_scope=conversation_scope, investigation_id=investigation_id, owner_user_principal_name=OWNER)
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.conversation_id
    question = ConversationMessage(conversation_id=conversation_id, author_role=MessageAuthorRole.USER, message_text="Which SLOs are at risk?")
    session.add(question)
    await session.flush()
    run_values = {"started_at": started_at} if started_at else {}
    run = ChatAnswerRun(
        conversation_id=conversation_id, user_message_id=question.message_id, client_request_id=client_request_id or uuid.uuid4().hex, conversation_scope=conversation_scope,
        investigation_id=investigation_id, requested_by_user_principal_name=OWNER, scope_snapshot_json={"scope": "global", "applications": [], "boundArguments": {}, "withheldTools": []},
        run_status=run_status, engine_version="1", prompt_key="ask_keigan_global", prompt_version="1", system_prompt_sha256="0" * 64, tool_catalog_sha256="1" * 64,
        offered_tools_json=[], provider_name="mock", model_name="mock", model_tier="deep", tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK, limits_json={"maximumToolCalls": 8}, **run_values,
    )
    session.add(run)
    await session.flush()
    model_turn = ChatRunStep(answer_run_id=run.answer_run_id, sequence_number=1, step_kind=ChatRunStepKind.MODEL_TURN, step_status=ChatRunStepStatus.SUCCEEDED, turn_number=1)
    session.add(model_turn)
    await session.flush()
    session.add(ChatRunStep(
        answer_run_id=run.answer_run_id, sequence_number=2, step_kind=ChatRunStepKind.TOOL_CALL, step_status=ChatRunStepStatus.SUCCEEDED, parent_run_step_id=model_turn.run_step_id,
        tool_name="get_slo_status", citation_code="T1",
    ))
    await session.flush()
    return StoredAnswerRun(conversation_id, question.message_id, run.answer_run_id)

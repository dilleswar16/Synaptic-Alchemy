"""Run one Ask Keigan answer end to end in a test: a conversation, the question, the profile, the engine, and everything the run left behind (events, run row, steps, messages)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select

from keigan.ai.llm_gateway import AgentTextChunk, AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, ModelTier, split_into_chunks
from keigan.ai.model_capabilities import ModelCapabilities, resolve_model_capabilities
from keigan.config.database_config import open_session
from keigan.config.settings import LlmProviderName, Settings, get_settings
from keigan.entities.base_entity import new_identifier
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.status_values import ConversationScope, MessageAuthorRole, ToolCallingMode
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_engine import AnswerOutcome, AnswerRequest, AskKeiganEngine
from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName, RunEventChannel
from keigan.services.ask_keigan_scopes import ScopeProfile, build_investigation_profile
from keigan.services.ask_keigan_trace import QuestionToStore, RunRegistration, TraceRecorder
from keigan.services.ask_keigan_transcript import ConversationTurn
from keigan.utils.pii_masker import PiiMasker


def user(user_principal_name: str, *group_names: str, is_admin: bool = False) -> CurrentUser:
    return CurrentUser(user_principal_name, user_principal_name, user_principal_name, frozenset(group_names), frozenset(), is_admin)


def request_for(tool_name: str, arguments: dict[str, Any] | None, request_id: str = "call_1") -> AgentToolRequest:
    return AgentToolRequest(request_id=request_id, tool_name=tool_name, arguments=arguments)


@dataclass
class Turn:
    """One scripted model turn. ``before`` runs when the turn starts (to change the world between two calls of one answer)."""

    text: str = ""
    requests: tuple[AgentToolRequest, ...] = ()
    finish: str | None = None
    input_tokens: int = 100
    output_tokens: int = 20
    before: Callable[[], Awaitable[None]] | None = None


class ScriptedGateway:
    """The part of ``LlmGateway`` the engine uses, replaying scripted turns (or raising a scripted failure) and recording what it was asked."""

    def __init__(self, script: Sequence[Turn | Exception], *, capabilities: ModelCapabilities | None = None):
        self.settings: Settings = get_settings()
        self._script = list(script)
        self._capabilities = capabilities or resolve_model_capabilities(LlmProviderName.MOCK, "mock")
        self.calls: list[dict[str, Any]] = []

    is_mock = False

    def agent_capabilities(self, model_tier: ModelTier) -> ModelCapabilities:
        return self._capabilities

    def model_name_for(self, model_tier: ModelTier) -> str:
        return "scripted-model"

    async def stream_agent_turn(self, **arguments: Any) -> AsyncIterator[AgentTextChunk | AgentTurnResult]:
        self.calls.append({**arguments, "transcript": list(arguments["transcript"])})
        assert self._script, "the engine asked for a model turn the test did not script"
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        if step.before:
            await step.before()
        for piece in split_into_chunks(step.text, 3):
            yield AgentTextChunk(piece)
        finish = step.finish or ("tool_requests" if step.requests else "answer")
        yield AgentTurnResult(
            text=step.text, tool_requests=step.requests, finish=finish, input_token_count=step.input_tokens, output_token_count=step.output_tokens,  # type: ignore[arg-type]
            token_counts_estimated=False, model_name="scripted-model", tool_calling_mode=ToolCallingMode.NATIVE,
        )

    def tool_results_seen_in_call(self, call_index: int) -> list[AgentTranscriptEntry]:
        return [entry for entry in self.calls[call_index]["transcript"] if entry.kind == "tool_result"]

    @property
    def offered_tools(self) -> tuple[AgentToolSpec, ...]:
        return tuple(self.calls[0]["tools"])


@dataclass
class Finished:
    outcome: AnswerOutcome
    events: list[AnswerEvent]
    run: ChatAnswerRun
    steps: list[ChatRunStep]
    messages: list[ConversationMessage]
    conversation_id: str
    user_message_id: str
    prepared_system_prompt: str

    def names(self) -> list[AnswerEventName]:
        return [event.name for event in self.events]

    def of(self, name: AnswerEventName) -> list[AnswerEvent]:
        return [event for event in self.events if event.name is name]

    @property
    def tool_steps(self) -> list[ChatRunStep]:
        return [step for step in self.steps if step.step_kind == "tool_call"]

    @property
    def assistant_messages(self) -> list[ConversationMessage]:
        return [message for message in self.messages if message.author_role == MessageAuthorRole.ASSISTANT]

    @property
    def question_message(self) -> ConversationMessage:
        return next(message for message in self.messages if message.message_id == self.user_message_id)


async def ask(
    profile: ScopeProfile, question: str, *, current_user: CurrentUser, gateway: ScriptedGateway | None = None, history: Sequence[ConversationTurn] = (),
    flag: CancellationFlag | None = None, on_event: Callable[[AnswerEvent, CancellationFlag], None] | None = None,
) -> Finished:
    engine = AskKeiganEngine(gateway) if gateway else AskKeiganEngine()
    prepared = engine.prepare(profile, current_user.preferred_locale)
    masker = PiiMasker()
    masked_question = masker.mask_text(question)
    async with open_session() as session:
        conversation = Conversation(conversation_scope=ConversationScope(profile.conversation_scope), investigation_id=profile.investigation_id, owner_user_principal_name=current_user.user_principal_name)
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.conversation_id
    run_id = new_identifier()
    channel = RunEventChannel(run_id)
    recorder = await TraceRecorder.begin(
        RunRegistration(
            answer_run_id=run_id, conversation_id=conversation_id, question=QuestionToStore(masked_question, current_user.display_name, current_user.user_principal_name),
            client_request_id=uuid.uuid4().hex, conversation_scope=profile.conversation_scope, investigation_id=profile.investigation_id,
            requested_by_user_principal_name=current_user.user_principal_name, scope_snapshot=profile.snapshot(), setup=prepared.setup,
        ),
        channel, masker,
    )
    cancellation = flag or CancellationFlag()
    events: list[AnswerEvent] = []

    async def read_events() -> None:
        async for event in channel.events():
            events.append(event)
            if on_event:
                on_event(event, cancellation)

    reader = asyncio.create_task(read_events())
    outcome = await engine.run(prepared, AnswerRequest(current_user, conversation_id, masked_question, tuple(history), masker), recorder, cancellation)
    await asyncio.wait_for(reader, timeout=5)  # the engine closes the channel when the run ends
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, run_id)
        user_message_id = run.user_message_id
        steps = list((await session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == run_id).order_by(ChatRunStep.sequence_number))).all())
        messages = list((await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.created_at))).all())
    return Finished(outcome, events, run, steps, messages, conversation_id, user_message_id, prepared.system_prompt)


async def profile_for(current_user: CurrentUser, investigation_id: str) -> ScopeProfile:
    async with open_session() as session:
        return await build_investigation_profile(session, replace(current_user, application_roles_by_application_id=None), investigation_id)

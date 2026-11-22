"""Runs one conformance scenario through the real Ask Keigan engine and reports what happened (spec 23, 4.6.6).

The engine, the tool registry, the trace and the database are the production ones; only the model is chosen by the caller (the offline planner, a scripted model, or a real
provider behind ``LlmGateway``). The gateway handed in is wrapped to see each model turn (tokens, how many tools were requested at once, how many text pieces streamed), which
is where the capability observations of the report come from. The runner makes its own conversation and run rows in the database it is given: use a throw-away one.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import contextmanager

from sqlalchemy import select

from keigan.ai.ask_keigan_answer_format import FixedAnswer, fixed_answer
from keigan.ai.llm_gateway import AgentTextChunk, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, LlmUsageContext, ModelTier
from keigan.ai.model_capabilities import ModelCapabilities
from keigan.config.database_config import open_session
from keigan.config.settings import Settings, get_settings
from keigan.entities.base_entity import new_identifier
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation, ConversationMessage
from keigan.entities.status_values import ChatRunStepKind, ChatRunStepStatus, ConversationScope
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_conformance_checks import ObservedCall, ObservedRun, ObservedTurn, evaluate
from keigan.services.ask_keigan_conformance_fixtures import fixture_named
from keigan.services.ask_keigan_conformance_report import ScenarioReport, scenario_report
from keigan.services.ask_keigan_conformance_scenarios import Scenario, ScenarioMode
from keigan.services.ask_keigan_engine import AnswerRequest, AskKeiganEngine
from keigan.services.ask_keigan_events import AnswerEvent, AnswerEventName, RunEventChannel
from keigan.services.ask_keigan_prepared_run import AgentGateway
from keigan.services.ask_keigan_scopes import ScopeProfile, build_global_profile, build_investigation_profile
from keigan.services.ask_keigan_trace import QuestionToStore, RunRegistration, TraceRecorder
from keigan.services.authentication_service import load_local_users
from keigan.utils.pii_masker import PiiMasker

EVENT_READER_TIMEOUT_SECONDS = 5  # the engine closes the channel when the run ends, so the reader ends right after it


class ObservingGateway:
    """The gateway as the engine sees it, remembering how each model turn went."""

    def __init__(self, inner: AgentGateway):
        self._inner = inner
        self.settings: Settings = inner.settings
        self.turns: list[ObservedTurn] = []

    @property
    def is_mock(self) -> bool:
        return self._inner.is_mock

    def agent_capabilities(self, model_tier: ModelTier) -> ModelCapabilities:
        return self._inner.agent_capabilities(model_tier)

    def model_name_for(self, model_tier: ModelTier) -> str:
        return self._inner.model_name_for(model_tier)

    async def stream_agent_turn(
        self, *, feature_name: str, model_tier: ModelTier, system_prompt: str, transcript: Sequence[AgentTranscriptEntry], tools: Sequence[AgentToolSpec], allow_tool_requests: bool,
        usage_context: LlmUsageContext,
    ) -> AsyncIterator[AgentTextChunk | AgentTurnResult]:
        chunk_count = 0
        async for item in self._inner.stream_agent_turn(
            feature_name=feature_name, model_tier=model_tier, system_prompt=system_prompt, transcript=transcript, tools=tools, allow_tool_requests=allow_tool_requests, usage_context=usage_context,
        ):
            if isinstance(item, AgentTextChunk):
                chunk_count += 1
            else:
                self.turns.append(ObservedTurn(item.input_token_count, item.output_token_count, item.token_counts_estimated, len(item.tool_requests), chunk_count))
            yield item


def local_user(user_principal_name: str) -> CurrentUser:
    """A demo user of ``local_users.yaml`` as the engine sees the person asking."""
    definition = next(user for user in load_local_users() if user.user_principal_name.lower() == user_principal_name.lower())
    groups = frozenset(definition.group_names)
    is_keigan_admin = get_settings().keigan_admin_group_name.lower() in {group.lower() for group in groups}
    return CurrentUser(definition.user_principal_name, definition.display_name, definition.email_address, groups, frozenset(), is_keigan_admin, preferred_locale=definition.preferred_locale)


@contextmanager
def lowered_limits(limits: dict[str, int]) -> Iterator[None]:
    """The scenario's settings in force while it runs."""
    settings = get_settings()
    originals = {name: getattr(settings, name) for name in limits}
    for name, value in limits.items():
        setattr(settings, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(settings, name, value)


async def _profile(scenario: Scenario, current_user: CurrentUser, investigation_id: str | None) -> ScopeProfile:
    async with open_session() as session:
        if scenario.scope == "investigation":
            if investigation_id is None:
                raise ValueError(f"{scenario.id} is an investigation scenario and its fixture made no investigation")
            return await build_investigation_profile(session, current_user, investigation_id)
        return await build_global_profile(session, current_user, [])


async def run_scenario(scenario: Scenario, gateway_for: Callable[[Scenario], AgentGateway], mode: ScenarioMode) -> tuple[ScenarioReport, ObservedRun]:
    """``gateway_for`` is given the scenario as it will run (its placeholders filled) and returns the gateway whose model answers it. Raises only when the scenario cannot be set up
    (an unknown user or fixture); a run that goes wrong is a failed scenario in the report."""
    async with fixture_named(scenario.fixture) as world:
        current_user = local_user(scenario.user)
        resolved = scenario.resolved({"outside_scope_answer": fixed_answer(FixedAnswer.OUTSIDE_SCOPE, current_user.preferred_locale), **world.variables})
        observing = ObservingGateway(gateway_for(resolved))
        with lowered_limits(resolved.limits):  # before the profile: it reads the tool-call limit when it is built
            run = await _ask(resolved, await _profile(resolved, current_user, world.investigation_id), current_user, observing)
    failures = evaluate(resolved, run)
    return scenario_report(resolved.id, resolved.title, mode.value, failures, run), run


async def _ask(scenario: Scenario, profile: ScopeProfile, current_user: CurrentUser, observing: ObservingGateway) -> ObservedRun:
    engine = AskKeiganEngine(observing)
    prepared = engine.prepare(profile, current_user.preferred_locale)
    masker = PiiMasker()
    masked_question = masker.mask_text(scenario.question)
    async with open_session() as session:
        conversation = Conversation(
            conversation_scope=ConversationScope(profile.conversation_scope), investigation_id=profile.investigation_id, owner_user_principal_name=current_user.user_principal_name,
        )
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
    events: list[AnswerEvent] = []

    async def read_events() -> None:
        async for event in channel.events():
            events.append(event)

    reader = asyncio.create_task(read_events())
    started_at = time.monotonic()
    await engine.run(prepared, AnswerRequest(current_user, conversation_id, masked_question, (), masker), recorder, CancellationFlag())
    duration_milliseconds = int((time.monotonic() - started_at) * 1000)
    await asyncio.wait_for(reader, timeout=EVENT_READER_TIMEOUT_SECONDS)
    return await _observe(run_id, profile, events, tuple(observing.turns), duration_milliseconds)


async def _observe(run_id: str, profile: ScopeProfile, events: list[AnswerEvent], turns: tuple[ObservedTurn, ...], duration_milliseconds: int) -> ObservedRun:
    async with open_session() as session:
        run = await session.get(ChatAnswerRun, run_id)
        assert run is not None
        steps = (await session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == run_id, ChatRunStep.step_kind == ChatRunStepKind.TOOL_CALL).order_by(ChatRunStep.sequence_number))).all()
        answer = await session.get(ConversationMessage, run.assistant_message_id) if run.assistant_message_id else None
    payload = (answer.message_payload_json if answer else None) or {}
    codes_by_application_id = {application.id: application.code for application in profile.readable_applications}
    return ObservedRun(
        run_status=run.run_status, stop_reason=run.stop_reason or "", error_code=run.error_code,
        calls=tuple(_observed_call(step) for step in steps if step.step_status != ChatRunStepStatus.SKIPPED),
        answer_text=answer.message_text if answer else None, citation_codes=tuple(citation["code"] for citation in payload.get("citations", [])), is_refusal=bool(payload.get("isRefusal")),
        applications_read=tuple(sorted(codes_by_application_id[application_id] for application_id in (run.used_application_ids_json or []) if application_id in codes_by_application_id)),
        answer_text_event_count=sum(event.name is AnswerEventName.ANSWER_TEXT for event in events), turns=turns, duration_milliseconds=duration_milliseconds,
        tool_calling_mode=run.tool_calling_mode, model_name=run.model_name,
    )


def _observed_call(step: ChatRunStep) -> ObservedCall:
    return ObservedCall(
        tool_name=step.tool_name or "", arguments=step.effective_arguments_json or {}, status=ChatRunStepStatus(step.step_status), outcome_code=step.outcome_code,
        citation_code=step.citation_code, result_text="\n".join(str(part) for part in (step.output_json, step.model_view_text, step.outcome_message) if part),
    )

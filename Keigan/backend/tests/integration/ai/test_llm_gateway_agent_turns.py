"""keigan/ai/llm_gateway.py agent turns: one model turn of Ask Keigan through native tool calling, the mock planner hook, the per-turn budget and usage (spec 23, section 4.6.1)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
from sqlalchemy import select

from keigan.ai import llm_gateway
from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.ai.llm_gateway import (
    AgentPlannerInput, AgentTextChunk, AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, LlmGateway, LlmUsageContext, ModelTier, PromptSection,
    register_mock_agent_planner,
)
from keigan.config.database_config import open_session
from keigan.config.settings import LlmProviderName, get_settings
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.entities.status_values import ToolCallingMode
from keigan.exceptions.keigan_exceptions import (
    AgentToolsUnsupportedException, LlmOutputValidationException, LlmTimeoutException, LlmUnavailableException, TokenBudgetExceededException,
)

FEATURE = "ask_keigan_test"
EVIDENCE_TOOL = AgentToolSpec(
    name="get_evidence", description="Open one evidence item.",
    parameters_schema={"type": "object", "properties": {"evidence_code": {"type": "string"}}, "required": ["evidence_code"], "additionalProperties": False},
)


class _UpstreamError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ScriptedAgentModel(BaseChatModel):
    """A chat model that replays scripted replies (lists of chunks, or an error raised before or after some chunks) and records what it was asked."""

    replies: list[Any] = Field(default_factory=list)
    bind_calls: list[dict[str, Any]] = Field(default_factory=list)
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)
    streamed_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-agent-model"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any) -> ScriptedAgentModel:
        self.bind_calls.append({"tools": list(tools), "tool_choice": tool_choice, **kwargs})
        return self

    def _next_reply(self, messages: list[BaseMessage]) -> list[Any]:
        self.seen_messages.append(messages)
        reply = self.replies.pop(0)
        return reply if isinstance(reply, list) else [reply]

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        items = self._next_reply(messages)
        failure = next((item for item in items if isinstance(item, Exception)), None)
        if failure is not None:
            raise failure
        merged = items[0]
        for item in items[1:]:
            merged = merged + item
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=merged.content, tool_calls=merged.tool_calls, usage_metadata=merged.usage_metadata))])

    async def _astream(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.streamed_calls += 1
        for item in self._next_reply(messages):
            if isinstance(item, Exception):
                raise item
            yield ChatGenerationChunk(message=item)

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        raise NotImplementedError


def text_chunk(text: str, **extra: Any) -> AIMessageChunk:
    return AIMessageChunk(content=text, **extra)


def usage(input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}


def tool_call_message(name: str, arguments_json: str, call_id: str = "call_1", **extra: Any) -> AIMessageChunk:
    return AIMessageChunk(content="", tool_call_chunks=[tool_call_chunk(name=name, args=arguments_json, id=call_id, index=0)], **extra)


@pytest.fixture
def agent_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", LlmProviderName.OPENAI_COMPATIBLE)
    monkeypatch.setattr(settings, "llm_api_key", "a-key")
    monkeypatch.setattr(settings, "llm_maximum_retries", 2)
    monkeypatch.setattr(LlmGateway, "_retry_delay_seconds", staticmethod(lambda attempt_index: 0.0))
    return settings


def gateway_with(model: ScriptedAgentModel) -> LlmGateway:
    gateway = LlmGateway(get_settings())
    gateway._chat_models_by_tier[ModelTier.DEEP] = model
    return gateway


async def run_turn(gateway: LlmGateway, **overrides: Any) -> list[AgentTextChunk | AgentTurnResult]:
    arguments: dict[str, Any] = {
        "feature_name": FEATURE, "model_tier": ModelTier.DEEP, "system_prompt": "You are Keigan.",
        "transcript": [AgentTranscriptEntry(kind="data", section=PromptSection("Question", "Show me evidence E2", is_untrusted=True, source_label="chat:user-question"))],
        "tools": [EVIDENCE_TOOL], "allow_tool_requests": True, "usage_context": LlmUsageContext(requested_by_user_principal_name=f"agent-{uuid.uuid4().hex[:8]}@keigan.local"),
        **overrides,
    }
    return [item async for item in gateway.stream_agent_turn(**arguments)]


async def test_a_turn_that_asks_for_a_tool_ends_with_the_parsed_request_and_the_reported_tokens(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[tool_call_message("get_evidence", '{"evidence_code": "E2"}', usage_metadata=usage(120, 15))])
    items = await run_turn(gateway_with(model))
    result = items[-1]
    assert isinstance(result, AgentTurnResult)
    assert result.finish == "tool_requests"
    assert result.tool_requests == (AgentToolRequest(request_id="call_1", tool_name="get_evidence", arguments={"evidence_code": "E2"}, arguments_problem=None),)
    assert (result.input_token_count, result.output_token_count, result.token_counts_estimated) == (120, 15, False)
    assert result.tool_calling_mode == ToolCallingMode.NATIVE
    assert result.model_name == get_settings().llm_deep_model


async def test_an_answer_is_streamed_in_pieces_and_followed_by_exactly_one_result(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("Evidence E2 "), text_chunk("shows a spike [T1].", usage_metadata=usage(80, 9))]])
    items = await run_turn(gateway_with(model))
    chunks, results = [item for item in items if isinstance(item, AgentTextChunk)], [item for item in items if isinstance(item, AgentTurnResult)]
    assert [chunk.text for chunk in chunks] == ["Evidence E2 ", "shows a spike [T1]."]
    assert len(results) == 1 and items[-1] is results[0]
    assert results[0].text == "Evidence E2 shows a spike [T1]." and results[0].finish == "answer" and results[0].tool_requests == ()


async def test_run_agent_turn_returns_only_the_final_result(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("Done.", usage_metadata=usage(10, 2))]])
    result = await gateway_with(model).run_agent_turn(
        feature_name=FEATURE, model_tier=ModelTier.DEEP, system_prompt="s", transcript=[], tools=[EVIDENCE_TOOL], allow_tool_requests=True,
        usage_context=LlmUsageContext(requested_by_user_principal_name="agent-run@keigan.local"),
    )
    assert isinstance(result, AgentTurnResult) and result.text == "Done."


async def test_run_agent_turn_raises_a_typed_error_when_the_turn_ended_without_a_result(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = gateway_with(ScriptedAgentModel(replies=[]))

    async def stream_without_a_result(**_arguments: Any) -> AsyncIterator[AgentTextChunk | AgentTurnResult]:
        yield AgentTextChunk("a text with no result after it")

    monkeypatch.setattr(gateway, "stream_agent_turn", stream_without_a_result)
    with pytest.raises(LlmOutputValidationException, match="without a result"):
        await gateway.run_agent_turn(
            feature_name=FEATURE, model_tier=ModelTier.DEEP, system_prompt="s", transcript=[], tools=[EVIDENCE_TOOL], allow_tool_requests=True,
            usage_context=LlmUsageContext(requested_by_user_principal_name="agent-run@keigan.local"),
        )


async def test_a_provider_that_reports_no_usage_gets_estimated_counts_flagged_as_estimates(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("Evidence E2 shows a spike on claims-api in the last hour.")]])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult)
    assert result.token_counts_estimated is True
    assert result.input_token_count > 0 and result.output_token_count > 0


async def test_a_reply_cut_off_by_the_models_length_limit_finishes_as_length(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("Half an ans", usage_metadata=usage(10, 5), response_metadata={"finish_reason": "length"})]])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "length"


async def test_a_tool_call_whose_arguments_are_not_json_is_reported_with_a_problem_and_no_arguments(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[tool_call_message("get_evidence", "not json at all {", usage_metadata=usage(10, 5))])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult)
    assert result.finish == "tool_requests"
    (request,) = result.tool_requests
    assert request.tool_name == "get_evidence" and request.arguments is None and request.arguments_problem


async def test_the_offered_tools_are_bound_as_function_definitions_without_a_tool_choice_while_requests_are_allowed(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model))
    (bind_call,) = model.bind_calls
    assert bind_call["tools"] == [{"type": "function", "function": {"name": "get_evidence", "description": "Open one evidence item.", "parameters": EVIDENCE_TOOL.parameters_schema}}]
    assert bind_call["tool_choice"] is None


async def test_the_final_turn_forbids_tool_calls_when_the_model_supports_tool_choice_none(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model), allow_tool_requests=False)
    assert model.bind_calls[0]["tool_choice"] == "none"


async def test_the_final_turn_binds_the_tools_unchanged_when_the_model_cannot_forbid_tool_calls(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "*", "supports_tool_choice_none": False}]}})
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", overrides)
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model), allow_tool_requests=False)
    assert model.bind_calls[0]["tool_choice"] is None


async def test_parallel_tool_calls_are_switched_off_for_an_openai_style_model_that_cannot_make_them(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model))
    assert model.bind_calls[0]["parallel_tool_calls"] is False


async def test_parallel_tool_calls_are_left_alone_for_a_model_that_can_make_them(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "*", "parallel_tool_calls": True}]}})
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", overrides)
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model))
    assert "parallel_tool_calls" not in model.bind_calls[0]


async def test_with_no_tools_offered_the_model_is_not_bound_to_tools(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model), tools=[])
    assert model.bind_calls == []


async def test_the_transcript_becomes_provider_messages_with_untrusted_text_spotlighted_and_tool_results_linked_to_their_call(agent_settings: Any) -> None:
    transcript = [
        AgentTranscriptEntry(kind="data", section=PromptSection("Question", "Show me evidence E2", is_untrusted=True, source_label="chat:user-question")),
        AgentTranscriptEntry(
            kind="assistant", text="Looking it up.",
            tool_requests=(AgentToolRequest(request_id="call_9", tool_name="get_evidence", arguments={"evidence_code": "E2"}, arguments_problem=None),),
        ),
        AgentTranscriptEntry(kind="tool_result", tool_request_id="call_9", tool_name="get_evidence", tool_result_text="<untrusted_data>spike</untrusted_data>"),
    ]
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model), transcript=transcript)
    system_message, question_message, assistant_message, tool_message = model.seen_messages[0]
    assert isinstance(system_message, SystemMessage) and system_message.content.startswith("You are Keigan.")
    assert "never claim to have executed commands" in system_message.content
    assert isinstance(question_message, HumanMessage) and "## Question" in question_message.content and '<untrusted_data source="chat:user-question"' in question_message.content
    assert isinstance(assistant_message, AIMessage) and assistant_message.content == "Looking it up."
    assert assistant_message.tool_calls == [{"name": "get_evidence", "args": {"evidence_code": "E2"}, "id": "call_9", "type": "tool_call"}]
    assert isinstance(tool_message, ToolMessage) and tool_message.tool_call_id == "call_9" and tool_message.content == "<untrusted_data>spike</untrusted_data>"


async def test_a_request_the_model_made_with_unusable_arguments_is_replayed_with_empty_arguments(agent_settings: Any) -> None:
    transcript = [
        AgentTranscriptEntry(kind="assistant", tool_requests=(AgentToolRequest(request_id="call_3", tool_name="get_evidence", arguments=None, arguments_problem="not JSON"),)),
        AgentTranscriptEntry(kind="tool_result", tool_request_id="call_3", tool_name="get_evidence", tool_result_text="refused: the arguments were not valid JSON"),
    ]
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    await run_turn(gateway_with(model), transcript=transcript)
    assert model.seen_messages[0][1].tool_calls[0]["args"] == {}


# ── Failures: retries only before the first chunk, usage on every turn ────────────────────────────────


async def test_a_failure_before_the_first_chunk_is_retried_and_the_turn_succeeds(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[_UpstreamError("Bad gateway", 502)], [text_chunk("Recovered.", usage_metadata=usage(5, 2))]])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.text == "Recovered."
    assert model.streamed_calls == 2


async def test_a_failure_after_the_first_chunk_is_not_retried_and_is_reported_as_a_classified_error(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("Evidence E2 "), _UpstreamError("Bad gateway", 502)], [text_chunk("never used")]])
    received: list[Any] = []
    with pytest.raises(LlmUnavailableException) as failure:
        async for item in gateway_with(model).stream_agent_turn(
            feature_name=FEATURE, model_tier=ModelTier.DEEP, system_prompt="s", transcript=[], tools=[EVIDENCE_TOOL], allow_tool_requests=True,
            usage_context=LlmUsageContext(requested_by_user_principal_name="agent-late@keigan.local"),
        ):
            received.append(item)
    assert failure.value.error_code == "ai_unavailable"
    assert received == [AgentTextChunk("Evidence E2 ")]
    assert model.streamed_calls == 1


async def test_a_model_that_goes_silent_between_chunks_times_out_with_the_timeout_error(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_maximum_retries", 0)
    monkeypatch.setattr(get_settings(), "llm_request_timeout_seconds", 0)
    monkeypatch.setattr(llm_gateway, "PROVIDER_TIMEOUT_GRACE_SECONDS", 0.05)

    class SilentModel(ScriptedAgentModel):
        async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
            await asyncio.sleep(5)
            yield ChatGenerationChunk(message=text_chunk("late"))

    with pytest.raises(LlmTimeoutException):
        await run_turn(gateway_with(SilentModel()))


async def test_a_failing_turn_records_a_failed_usage_row_and_a_good_turn_records_its_tokens(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_gateway, "USAGE_FLUSH_DELAY_SECONDS", 0)
    conversation_id = f"conversation-{uuid.uuid4().hex[:8]}"
    context = LlmUsageContext(conversation_id=conversation_id, requested_by_user_principal_name=f"usage-{uuid.uuid4().hex[:8]}@keigan.local")
    monkeypatch.setattr(get_settings(), "llm_maximum_retries", 0)
    gateway = gateway_with(ScriptedAgentModel(replies=[[text_chunk("Fine.", usage_metadata=usage(30, 4))], [_UpstreamError("Bad gateway", 502)]]))
    await run_turn(gateway, usage_context=context)
    await gateway._usage_flush_task
    with pytest.raises(LlmUnavailableException):
        await run_turn(gateway, usage_context=context)
    await gateway._usage_flush_task
    async with open_session() as session:
        rows = (await session.scalars(select(LlmUsageRecord).where(LlmUsageRecord.conversation_id == conversation_id).order_by(LlmUsageRecord.created_at))).all()
    assert sorted((row.outcome_status, row.input_token_count, row.output_token_count, row.feature_name) for row in rows) == [
        ("failed", 0, 0, FEATURE), ("succeeded", 30, 4, FEATURE),
    ]


async def test_a_user_over_the_budget_cannot_start_a_turn_and_the_model_is_never_called(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_ai_safety_settings(), "llm_daily_token_budget_per_user", 1000)
    user = f"budget-{uuid.uuid4().hex[:8]}@keigan.local"
    async with open_session() as session:
        session.add(LlmUsageRecord(feature_name=FEATURE, provider_name="x", model_name="x", model_tier="deep", input_token_count=900, output_token_count=200, outcome_status="succeeded",
                                   requested_by_user_principal_name=user))
    model = ScriptedAgentModel(replies=[[text_chunk("never")]])
    with pytest.raises(TokenBudgetExceededException):
        await run_turn(gateway_with(model), usage_context=LlmUsageContext(requested_by_user_principal_name=user))
    assert model.seen_messages == []


# ── Capabilities decide what is possible ────────────────────────────────────────────────────────


async def test_a_model_that_cannot_use_tools_is_refused_instead_of_answering_without_them(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "*", "tool_calling": "none"}]}})
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", overrides)
    model = ScriptedAgentModel(replies=[[text_chunk("never")]])
    with pytest.raises(AgentToolsUnsupportedException) as failure:
        await run_turn(gateway_with(model))
    assert failure.value.error_code == "ai_tools_unsupported" and failure.value.status_code == 503
    assert "Ask Keigan needs an AI model that can use tools" in failure.value.detail
    assert model.seen_messages == []


async def test_a_model_that_does_not_stream_is_asked_once_and_yields_only_its_result(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "*", "streams_text": False}]}})
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", overrides)
    model = ScriptedAgentModel(replies=[[text_chunk("Whole answer.", usage_metadata=usage(7, 3))]])
    items = await run_turn(gateway_with(model))
    assert model.streamed_calls == 0
    assert len(items) == 1 and isinstance(items[0], AgentTurnResult) and items[0].text == "Whole answer." and items[0].input_token_count == 7


def test_the_capabilities_of_a_tier_come_from_the_catalog_and_the_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.OPENAI_COMPATIBLE)
    monkeypatch.setattr(get_settings(), "llm_deep_model", "wrapper-large")
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", json.dumps({"providers": {"openai_compatible": [{"model": "wrapper-*", "max_context_tokens": 32000}]}}))
    assert LlmGateway(get_settings()).agent_capabilities(ModelTier.DEEP).max_context_tokens == 32_000


# ── Mock provider: the registered planner answers, no chat model exists ──────────────────────────────────


def planner_that_asks_for_evidence_then_answers(planner_input: AgentPlannerInput) -> AgentTurnResult:
    already_called = any(entry.kind == "tool_result" for entry in planner_input.transcript)
    if already_called or not planner_input.allow_tool_requests:
        return AgentTurnResult(
            text="Evidence E2 shows a spike on claims-api in the last hour [T1].", tool_requests=(), finish="answer", input_token_count=10, output_token_count=12,
            token_counts_estimated=True, model_name="mock", tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK,
        )
    return AgentTurnResult(
        text="", tool_requests=(AgentToolRequest("k1", "get_evidence", {"evidence_code": "E2"}, None),), finish="tool_requests", input_token_count=10, output_token_count=5,
        token_counts_estimated=True, model_name="mock", tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK,
    )


async def test_with_the_mock_provider_the_registered_planner_decides_the_turn_and_the_planner_sees_the_offered_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    seen: list[AgentPlannerInput] = []

    def recording_planner(planner_input: AgentPlannerInput) -> AgentTurnResult:
        seen.append(planner_input)
        return planner_that_asks_for_evidence_then_answers(planner_input)

    monkeypatch.setitem(llm_gateway._mock_agent_planners, FEATURE, recording_planner)
    gateway = LlmGateway(get_settings())
    first = (await run_turn(gateway))[-1]
    assert isinstance(first, AgentTurnResult) and first.tool_requests[0].tool_name == "get_evidence" and first.tool_calling_mode == ToolCallingMode.SCRIPTED_MOCK
    assert seen[0].tools == (EVIDENCE_TOOL,) and seen[0].allow_tool_requests is True and seen[0].system_prompt == "You are Keigan."
    assert gateway._chat_models_by_tier == {}


async def test_the_mock_planner_is_told_when_no_more_tool_requests_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    monkeypatch.setitem(llm_gateway._mock_agent_planners, FEATURE, planner_that_asks_for_evidence_then_answers)
    result = (await run_turn(LlmGateway(get_settings()), allow_tool_requests=False))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "answer" and result.tool_requests == ()


async def test_with_the_mock_provider_an_answer_is_streamed_in_several_chunks_that_add_up_to_the_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    monkeypatch.setitem(llm_gateway._mock_agent_planners, FEATURE, planner_that_asks_for_evidence_then_answers)
    items = await run_turn(LlmGateway(get_settings()), allow_tool_requests=False)
    chunks = [item.text for item in items if isinstance(item, AgentTextChunk)]
    assert len(chunks) == llm_gateway.MOCK_ANSWER_CHUNK_COUNT
    assert "".join(chunks) == "Evidence E2 shows a spike on claims-api in the last hour [T1]."


async def test_with_the_mock_provider_a_feature_without_a_planner_answers_with_the_standard_simulated_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    result = (await run_turn(LlmGateway(get_settings()), feature_name="ask_keigan_without_a_planner"))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "answer" and "LLM_PROVIDER=mock" in result.text and result.tool_calling_mode == ToolCallingMode.SCRIPTED_MOCK


async def test_with_the_mock_provider_a_user_over_the_budget_is_still_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    monkeypatch.setattr(get_ai_safety_settings(), "llm_daily_token_budget_per_user", 1000)
    user = f"mock-budget-{uuid.uuid4().hex[:8]}@keigan.local"
    async with open_session() as session:
        session.add(LlmUsageRecord(feature_name=FEATURE, provider_name="mock", model_name="mock", model_tier="deep", input_token_count=1500, output_token_count=0,
                                   outcome_status="succeeded", requested_by_user_principal_name=user))
    monkeypatch.setitem(llm_gateway._mock_agent_planners, FEATURE, planner_that_asks_for_evidence_then_answers)
    with pytest.raises(TokenBudgetExceededException):
        await run_turn(LlmGateway(get_settings()), usage_context=LlmUsageContext(requested_by_user_principal_name=user))


def test_a_planner_is_registered_by_feature_name() -> None:
    try:
        register_mock_agent_planner("ask_keigan_registration_test", planner_that_asks_for_evidence_then_answers)
        assert llm_gateway._mock_agent_planners["ask_keigan_registration_test"] is planner_that_asks_for_evidence_then_answers
    finally:
        llm_gateway._mock_agent_planners.pop("ask_keigan_registration_test", None)


# ── The chat model follows the capabilities of the model it is built for ─────────────────────────────────


def test_a_model_that_rejects_a_temperature_is_built_without_one_while_other_models_keep_it(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", LlmProviderName.OPENAI_COMPATIBLE)
    monkeypatch.setattr(settings, "llm_api_key", "a-key")
    monkeypatch.setattr(settings, "llm_temperature", 0.3)
    monkeypatch.setattr(settings, "llm_model_capabilities_json", json.dumps({"providers": {"openai_compatible": [{"model": "reasoning-*", "supports_temperature": False}]}}))
    gateway = LlmGateway(settings)
    assert gateway._create_chat_model("reasoning-large").temperature is None
    assert gateway._create_chat_model("plain-model").temperature == 0.3


async def test_structured_output_uses_the_method_the_model_declares_instead_of_the_global_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", LlmProviderName.OPENAI_COMPATIBLE)
    monkeypatch.setattr(settings, "llm_api_key", "a-key")
    monkeypatch.setattr(settings, "llm_structured_output_method", "function_calling")
    monkeypatch.setattr(settings, "llm_model_capabilities_json", json.dumps({"providers": {"openai_compatible": [{"model": "*", "structured_output_method": "json_schema"}]}}))
    methods: list[str] = []

    class Answer(llm_gateway.BaseModel):
        value: str

    class StructuredStub:
        async def ainvoke(self, messages: object) -> dict[str, Any]:
            return {"raw": AIMessage(content=""), "parsed": Answer(value="x"), "parsing_error": None}

    class Model(ScriptedAgentModel):
        def with_structured_output(self, schema: Any, *, include_raw: bool = False, method: str = "", **kwargs: Any) -> StructuredStub:
            methods.append(method)
            return StructuredStub()

    gateway = LlmGateway(settings)
    gateway._chat_models_by_tier[ModelTier.FAST] = Model()
    await gateway.generate_structured(
        feature_name="x", model_tier=ModelTier.FAST, system_prompt="s", prompt_sections=[], output_schema=Answer, usage_context=LlmUsageContext(enforce_token_budget=False)
    )
    assert methods == ["json_schema"]


# ── Prompted JSON: a model without native tool calling (spec 23, 4.6.4) ─────────────────────────────────────────


@pytest.fixture
def prompted_settings(agent_settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "llm_model_capabilities_json", json.dumps({"providers": {"openai_compatible": [{"model": "*", "tool_calling": "prompted_json"}]}}))
    monkeypatch.setattr(get_settings(), "ask_keigan_protocol_repair_attempts", 1)
    return agent_settings


def reply(payload: Any, **extra: Any) -> list[AIMessageChunk]:
    return [text_chunk(payload if isinstance(payload, str) else json.dumps(payload), **extra)]


REQUEST_REPLY = {"kind": "tool_requests", "requests": [{"id": "k1", "tool": "get_evidence", "arguments": {"evidence_code": "E2"}}]}


async def test_prompted_mode_parses_a_request_reply_into_the_same_request_a_native_call_gives(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[reply(REQUEST_REPLY, usage_metadata=usage(120, 15))])
    items = await run_turn(gateway_with(model))
    assert len(items) == 1  # the reply is JSON: nothing is streamed as text
    result = items[0]
    assert isinstance(result, AgentTurnResult) and result.finish == "tool_requests" and result.text == ""
    assert result.tool_requests == (AgentToolRequest("k1", "get_evidence", {"evidence_code": "E2"}, None),)
    assert (result.input_token_count, result.output_token_count, result.token_counts_estimated) == (120, 15, False)
    assert result.tool_calling_mode == ToolCallingMode.PROMPTED_JSON
    assert model.bind_calls == [] and model.streamed_calls == 0


async def test_prompted_mode_returns_the_answer_text_with_its_follow_ups(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[reply({"kind": "answer", "text": "E2 shows a spike [T1].", "follow_ups": ["What changed?"]})])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "answer" and result.tool_requests == ()
    assert result.text == "E2 shows a spike [T1].\n\n<<follow-ups>>\nWhat changed?"
    assert result.token_counts_estimated is True and result.input_token_count > 0


async def test_prompted_mode_puts_the_protocol_and_the_tools_in_the_system_prompt_and_spotlights_the_question(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[reply({"kind": "answer", "text": "ok"})])
    await run_turn(gateway_with(model))
    system_message, question_message = model.seen_messages[0]
    assert system_message.content.startswith("You are Keigan.") and "exactly one JSON object" in system_message.content and "get_evidence" in system_message.content
    assert "never claim to have executed commands" in system_message.content
    assert '<untrusted_data source="chat:user-question"' in question_message.content


async def test_prompted_mode_does_not_offer_tool_requests_on_the_final_turn(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[reply({"kind": "answer", "text": "ok"})])
    await run_turn(gateway_with(model), allow_tool_requests=False)
    assert "Tool requests are not accepted" in model.seen_messages[0][0].content


async def test_prompted_mode_shows_earlier_turns_as_json_and_results_as_one_spotlighted_block_with_unique_request_numbers(prompted_settings: Any) -> None:
    transcript = [
        AgentTranscriptEntry(kind="data", section=PromptSection("Question", "Show me evidence E2", is_untrusted=True, source_label="chat:user-question")),
        AgentTranscriptEntry(kind="assistant", tool_requests=(AgentToolRequest("k1", "get_evidence", {"evidence_code": "E2"}),)),
        AgentTranscriptEntry(kind="tool_result", tool_request_id="k1", tool_name="get_evidence", tool_result_text='<untrusted_data source="tool:get_evidence:T1">spike</untrusted_data>'),
    ]
    model = ScriptedAgentModel(replies=[reply(REQUEST_REPLY)])
    result = (await run_turn(gateway_with(model), transcript=transcript))[-1]
    _, _, assistant_message, results_message = model.seen_messages[0]
    assert isinstance(assistant_message, AIMessage) and json.loads(assistant_message.content)["requests"][0]["tool"] == "get_evidence" and assistant_message.tool_calls == []
    assert isinstance(results_message, HumanMessage) and "## Tool results" in results_message.content and 'source="tool:get_evidence:T1"' in results_message.content
    assert isinstance(result, AgentTurnResult) and [request.request_id for request in result.tool_requests] == ["k2"]


async def test_a_malformed_reply_is_sent_back_with_the_problem_and_the_corrected_reply_is_used(prompted_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_gateway, "USAGE_FLUSH_DELAY_SECONDS", 0.2)  # long enough for both calls of the turn to be queued before the rows are written
    conversation_id = f"conversation-{uuid.uuid4().hex[:8]}"
    model = ScriptedAgentModel(replies=[reply("The evidence shows a spike.", usage_metadata=usage(50, 6)), reply(REQUEST_REPLY, usage_metadata=usage(80, 14))])
    gateway = gateway_with(model)
    result = (await run_turn(gateway, usage_context=LlmUsageContext(conversation_id=conversation_id, requested_by_user_principal_name=f"repair-{uuid.uuid4().hex[:8]}@keigan.local")))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "tool_requests" and result.tool_requests[0].tool_name == "get_evidence"
    assert (result.input_token_count, result.output_token_count) == (130, 20)  # both calls count against the answer's budget
    repair_messages = model.seen_messages[1][-2:]
    assert repair_messages[0].content == "The evidence shows a spike." and "not valid JSON" in repair_messages[1].content
    await gateway._usage_flush_task
    async with open_session() as session:
        rows = (await session.scalars(select(LlmUsageRecord).where(LlmUsageRecord.conversation_id == conversation_id))).all()
    assert sorted(row.outcome_status for row in rows) == ["succeeded", "validation_retry"]


async def test_a_second_malformed_reply_ends_the_turn_as_a_protocol_error_instead_of_guessing(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[reply("not json", usage_metadata=usage(10, 2)), reply('{"kind": "answer"}', usage_metadata=usage(20, 3))])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "protocol_error" and result.tool_requests == () and result.text == ""
    assert (result.input_token_count, result.output_token_count) == (30, 5) and result.tool_calling_mode == ToolCallingMode.PROMPTED_JSON
    assert len(model.seen_messages) == 2


async def test_with_no_repair_attempts_the_first_malformed_reply_is_a_protocol_error(prompted_settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_protocol_repair_attempts", 0)
    model = ScriptedAgentModel(replies=[reply("not json")])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.finish == "protocol_error" and len(model.seen_messages) == 1


async def test_prompted_mode_leaves_the_values_of_arguments_to_the_tool_registry_like_native_mode(prompted_settings: Any) -> None:
    payload = {"kind": "tool_requests", "requests": [{"tool": "get_evidence", "arguments": {"evidence_code": 99999}}]}
    result = (await run_turn(gateway_with(ScriptedAgentModel(replies=[reply(payload)]))))[-1]
    assert isinstance(result, AgentTurnResult) and result.tool_requests[0].arguments == {"evidence_code": 99999}


async def test_a_failing_prompted_call_is_retried_and_classified_like_a_native_one(prompted_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[_UpstreamError("Bad gateway", 502)], reply({"kind": "answer", "text": "Recovered."})])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.text == "Recovered."
    with pytest.raises(LlmUnavailableException):
        await run_turn(gateway_with(ScriptedAgentModel(replies=[[_UpstreamError("Bad gateway", 502)]] * 3)))


async def test_prompted_mode_is_never_used_when_the_model_is_native(agent_settings: Any) -> None:
    model = ScriptedAgentModel(replies=[[text_chunk("ok", usage_metadata=usage(1, 1))]])
    result = (await run_turn(gateway_with(model)))[-1]
    assert isinstance(result, AgentTurnResult) and result.tool_calling_mode == ToolCallingMode.NATIVE and "exactly one JSON object" not in model.seen_messages[0][0].content

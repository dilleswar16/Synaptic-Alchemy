"""The loop of one Ask Keigan answer: ask the model, run the tools it requests, repeat until it answers or a limit ends it (spec 23, 4.8).

Each pass first checks for a stop request, then decides whether this turn is the last (the tool-call limit is used up, or 85 % of the token budget is),
streams one model turn (paragraphs are released as they close), and either runs the requested tools one after another or ends with the model's text. The
loop knows nothing about where the answer is stored or how a failure is worded: it returns the final text and why it stopped, or raises.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from keigan.ai.ask_keigan_answer_stream import AnswerTextStreamer
from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import AgentTextChunk, AgentToolRequest, AgentTranscriptEntry, AgentTurnResult, LlmUsageContext
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatAnswerStopReason
from keigan.exceptions.keigan_exceptions import AgentToolProtocolException, LlmOutputValidationException
from keigan.services.ask_keigan_answer_assembler import build_citation_targets
from keigan.services.ask_keigan_cancellation import RunCancellationGuard
from keigan.services.ask_keigan_limit_summary import limit_reached_answer
from keigan.services.ask_keigan_prepared_run import AgentGateway, PreparedRun
from keigan.services.ask_keigan_run_state import ExecutedToolCall
from keigan.services.ask_keigan_tool_runner import ToolCallRunner
from keigan.services.ask_keigan_trace import SkipReason, StepHandle, TraceRecorder
from keigan.services.ask_keigan_transcript import assistant_turn_entry, tool_result_entry

TOKEN_BUDGET_FINAL_TURN_FRACTION = 0.85  # at this share of the answer's token budget the next model turn is the last one (spec 23, 4.8)
_PROTOCOL_ERROR_FINISH = "protocol_error"
_LENGTH_FINISH = "length"  # the model was cut off: whatever tool requests it carries are unreliable
_SKIP_REASON_BY_STOP_REASON = {ChatAnswerStopReason.TOOL_LIMIT_REACHED: SkipReason.TOOL_LIMIT_REACHED, ChatAnswerStopReason.TOKEN_BUDGET_REACHED: SkipReason.TOKEN_BUDGET_REACHED}


@dataclass(frozen=True)
class LoopOutcome:
    answer_text: str  # the model's final text (with its follow-up section), or the deterministic limit summary
    stop_reason: ChatAnswerStopReason
    executed_calls: tuple[ExecutedToolCall, ...]


@dataclass
class _LoopState:
    transcript: list[AgentTranscriptEntry]
    executed_calls: list[ExecutedToolCall] = field(default_factory=list)
    tokens_used: int = 0
    turn_number: int = 0


@dataclass(frozen=True)
class _Turn:
    handle: StepHandle
    result: AgentTurnResult


def _tool_requests_of(result: AgentTurnResult) -> tuple[AgentToolRequest, ...]:
    return () if result.finish == _LENGTH_FINISH else result.tool_requests


class AnswerLoop:
    def __init__(
        self, *, gateway: AgentGateway, prepared: PreparedRun, recorder: TraceRecorder, tool_runner: ToolCallRunner, guard: RunCancellationGuard, usage_context: LlmUsageContext,
        language_code: str | None,
    ):
        self._gateway, self._prepared, self._recorder, self._tool_runner = gateway, prepared, recorder, tool_runner
        self._guard, self._usage_context, self._language_code = guard, usage_context, language_code
        self._profile = prepared.profile

    async def run(self, transcript: Sequence[AgentTranscriptEntry]) -> LoopOutcome:
        """Raises ``AnswerCancelledError``, ``AccessLostMidRunException``, ``AgentToolProtocolException``, ``LlmOutputValidationException`` or what the model call raised."""
        state = _LoopState(list(transcript))
        while True:
            await self._guard.raise_if_requested()
            forced_stop_reason = self._forced_stop_reason(state)
            turn = await self._guard.run(self._take_turn(state, allow_tool_requests=forced_stop_reason is None))
            if turn.result.finish == _PROTOCOL_ERROR_FINISH:
                raise AgentToolProtocolException("The model did not follow the tool format.")
            requested_tools = _tool_requests_of(turn.result)
            if requested_tools and forced_stop_reason is None:
                await self._run_requested_tools(state, turn, requested_tools)
                continue
            if forced_stop_reason is not None:
                await self._skip_requests_of_the_last_turn(turn, requested_tools, forced_stop_reason)
            return self._outcome(state, turn.result, forced_stop_reason)

    def _forced_stop_reason(self, state: _LoopState) -> ChatAnswerStopReason | None:
        if len(state.executed_calls) >= self._profile.maximum_tool_calls:
            return ChatAnswerStopReason.TOOL_LIMIT_REACHED
        if state.tokens_used >= TOKEN_BUDGET_FINAL_TURN_FRACTION * get_settings().ask_keigan_answer_token_budget:
            return ChatAnswerStopReason.TOKEN_BUDGET_REACHED
        return None

    async def _take_turn(self, state: _LoopState, *, allow_tool_requests: bool) -> _Turn:
        state.turn_number += 1
        handle = await self._recorder.start_model_turn(state.turn_number)
        streamer = AnswerTextStreamer(frozenset(self._citable_codes(state)))
        paragraphs: list[str] = []
        turn_result: AgentTurnResult | None = None
        received_text_chunks = False
        async for item in self._gateway.stream_agent_turn(
            feature_name=self._profile.feature_name.value, model_tier=self._prepared.model_tier, system_prompt=self._prepared.system_prompt, transcript=state.transcript,
            tools=self._prepared.tool_specs, allow_tool_requests=allow_tool_requests, usage_context=self._usage_context,
        ):
            if isinstance(item, AgentTextChunk):
                received_text_chunks = True
                self._release(state, paragraphs, streamer.feed(item.text))
            else:
                turn_result = item
        if turn_result is None:
            raise LlmOutputValidationException("The model call ended without a result.")
        if not received_text_chunks:  # a model that does not stream: its text arrives with the result and is released the same way
            self._release(state, paragraphs, streamer.feed(turn_result.text))
        self._release(state, paragraphs, streamer.finish())
        state.tokens_used += turn_result.input_token_count + turn_result.output_token_count
        is_note = allow_tool_requests and bool(_tool_requests_of(turn_result))
        await self._recorder.finish_model_turn(handle, turn_result, model_text="\n\n".join(paragraphs), is_note=is_note)
        return _Turn(handle, turn_result)

    def _release(self, state: _LoopState, paragraphs: list[str], released_paragraphs: list[str]) -> None:
        for paragraph in released_paragraphs:
            paragraphs.append(paragraph)
            self._recorder.publish_answer_text(state.turn_number, paragraph)

    def _citable_codes(self, state: _LoopState) -> set[str]:
        return set(build_citation_targets(self._profile.reference_citations, self._profile.accepted_citation_prefixes, state.executed_calls))

    async def _run_requested_tools(self, state: _LoopState, turn: _Turn, requested_tools: Sequence[AgentToolRequest]) -> None:
        """Run the requests one after another (one database session at a time). Every request gets an answer in the transcript, so the model sees what became of it."""
        settings = get_settings()
        state.transcript.append(assistant_turn_entry(turn.result))
        for position, request in enumerate(requested_tools):
            await self._guard.raise_if_requested()
            if position >= settings.ask_keigan_max_parallel_tool_calls:
                call_result = await self._tool_runner.skip(request, turn.handle, SkipReason.PARALLEL_LIMIT_REACHED)
            elif len(state.executed_calls) >= self._profile.maximum_tool_calls:
                call_result = await self._tool_runner.skip(request, turn.handle, SkipReason.TOOL_LIMIT_REACHED, self._tool_limit_message())
            else:
                call_result = await self._tool_runner.run(request, turn.handle, citation_number=len(state.executed_calls) + 1)
            if call_result.executed is not None:
                state.executed_calls.append(call_result.executed)
            state.transcript.append(tool_result_entry(request, call_result.transcript_text))

    async def _skip_requests_of_the_last_turn(self, turn: _Turn, requested_tools: Sequence[AgentToolRequest], stop_reason: ChatAnswerStopReason) -> None:
        """The model asked for tools on the turn that was meant to be the last: the requests are shown in the trace as skipped, and not run."""
        for request in requested_tools:
            await self._tool_runner.skip(
                request, turn.handle, _SKIP_REASON_BY_STOP_REASON[stop_reason], self._tool_limit_message() if stop_reason is ChatAnswerStopReason.TOOL_LIMIT_REACHED else None,
            )

    def _tool_limit_message(self) -> str:
        return AskKeiganErrorCatalogue.describe("tool_limit_reached", {"maximum": self._profile.maximum_tool_calls}, self._language_code).detail

    def _outcome(self, state: _LoopState, result: AgentTurnResult, forced_stop_reason: ChatAnswerStopReason | None) -> LoopOutcome:
        if result.text.strip():
            return LoopOutcome(result.text, forced_stop_reason or ChatAnswerStopReason.ANSWERED, tuple(state.executed_calls))
        if forced_stop_reason is None:
            raise LlmOutputValidationException("The model returned an empty answer.")
        summary = limit_reached_answer(forced_stop_reason, self._profile.maximum_tool_calls, state.executed_calls, self._language_code)
        return LoopOutcome(summary, forced_stop_reason, tuple(state.executed_calls))

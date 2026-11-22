"""A chat model that replays the recorded behaviour of a conformance scenario, so both gateway paths run without a network (spec 23, 4.6.6).

In ``native`` mode it answers like a provider with tool calling: text streamed in pieces and tool calls as ``tool_call_chunks``, which LangChain's own parsing turns into
``tool_calls``. In ``prompted`` mode it answers like a plain model told to reply in JSON: one text with the JSON object (or the scenario's ``raw`` text, a reply outside the format).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from keigan.ai.llm_gateway import split_into_chunks
from keigan.services.ask_keigan_conformance_scenarios import ScriptedTurn

REPORTED_INPUT_TOKENS = 100
REPORTED_OUTPUT_TOKENS = 20
STREAMED_PIECES = 3


class UpstreamError(Exception):
    """What a provider SDK raises for an HTTP failure: the status code is what the gateway classifies on."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"The endpoint answered {status_code}.")
        self.status_code = status_code


class ConformanceScriptedModel(BaseChatModel):
    script: list[ScriptedTurn] = Field(default_factory=list)
    tool_mode: Literal["native", "prompted"] = "native"
    turns_taken: int = 0
    call_number: int = 0

    @property
    def _llm_type(self) -> str:
        return "conformance-scripted-model"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any) -> ConformanceScriptedModel:
        return self

    def _next_turn(self) -> ScriptedTurn:
        assert self.script, "the scenario's offline_script ran out: the engine asked for more model turns than were recorded"
        self.turns_taken += 1
        turn = self.script.pop(0)
        if turn.fails_with_status is not None:
            raise UpstreamError(turn.fails_with_status)
        return turn

    def _usage(self) -> dict[str, int]:
        return {"input_tokens": REPORTED_INPUT_TOKENS, "output_tokens": REPORTED_OUTPUT_TOKENS, "total_tokens": REPORTED_INPUT_TOKENS + REPORTED_OUTPUT_TOKENS}

    def _prompted_reply(self, turn: ScriptedTurn) -> str:
        if turn.raw is not None:
            return turn.raw
        if turn.tool_requests is not None:
            requests = [{"id": f"k{number}", "tool": request.tool, "arguments": request.arguments} for number, request in enumerate(turn.tool_requests, start=1)]
            return json.dumps({"kind": "tool_requests", "requests": requests})
        return json.dumps({"kind": "answer", "text": turn.answer, "follow_ups": turn.follow_ups})

    def _native_text(self, turn: ScriptedTurn) -> str:
        assert turn.raw is None, "a reply outside the prompted format has no native form; the scenario must not run in native mode"
        follow_ups = "".join(f"\n{question}" for question in turn.follow_ups)
        return (turn.answer or "") + (f"\n\n<<follow-ups>>{follow_ups}" if follow_ups else "")

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        turn = self._next_turn()
        assert self.tool_mode == "prompted", "the native path streams"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._prompted_reply(turn), usage_metadata=self._usage()))])  # type: ignore[arg-type]

    async def _astream(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        turn = self._next_turn()
        assert self.tool_mode == "native", "the prompted path does not stream"
        if turn.tool_requests is not None:
            for index, request in enumerate(turn.tool_requests):
                self.call_number += 1
                chunk = AIMessageChunk(content="", tool_call_chunks=[tool_call_chunk(name=request.tool, args=json.dumps(request.arguments), id=f"call_{self.call_number}", index=index)])
                yield ChatGenerationChunk(message=chunk)
            yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=self._usage()))  # type: ignore[arg-type]
            return
        pieces = split_into_chunks(self._native_text(turn), STREAMED_PIECES)
        for position, piece in enumerate(pieces):
            is_last = position == len(pieces) - 1
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece, usage_metadata=self._usage() if is_last else None))  # type: ignore[arg-type]

"""The prompted-JSON tool protocol: how Ask Keigan uses a model that has no native tool calling (spec 23, 4.6.4).

The model is told, in the system prompt, to reply with exactly one JSON object: a request for tools or an answer. This module renders that instruction, parses and
checks a reply, words the correction for a reply outside the format, and turns the transcript into what such a model reads (earlier turns as the JSON they would have
written, tool results as one block). It never calls a model and never decides what a tool may do: a reply gives the same ``AgentToolRequest`` a native tool call gives, and
the values of its arguments are judged afterwards by the tool registry, for both modes, with the same access checks, masking and limits. What counts as malformed is the
format only: not one JSON object, an unknown ``kind``, no or blank answer text, no requests, a tool that is not offered, arguments that are not an object, more requests
than one turn may run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from keigan.ai.agent_turn_types import AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, PromptSection
from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER
from keigan.config import application_context

PROTOCOL_PROMPT_KEY = "_agent_tool_protocol"
TOOL_RESULTS_SECTION_TITLE = "Tool results"
MAXIMUM_PROBLEM_CHARACTERS = 1500  # how much of a problem the correction message repeats
_CODE_FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\r?\n(.*)\r?\n```\s*\Z", re.DOTALL)
_REPAIR_TEMPLATE = (
    "Your previous reply could not be used: {problem}\n"
    'Reply again with exactly one JSON object and nothing else: either {{"kind": "tool_requests", "requests": [{{"id": "k1", "tool": "<tool name>", "arguments": {{}}}}]}} '
    'or {{"kind": "answer", "text": "<your answer>", "follow_ups": []}}.'
)


class MalformedAgentReply(ValueError):
    """The model's reply is outside the protocol. The message says what is wrong, specifically enough for the model to correct it."""


class _RequestedTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None  # accepted, and ignored: Keigan numbers the requests itself so every id is unique across the answer
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class _ToolRequestsReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool_requests"]
    requests: list[_RequestedTool] = Field(min_length=1)


class _AnswerReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["answer"]
    text: str
    follow_ups: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _text_is_not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("an answer needs text")
        return text


_REPLY = TypeAdapter(Annotated[_ToolRequestsReply | _AnswerReply, Field(discriminator="kind")])


@dataclass(frozen=True)
class ParsedAgentReply:
    """``text`` is the answer (with its follow-ups after the marker line, as a native model writes them); ``tool_requests`` is empty for an answer."""

    text: str
    tool_requests: tuple[AgentToolRequest, ...]


def protocol_system_prompt(system_prompt: str, tools: Sequence[AgentToolSpec], *, allow_tool_requests: bool, maximum_requests: int) -> str:
    """The scope's system prompt followed by the versioned protocol fragment with the offered tools and their schemas (without tools on the final turn)."""
    protocol_text = application_context.prompt_library().render(
        PROTOCOL_PROMPT_KEY, allow_tool_requests=allow_tool_requests, maximum_requests=maximum_requests,
        tools=[{"name": tool.name, "description": tool.description, "schema_json": json.dumps(tool.parameters_schema)} for tool in tools],
    )
    return f"{system_prompt.strip()}\n\n{protocol_text}"


def parse_agent_reply(reply_text: str, tools: Sequence[AgentToolSpec], *, maximum_requests: int, first_request_number: int) -> ParsedAgentReply:
    """Raises ``MalformedAgentReply``. The requests get the ids ``k<first_request_number>``, ``k<n+1>`` ..."""
    fenced_body = _CODE_FENCE.match(reply_text)
    try:
        reply_data = json.loads(fenced_body.group(1) if fenced_body else reply_text)
    except json.JSONDecodeError as problem:
        raise MalformedAgentReply(f"The reply is not valid JSON ({problem.msg} at position {problem.pos}). It must be exactly one JSON object, with no text around it.") from problem
    if not isinstance(reply_data, dict):
        raise MalformedAgentReply("The reply must be a JSON object, not a list or a plain value.")
    try:
        reply = _REPLY.validate_python(reply_data)
    except ValidationError as problem:
        raise MalformedAgentReply(_describe(problem)) from problem
    if isinstance(reply, _AnswerReply):
        follow_ups = [question.strip() for question in reply.follow_ups if question.strip()]
        return ParsedAgentReply(f"{reply.text}\n\n{FOLLOW_UP_MARKER}\n" + "\n".join(follow_ups) if follow_ups else reply.text, ())
    if len(reply.requests) > maximum_requests:
        raise MalformedAgentReply(f"The reply asks for {len(reply.requests)} tools; ask for at most {maximum_requests} in one reply.")
    offered_names = [tool.name for tool in tools]
    if unknown := next((request.tool for request in reply.requests if request.tool not in offered_names), None):
        raise MalformedAgentReply(f"'{unknown}' is not a tool you can ask for. The tools are: {', '.join(offered_names)}.")
    return ParsedAgentReply("", tuple(AgentToolRequest(f"k{first_request_number + position}", request.tool, request.arguments) for position, request in enumerate(reply.requests)))


def repair_message(problem: str) -> str:
    """What is sent back to a model whose reply was outside the format."""
    return _REPAIR_TEMPLATE.format(problem=problem[:MAXIMUM_PROBLEM_CHARACTERS])


def prompted_transcript(transcript: Sequence[AgentTranscriptEntry]) -> list[AgentTranscriptEntry]:
    """The conversation as a model without tool calling reads it: an earlier model turn is the JSON reply it stands for, and the tool results that follow it are one block
    (they are already spotlighted by the registry, so the block itself is trusted text)."""
    converted: list[AgentTranscriptEntry] = []
    results: list[str] = []

    def flush_results() -> None:
        if results:
            converted.append(AgentTranscriptEntry(kind="data", section=PromptSection(TOOL_RESULTS_SECTION_TITLE, "\n\n".join(results))))
            results.clear()

    for entry in transcript:
        if entry.kind == "tool_result":
            results.append(f"Result of request {entry.tool_request_id} ({entry.tool_name}):\n{entry.tool_result_text}")
            continue
        flush_results()
        converted.append(AgentTranscriptEntry(kind="assistant", text=_reply_text_of(entry)) if entry.kind == "assistant" else entry)
    flush_results()
    return converted


def _reply_text_of(entry: AgentTranscriptEntry) -> str:
    if entry.tool_requests:
        requests = [{"id": request.request_id, "tool": request.tool_name, "arguments": request.arguments or {}} for request in entry.tool_requests]
        return json.dumps({"kind": "tool_requests", "requests": requests})
    return json.dumps({"kind": "answer", "text": entry.text})


def _describe(problem: ValidationError) -> str:
    """The first validation problems in plain words: where, and what."""
    parts = []
    for error in problem.errors()[:3]:
        location = ".".join(str(step) for step in error["loc"] if not str(step).endswith("Reply")) or "reply"
        parts.append(f"{location}: {error['msg']}")
    return "The reply does not match the format (" + "; ".join(parts) + ")."

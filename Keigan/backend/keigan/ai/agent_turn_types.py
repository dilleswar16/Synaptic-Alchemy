"""The provider-neutral types of one Ask Keigan model turn: what the model is offered, what it asks for, the conversation it is given and the turn's result.

They live apart from ``llm_gateway`` so the modules the gateway uses to speak to a model (the prompted-JSON tool protocol) can build them without importing the gateway.
``llm_gateway`` re-exports every name here, so callers keep importing them from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from keigan.entities.status_values import ToolCallingMode


@dataclass
class PromptSection:
    """One block of the user message. ``is_untrusted`` content is spotlighted and never treated as instructions."""

    title: str
    content: str
    is_untrusted: bool = False
    source_label: str = ""
    maximum_characters: int = 20_000
    is_flagged: bool = False  # the source is already known to look like a prompt-injection attempt; mark its block with a warning


AgentFinish = Literal["tool_requests", "answer", "length", "protocol_error"]


@dataclass(frozen=True)
class AgentToolSpec:
    """A tool as the model is offered it: a name, a description and a closed JSON Schema for its arguments."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


@dataclass(frozen=True)
class AgentToolRequest:
    """A tool the model asked for. ``arguments`` is None (with the reason in ``arguments_problem``) when they could not be read as JSON."""

    request_id: str
    tool_name: str
    arguments: dict[str, Any] | None
    arguments_problem: str | None = None


@dataclass(frozen=True)
class AgentTranscriptEntry:
    """One item of the conversation the gateway turns into provider messages: prompt sections, an earlier model turn, or a tool result."""

    kind: Literal["data", "assistant", "tool_result"]
    section: PromptSection | None = None
    text: str = ""
    tool_requests: tuple[AgentToolRequest, ...] = ()
    tool_request_id: str = ""
    tool_name: str = ""
    tool_result_text: str = ""  # already spotlighted by the tool registry


@dataclass(frozen=True)
class AgentTurnResult:
    text: str
    tool_requests: tuple[AgentToolRequest, ...]
    finish: AgentFinish
    input_token_count: int
    output_token_count: int
    token_counts_estimated: bool
    model_name: str
    tool_calling_mode: ToolCallingMode


@dataclass(frozen=True)
class AgentTextChunk:
    text: str

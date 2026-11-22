"""Everything about an Ask Keigan run that is decided before it starts, and the checks that refuse a run that could not work (spec 23, 4.6.5 and 4.8).

``prepare_run`` is called before the run row is created, so a model that cannot use tools, or whose context window cannot hold the prompt, is refused
(HTTP 503) instead of starting a run that is certain to fail. The result carries the rendered system prompt, the tool schemas the model is offered and
the ``RunSetup`` stored with the run (versions, hashes, offered tools, model, limits) that makes the run reproducible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER, FixedAnswer, fixed_answer
from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import AgentTextChunk, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, LlmUsageContext, ModelTier, estimate_token_count
from keigan.ai.model_capabilities import ModelCapabilities, ToolCallingSupport
from keigan.ai.prompt_library import PromptLibrary
from keigan.ai.tool_registry import ToolRegistry
from keigan.config.settings import Settings
from keigan.entities.status_values import ToolCallingMode
from keigan.exceptions.keigan_exceptions import AgentToolsUnsupportedException, LlmRequestRejectedException
from keigan.services.ask_keigan_scopes import ScopeProfile
from keigan.services.ask_keigan_trace import RunSetup

ENGINE_VERSION = "1"  # the version of the loop itself; stored with every run so a replay knows which engine produced it
_TOOL_CALLING_MODE_BY_SUPPORT = {ToolCallingSupport.NATIVE: ToolCallingMode.NATIVE, ToolCallingSupport.PROMPTED_JSON: ToolCallingMode.PROMPTED_JSON}


class AgentGateway(Protocol):
    """The part of ``LlmGateway`` the engine uses (a scripted double stands in for it in tests)."""

    settings: Settings

    @property
    def is_mock(self) -> bool: ...

    def agent_capabilities(self, model_tier: ModelTier) -> ModelCapabilities: ...

    def model_name_for(self, model_tier: ModelTier) -> str: ...

    def stream_agent_turn(
        self, *, feature_name: str, model_tier: ModelTier, system_prompt: str, transcript: Sequence[AgentTranscriptEntry], tools: Sequence[AgentToolSpec], allow_tool_requests: bool,
        usage_context: LlmUsageContext,
    ) -> AsyncIterator[AgentTextChunk | AgentTurnResult]: ...


@dataclass(frozen=True)
class PreparedRun:
    profile: ScopeProfile
    model_tier: ModelTier
    system_prompt: str
    tool_specs: tuple[AgentToolSpec, ...]
    setup: RunSetup


def prepare_run(*, gateway: AgentGateway, prompt_library: PromptLibrary, registry: ToolRegistry, profile: ScopeProfile, language_code: str | None) -> PreparedRun:
    """Raises ``AgentToolsUnsupportedException`` when the model cannot use tools and ``LlmRequestRejectedException`` when the prompt cannot fit its context window."""
    settings = gateway.settings
    model_tier = ModelTier(prompt_library.model_tier_for_call(profile.prompt_key))
    capabilities = gateway.agent_capabilities(model_tier)
    if capabilities.tool_calling is ToolCallingSupport.NONE:
        raise AgentToolsUnsupportedException(AskKeiganErrorCatalogue.describe("ai_tools_unsupported", {"modelTier": model_tier.value}, language_code).detail)
    system_prompt = prompt_library.render(
        profile.prompt_key, maximum_tool_calls=profile.maximum_tool_calls, follow_up_limit=settings.ask_keigan_follow_up_question_limit, follow_up_marker=FOLLOW_UP_MARKER,
        outside_scope_answer=fixed_answer(FixedAnswer.OUTSIDE_SCOPE, language_code), **profile.prompt_variables,
    )
    tool_specs = tuple(AgentToolSpec(tool.name, tool.description, registry.model_schema(tool, profile)) for tool in profile.offered_tools)
    _ensure_the_prompt_fits(system_prompt, tool_specs, profile, capabilities, settings, model_tier, language_code)
    setup = RunSetup(
        engine_version=ENGINE_VERSION, prompt_key=profile.prompt_key, prompt_version=prompt_library.version_of(profile.prompt_key), system_prompt_sha256=_sha256(system_prompt),
        tool_catalog_sha256=registry.catalog_hash(profile.offered_tools),
        offered_tools=[
            {"name": tool.name, "version": tool.version, "source": tool.source, "schemaSha256": _sha256(json.dumps(spec.parameters_schema, sort_keys=True))}
            for tool, spec in zip(profile.offered_tools, tool_specs, strict=True)
        ],
        provider_name=settings.llm_provider.value, model_name=gateway.model_name_for(model_tier), model_tier=model_tier.value,
        tool_calling_mode=ToolCallingMode.SCRIPTED_MOCK if gateway.is_mock else _TOOL_CALLING_MODE_BY_SUPPORT[capabilities.tool_calling],
        limits={
            "maximumToolCalls": profile.maximum_tool_calls, "maximumParallelToolCalls": settings.ask_keigan_max_parallel_tool_calls, "toolTimeoutSeconds": settings.ask_keigan_tool_timeout_seconds,
            "answerTokenBudget": settings.ask_keigan_answer_token_budget, "toolOutputModelCharacters": settings.ask_keigan_tool_output_model_characters,
            "toolOutputStoredCharacters": settings.ask_keigan_tool_output_stored_characters, "toolOutputPreviewCharacters": settings.ask_keigan_tool_output_preview_characters,
            "followUpQuestionLimit": settings.ask_keigan_follow_up_question_limit, "capabilities": capabilities.model_dump(mode="json"),
        },
    )
    return PreparedRun(profile, model_tier, system_prompt, tool_specs, setup)


def _ensure_the_prompt_fits(
    system_prompt: str, tool_specs: Sequence[AgentToolSpec], profile: ScopeProfile, capabilities: ModelCapabilities, settings: Settings, model_tier: ModelTier, language_code: str | None,
) -> None:
    """The prompt, the tool schemas and the context sections, plus room for the largest tool results the answer may collect, must fit the model's context window."""
    fixed_text = "\n".join([system_prompt, json.dumps([spec.parameters_schema for spec in tool_specs]), *(section.content for section in profile.context_sections)])
    room_for_tool_results = profile.maximum_tool_calls * estimate_token_count("x" * settings.ask_keigan_tool_output_model_characters)
    if estimate_token_count(fixed_text) + room_for_tool_results > capabilities.max_context_tokens:
        raise LlmRequestRejectedException(AskKeiganErrorCatalogue.describe("ai_request_rejected", {"modelTier": model_tier.value}, language_code).detail)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

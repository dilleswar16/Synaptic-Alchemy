"""keigan/ai/model_capabilities.py: what a configured model can do comes from a catalog plus overrides, never from code (spec 23, section 4.6.2)."""

from __future__ import annotations

import json

import pytest

from keigan.ai.model_capabilities import ModelCapabilities, ToolCallingSupport, parse_capability_overrides, resolve_model_capabilities
from keigan.config.settings import LlmProviderName


def test_a_model_with_no_catalog_entry_gets_the_catalog_defaults() -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.GEMINI, "some-future-model")
    assert capabilities.tool_calling == ToolCallingSupport.NATIVE
    assert capabilities.parallel_tool_calls is False
    assert capabilities.streams_text is True
    assert capabilities.supports_tool_choice_none is False
    assert capabilities.supports_temperature is True
    assert capabilities.max_context_tokens == 128_000
    assert capabilities.structured_output_method is None


def test_the_first_entry_whose_model_pattern_matches_wins() -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.GEMINI, "gemini-2.5-pro")
    assert capabilities.parallel_tool_calls is True
    assert capabilities.max_context_tokens == 1_000_000


def test_flags_an_entry_does_not_state_come_from_the_defaults() -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.OPENAI_COMPATIBLE, "any-deployment-name")
    assert capabilities.supports_tool_choice_none is True
    assert capabilities.parallel_tool_calls is False
    assert capabilities.max_context_tokens == 128_000


def test_the_mock_provider_declares_scripted_tool_planning_as_native_and_streaming() -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock")
    assert capabilities.tool_calling == ToolCallingSupport.NATIVE
    assert capabilities.streams_text is True
    assert capabilities.reports_stream_usage is True


def test_an_override_entry_beats_the_catalog_for_the_same_model() -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "internal-*", "tool_calling": "prompted_json", "max_context_tokens": 32000}]}})
    capabilities = resolve_model_capabilities(LlmProviderName.OPENAI_COMPATIBLE, "internal-wrapper-1", overrides)
    assert capabilities.tool_calling == ToolCallingSupport.PROMPTED_JSON
    assert capabilities.max_context_tokens == 32_000
    assert capabilities.supports_tool_choice_none is False  # first match wins: the catalog's "*" entry is not merged in
    assert resolve_model_capabilities(LlmProviderName.OPENAI_COMPATIBLE, "other-model", overrides).tool_calling == ToolCallingSupport.NATIVE


def test_an_override_for_one_provider_does_not_change_another() -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "*", "tool_calling": "none"}]}})
    assert resolve_model_capabilities(LlmProviderName.GEMINI, "gemini-2.5-pro", overrides).tool_calling == ToolCallingSupport.NATIVE


def test_override_defaults_apply_to_models_that_no_entry_matches() -> None:
    overrides = json.dumps({"defaults": {"supports_temperature": False}})
    assert resolve_model_capabilities(LlmProviderName.GEMINI, "some-future-model", overrides).supports_temperature is False
    assert resolve_model_capabilities(LlmProviderName.GEMINI, "some-future-model").supports_temperature is True


def test_overrides_may_turn_tool_calling_off_for_a_model() -> None:
    overrides = json.dumps({"providers": {"azure_openai": [{"model": "legacy-*", "tool_calling": "none"}]}})
    assert resolve_model_capabilities(LlmProviderName.AZURE_OPENAI, "legacy-chat", overrides).tool_calling == ToolCallingSupport.NONE


def test_empty_or_blank_overrides_change_nothing() -> None:
    assert parse_capability_overrides("{}").providers == {}
    assert parse_capability_overrides("   ").providers == {}


def test_overrides_that_are_not_json_are_refused_with_the_setting_name() -> None:
    with pytest.raises(ValueError, match="LLM_MODEL_CAPABILITIES_JSON"):
        parse_capability_overrides("{nope")


def test_an_unknown_flag_is_refused_and_named() -> None:
    with pytest.raises(ValueError, match="streams_everything"):
        parse_capability_overrides('{"providers": {"mock": [{"model": "*", "streams_everything": true}]}}')


def test_an_unknown_provider_is_refused_and_named() -> None:
    with pytest.raises(ValueError, match="ollama"):
        parse_capability_overrides('{"providers": {"ollama": [{"model": "*"}]}}')


def test_an_unknown_tool_calling_value_is_refused() -> None:
    with pytest.raises(ValueError, match="tool_calling"):
        parse_capability_overrides('{"defaults": {"tool_calling": "maybe"}}')


def test_a_context_size_of_zero_is_refused() -> None:
    with pytest.raises(ValueError, match="max_context_tokens"):
        parse_capability_overrides('{"defaults": {"max_context_tokens": 0}}')


def test_an_entry_without_a_model_pattern_is_refused() -> None:
    with pytest.raises(ValueError, match="model"):
        parse_capability_overrides('{"providers": {"mock": [{"tool_calling": "native"}]}}')


def test_resolved_capabilities_cannot_be_changed_by_a_caller() -> None:
    capabilities = resolve_model_capabilities(LlmProviderName.MOCK, "mock")
    assert isinstance(capabilities, ModelCapabilities)
    with pytest.raises(ValueError):
        capabilities.streams_text = False  # type: ignore[misc]

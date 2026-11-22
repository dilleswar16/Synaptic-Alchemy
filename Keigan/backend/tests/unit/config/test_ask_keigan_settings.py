"""keigan/config/settings.py: the Ask Keigan limits are validated settings with documented defaults (spec 23, section 4.7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keigan.config.settings import STALE_RUN_MINIMUM_HEARTBEATS, Settings


def build_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, environment="test", **overrides)  # type: ignore[arg-type]


def test_the_defaults_are_the_documented_values() -> None:
    settings = build_settings()
    assert settings.ask_keigan_max_tool_calls_global == 8
    assert settings.ask_keigan_max_tool_calls_investigation == 6
    assert settings.ask_keigan_max_parallel_tool_calls == 3
    assert settings.ask_keigan_tool_timeout_seconds == 60
    assert settings.ask_keigan_stale_run_seconds == 300
    assert settings.ask_keigan_progress_heartbeat_seconds == 15
    assert settings.ask_keigan_digest_timeline_events == 15
    assert settings.ask_keigan_digest_topology_nodes == 40
    assert settings.ask_keigan_digest_evidence_summary_characters == 300
    assert settings.ask_keigan_answer_token_budget == 80_000
    assert settings.ask_keigan_tool_output_model_characters == 6000
    assert settings.ask_keigan_tool_output_stored_characters == 60_000
    assert settings.ask_keigan_tool_output_preview_characters == 1500
    assert settings.ask_keigan_tool_list_item_limit == 20
    assert settings.ask_keigan_tool_passage_characters == 2400
    assert settings.ask_keigan_log_query_max_lookback_minutes == 43_200
    assert settings.ask_keigan_knowledge_token_budget == 2500
    assert settings.ask_keigan_heartbeat_seconds == 15
    assert settings.ask_keigan_protocol_repair_attempts == 1
    assert settings.ask_keigan_follow_up_question_limit == 3
    assert settings.ask_keigan_event_queue_size == 1000
    assert settings.ask_keigan_shutdown_grace_seconds == 10
    assert settings.llm_model_capabilities_json == "{}"
    assert settings.llm_managed_identity_scope == "https://cognitiveservices.azure.com/.default"


def test_nothing_expires_by_default() -> None:
    assert build_settings().ask_keigan_trace_retention_days is None


def test_an_empty_trace_retention_in_the_environment_means_keep_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_KEIGAN_TRACE_RETENTION_DAYS", "")
    assert build_settings().ask_keigan_trace_retention_days is None


def test_the_limits_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASK_KEIGAN_MAX_TOOL_CALLS_GLOBAL", "12")
    monkeypatch.setenv("ASK_KEIGAN_TRACE_RETENTION_DAYS", "90")
    settings = build_settings()
    assert settings.ask_keigan_max_tool_calls_global == 12
    assert settings.ask_keigan_trace_retention_days == 90


@pytest.mark.parametrize(
    ("setting_name", "lowest_allowed", "highest_allowed"),
    [
        ("ask_keigan_max_tool_calls_global", 1, 50),
        ("ask_keigan_max_tool_calls_investigation", 1, 50),
        ("ask_keigan_max_parallel_tool_calls", 1, 5),
        ("ask_keigan_tool_timeout_seconds", 5, 600),
        ("ask_keigan_stale_run_seconds", 60, 3600),
        ("ask_keigan_answer_token_budget", 5000, 1_000_000),
        ("ask_keigan_tool_output_model_characters", 500, 50_000),
        ("ask_keigan_tool_output_preview_characters", 200, 10_000),
        ("ask_keigan_tool_list_item_limit", 1, 200),
        ("ask_keigan_tool_passage_characters", 200, 20_000),
        ("ask_keigan_log_query_max_lookback_minutes", 5, 43_200),
        ("ask_keigan_knowledge_token_budget", 500, 20_000),
        ("ask_keigan_heartbeat_seconds", 5, 60),
        ("ask_keigan_protocol_repair_attempts", 0, 2),
        ("ask_keigan_follow_up_question_limit", 0, 5),
        ("ask_keigan_event_queue_size", 100, 100_000),
        ("ask_keigan_shutdown_grace_seconds", 1, 120),
        ("ask_keigan_trace_retention_days", 30, 3650),
    ],
)
def test_each_limit_accepts_its_bounds_and_refuses_one_step_outside(setting_name: str, lowest_allowed: int, highest_allowed: int) -> None:
    assert getattr(build_settings(**{setting_name: lowest_allowed}), setting_name) == lowest_allowed
    assert getattr(build_settings(**{setting_name: highest_allowed}), setting_name) == highest_allowed
    with pytest.raises(ValidationError, match=setting_name):
        build_settings(**{setting_name: lowest_allowed - 1})
    with pytest.raises(ValidationError, match=setting_name):
        build_settings(**{setting_name: highest_allowed + 1})


def test_the_stored_output_size_accepts_its_bounds_and_refuses_one_step_outside() -> None:
    smallest_companions = {"ask_keigan_tool_output_model_characters": 500, "ask_keigan_tool_output_preview_characters": 200}
    assert build_settings(ask_keigan_tool_output_stored_characters=1000, **smallest_companions).ask_keigan_tool_output_stored_characters == 1000
    assert build_settings(ask_keigan_tool_output_stored_characters=1_000_000).ask_keigan_tool_output_stored_characters == 1_000_000
    with pytest.raises(ValidationError, match="ask_keigan_tool_output_stored_characters"):
        build_settings(ask_keigan_tool_output_stored_characters=999, **smallest_companions)
    with pytest.raises(ValidationError, match="ask_keigan_tool_output_stored_characters"):
        build_settings(ask_keigan_tool_output_stored_characters=1_000_001)


def test_a_preview_longer_than_what_is_stored_is_refused() -> None:
    with pytest.raises(ValidationError, match="ASK_KEIGAN_TOOL_OUTPUT_PREVIEW_CHARACTERS"):
        build_settings(ask_keigan_tool_output_stored_characters=1000, ask_keigan_tool_output_model_characters=500, ask_keigan_tool_output_preview_characters=1001)


def test_a_model_view_longer_than_what_is_stored_is_refused() -> None:
    with pytest.raises(ValidationError, match="ASK_KEIGAN_TOOL_OUTPUT_MODEL_CHARACTERS"):
        build_settings(ask_keigan_tool_output_stored_characters=1000, ask_keigan_tool_output_preview_characters=200, ask_keigan_tool_output_model_characters=1001)


def test_a_run_counts_as_stale_only_after_several_missed_heartbeats() -> None:
    # The heartbeat refreshes last_progress_at while a model turn or tool call is in flight, so the longest silence of a live run is one beat (plus one database write):
    # the stale limit must leave room for several missed beats before a run is called interrupted, whatever the provider timeouts and retries are.
    assert build_settings(ask_keigan_stale_run_seconds=60, ask_keigan_progress_heartbeat_seconds=60 // STALE_RUN_MINIMUM_HEARTBEATS).ask_keigan_stale_run_seconds == 60
    with pytest.raises(ValidationError, match="ASK_KEIGAN_STALE_RUN_SECONDS"):
        build_settings(ask_keigan_stale_run_seconds=60, ask_keigan_progress_heartbeat_seconds=60 // STALE_RUN_MINIMUM_HEARTBEATS + 1)


def test_the_default_stale_limit_leaves_many_beats_of_room() -> None:
    settings = build_settings()
    assert settings.ask_keigan_stale_run_seconds >= STALE_RUN_MINIMUM_HEARTBEATS * settings.ask_keigan_progress_heartbeat_seconds


@pytest.mark.parametrize(("setting_name", "lowest_allowed", "highest_allowed"), [
    ("ask_keigan_progress_heartbeat_seconds", 5, 300), ("ask_keigan_digest_timeline_events", 0, 100), ("ask_keigan_digest_topology_nodes", 0, 500),
    ("ask_keigan_digest_evidence_summary_characters", 50, 2000),
])
def test_the_heartbeat_and_digest_limits_accept_their_bounds_and_refuse_one_step_outside(setting_name: str, lowest_allowed: int, highest_allowed: int) -> None:
    companions = {"ask_keigan_stale_run_seconds": 3600}  # leaves room for the longest heartbeat
    assert getattr(build_settings(**{setting_name: lowest_allowed}, **companions), setting_name) == lowest_allowed
    assert getattr(build_settings(**{setting_name: highest_allowed}, **companions), setting_name) == highest_allowed
    with pytest.raises(ValidationError, match=setting_name):
        build_settings(**{setting_name: lowest_allowed - 1}, **companions)
    with pytest.raises(ValidationError, match=setting_name):
        build_settings(**{setting_name: highest_allowed + 1}, **companions)


def test_an_empty_managed_identity_scope_is_refused() -> None:
    with pytest.raises(ValidationError, match="llm_managed_identity_scope"):
        build_settings(llm_managed_identity_scope="")


def test_capability_overrides_that_are_not_valid_json_refuse_start_up() -> None:
    with pytest.raises(ValidationError, match="LLM_MODEL_CAPABILITIES_JSON"):
        build_settings(llm_model_capabilities_json="{not json")


def test_capability_overrides_with_an_unknown_key_refuse_start_up_and_name_the_key() -> None:
    with pytest.raises(ValidationError, match="tool_callingg"):
        build_settings(llm_model_capabilities_json='{"defaults": {"tool_callingg": "native"}}')


def test_valid_capability_overrides_are_accepted() -> None:
    overrides = '{"providers": {"openai_compatible": [{"model": "my-model", "tool_calling": "prompted_json"}]}}'
    assert build_settings(llm_model_capabilities_json=overrides).llm_model_capabilities_json == overrides

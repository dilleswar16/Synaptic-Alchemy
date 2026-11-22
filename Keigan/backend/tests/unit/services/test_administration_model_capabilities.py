"""keigan/services/administration_model_capabilities.py: what the administration page shows about the configured models (spec 23, phase 4 row 4.5)."""

from __future__ import annotations

import json
from pathlib import Path

from keigan.config.settings import LlmProviderName, Settings
from keigan.services.administration_model_capabilities import last_conformance_report, model_capability_views


def build_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, environment="test", **overrides)  # type: ignore[arg-type]


def test_every_model_tier_is_listed_with_its_resolved_capabilities() -> None:
    settings = build_settings(llm_provider=LlmProviderName.GEMINI, llm_api_key="test-key", llm_fast_model="gemini-2.5-flash", llm_deep_model="gemini-2.5-pro", llm_vision_model="gemini-2.5-flash")
    views = model_capability_views(settings)
    assert [view.model_tier for view in views] == ["fast", "deep", "vision"]
    assert [view.model_name for view in views] == ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash"]
    assert all(view.max_context_tokens > 0 and view.tool_calling in {"native", "prompted_json", "none"} for view in views)


def test_an_override_in_the_settings_wins_over_the_catalogue() -> None:
    overrides = json.dumps({"providers": {"openai_compatible": [{"model": "my-wrapper-*", "tool_calling": "prompted_json", "max_context_tokens": 32000}]}})
    settings = build_settings(llm_provider=LlmProviderName.OPENAI_COMPATIBLE, llm_fast_model="my-wrapper-small", llm_deep_model="my-wrapper-large", llm_vision_model="my-wrapper-small",
                              llm_base_url="https://gateway.example/v1", llm_api_key="test-key", llm_model_capabilities_json=overrides)
    deep = next(view for view in model_capability_views(settings) if view.model_tier == "deep")
    assert (deep.tool_calling, deep.max_context_tokens) == ("prompted_json", 32000)


def test_no_report_file_means_no_last_report(tmp_path: Path) -> None:
    assert last_conformance_report(tmp_path / "missing.json") is None


def test_a_written_report_is_summarised(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "generatedAt": "2026-11-23T05:00:00+00:00", "passed": False, "providerName": "gemini", "modelName": "gemini-2.5-pro", "toolCallingMode": "native",
        "summary": {"scenarioCount": 11, "passedCount": 9}, "scenarios": [],
    }), encoding="utf-8")
    summary = last_conformance_report(report_path)
    assert summary is not None
    assert (summary.provider_name, summary.model_name, summary.tool_calling_mode, summary.scenario_count, summary.passed_count, summary.passed) == ("gemini", "gemini-2.5-pro", "native", 11, 9, False)
    assert summary.generated_at.isoformat() == "2026-11-23T05:00:00+00:00"


def test_a_file_that_is_not_a_report_is_ignored_not_fatal(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text("this is not json", encoding="utf-8")
    assert last_conformance_report(report_path) is None
    report_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
    assert last_conformance_report(report_path) is None

"""keigan/services/ask_keigan_conformance_suite.py and the live script's pieces, offline: the suite, the observing gateway and the report on disk (spec 23, 4.6.6, AC-33).

The live script was never run against a real model (there is no key here); it was run with ``LLM_PROVIDER=mock``, which uses the same code path with the offline planner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keigan.ai.llm_gateway import LlmGateway
from keigan.config.settings import LlmProviderName, get_settings
from keigan.services.ask_keigan_conformance_report import write_report
from keigan.services.ask_keigan_conformance_runner import local_user, lowered_limits
from keigan.services.ask_keigan_conformance_scenarios import ScenarioMode, load_scenarios, scenarios_for
from keigan.services.ask_keigan_conformance_suite import run_suite

pytestmark = pytest.mark.usefixtures("seed_context")


async def test_a_suite_run_with_the_offline_planner_reports_every_live_scenario_and_the_capabilities_it_saw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    report = await run_suite(LlmGateway(get_settings()), ScenarioMode.LIVE, scenarios_for(ScenarioMode.LIVE))
    assert [scenario.scenario_id for scenario in report.scenarios] == [scenario.id for scenario in scenarios_for(ScenarioMode.LIVE)]
    assert report.passed, [(scenario.scenario_id, scenario.failures) for scenario in report.scenarios if not scenario.passed]
    assert report.provider_name == "mock" and report.tool_calling_mode == "scripted_mock" and report.model_name == "mock"
    assert report.configured_capabilities["tool_calling"] == "native"
    assert report.observations.streamed_text_seen and not report.observations.stream_usage_reported  # the planner's counts are estimates
    target = tmp_path / "report.json"
    write_report(report, target)
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["summary"] == {"scenarioCount": len(report.scenarios), "passedCount": len(report.scenarios)} and written["passed"] is True


async def test_a_scenario_that_cannot_be_set_up_is_reported_as_failed_and_the_others_still_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    broken = load_scenarios()[0].model_copy(update={"user": "nobody@keigan.local"})
    working = load_scenarios()[7]  # C8: the question outside Keigan's data
    report = await run_suite(LlmGateway(get_settings()), ScenarioMode.LIVE, [broken, working])
    assert [scenario.passed for scenario in report.scenarios] == [False, True]
    assert "could not be run" in report.scenarios[0].failures[0] and report.passed is False


def test_the_scenarios_limits_are_in_force_only_while_it_runs() -> None:
    settings = get_settings()
    before = settings.ask_keigan_max_tool_calls_global
    with lowered_limits({"ask_keigan_max_tool_calls_global": 1}):
        assert settings.ask_keigan_max_tool_calls_global == 1
    assert settings.ask_keigan_max_tool_calls_global == before


def test_a_demo_user_is_built_with_the_groups_and_the_admin_flag_of_the_local_users_file() -> None:
    reader, admin = local_user("RUI.reader@keigan.local"), local_user("keigan.admin@keigan.local")
    assert reader.group_names == {"CLMJP_reader", "PAYAU_reader"} and reader.is_keigan_admin is False and reader.preferred_locale == "en"
    assert admin.is_keigan_admin is True

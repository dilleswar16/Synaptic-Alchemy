"""The conformance scenarios of spec 23, 4.6.6, run offline through the real engine, tools, trace and gateway: with the mock planner, and with a scripted model through native
tool calling and through the prompted-JSON protocol. The same expectations are judged in every mode (AC-17, AC-28, AC-29)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from keigan.ai.llm_gateway import LlmGateway, ModelTier
from keigan.config.settings import LlmProviderName, get_settings
from keigan.services.ask_keigan_conformance_checks import ObservedRun
from keigan.services.ask_keigan_conformance_runner import run_scenario
from keigan.services.ask_keigan_conformance_scenarios import Scenario, ScenarioMode, load_scenarios, scenarios_for
from support.conformance_scripted_model import ConformanceScriptedModel

pytestmark = pytest.mark.usefixtures("seed_context")


def gateway_factory(mode: ScenarioMode, monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = get_settings()
    if mode is ScenarioMode.MOCK:
        monkeypatch.setattr(settings, "llm_provider", LlmProviderName.MOCK)
        return lambda scenario: LlmGateway(settings)
    monkeypatch.setattr(settings, "llm_provider", LlmProviderName.OPENAI_COMPATIBLE)
    monkeypatch.setattr(settings, "llm_api_key", "a-key")
    monkeypatch.setattr(LlmGateway, "_retry_delay_seconds", staticmethod(lambda attempt_index: 0.0))
    tool_calling = "native" if mode is ScenarioMode.NATIVE else "prompted_json"
    monkeypatch.setattr(settings, "llm_model_capabilities_json", json.dumps({"providers": {"openai_compatible": [{"model": "*", "tool_calling": tool_calling, "parallel_tool_calls": True}]}}))

    def build(scenario: Scenario) -> LlmGateway:
        gateway = LlmGateway(settings)
        gateway._chat_models_by_tier[ModelTier.DEEP] = ConformanceScriptedModel(script=list(scenario.offline_script), tool_mode=mode.value)  # type: ignore[arg-type]
        return gateway

    return build


OFFLINE_MODES = (ScenarioMode.MOCK, ScenarioMode.NATIVE, ScenarioMode.PROMPTED)
CASES = [pytest.param(mode, scenario, id=f"{scenario.id}-{mode.value}") for mode in OFFLINE_MODES for scenario in scenarios_for(mode)]


@pytest.mark.parametrize(("mode", "scenario"), CASES)
async def test_the_scenario_passes(mode: ScenarioMode, scenario: Scenario, monkeypatch: pytest.MonkeyPatch) -> None:
    report, observed = await run_scenario(scenario, gateway_factory(mode, monkeypatch), mode)
    assert report.failures == [], f"{scenario.id} in {mode.value} mode: {report.failures}; the calls were {report.tools_called}; the answer was {report.answer_text!r}"
    expected_mode = {ScenarioMode.MOCK: "scripted_mock", ScenarioMode.NATIVE: "native", ScenarioMode.PROMPTED: "prompted_json"}[mode]
    assert observed.tool_calling_mode == expected_mode


def test_every_scenario_runs_offline_in_at_least_one_mode_and_the_first_set_is_there() -> None:
    assert {scenario.id for scenario in load_scenarios()} >= {f"C{number}" for number in range(1, 11)}
    assert all(set(scenario.runs_in) & set(OFFLINE_MODES) for scenario in load_scenarios())


def test_the_same_scenarios_run_in_both_tool_modes_except_the_ones_about_one_of_them() -> None:
    native, prompted = {scenario.id for scenario in scenarios_for(ScenarioMode.NATIVE)}, {scenario.id for scenario in scenarios_for(ScenarioMode.PROMPTED)}
    assert native ^ prompted == {"C14"}  # the prompted protocol's own failure
    assert {"C1", "C2", "C3"} <= native & prompted  # AC-28: the same steps in both modes


@pytest.mark.parametrize("scenario_id", ["C1", "C2", "C3"])
async def test_prompted_mode_produces_the_same_calls_and_turns_as_native_mode(scenario_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = next(scenario for scenario in load_scenarios() if scenario.id == scenario_id)
    _, native = await run_scenario(scenario, gateway_factory(ScenarioMode.NATIVE, monkeypatch), ScenarioMode.NATIVE)
    _, prompted = await run_scenario(scenario, gateway_factory(ScenarioMode.PROMPTED, monkeypatch), ScenarioMode.PROMPTED)
    def shape(run: ObservedRun) -> list[tuple[str, dict[str, Any], str, str | None]]:
        # every run has its own investigation (the fixture makes a new one), so the bound id is left out
        return [(call.tool_name, {name: value for name, value in call.arguments.items() if name != "investigation_id"}, call.status.value, call.citation_code) for call in run.calls]

    assert shape(prompted) == shape(native)
    assert len(prompted.turns) == len(native.turns) and prompted.citation_codes == native.citation_codes
    assert (native.tool_calling_mode, prompted.tool_calling_mode) == ("native", "prompted_json")


async def test_a_run_that_goes_wrong_is_a_failed_scenario_in_the_report_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = next(scenario for scenario in load_scenarios() if scenario.id == "C2")
    broken = scenario.model_copy(update={"offline_script": scenario.offline_script[:1]})  # the model is asked for a second turn the script does not have
    report, observed = await run_scenario(broken, gateway_factory(ScenarioMode.NATIVE, monkeypatch), ScenarioMode.NATIVE)
    assert report.passed is False and observed.run_status == "failed" and any("failed" in failure for failure in report.failures)

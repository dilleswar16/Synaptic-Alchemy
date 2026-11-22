"""keigan/services/ask_keigan_conformance_scenarios.py: the shape of the scenario file and its checks (spec 23, 4.6.6)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from keigan.services.ask_keigan_conformance_scenarios import Scenario, ScenarioMode, load_scenarios, scenarios_for


def scenario_data(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "C99", "title": "t", "scope": "global", "user": "rui.reader@keigan.local", "question": "q", "runs_in": ["mock"], "expect": {}, **overrides,
    }


def test_the_shipped_scenarios_load_with_unique_ids_and_the_first_set() -> None:
    scenarios = load_scenarios()
    assert [scenario.id for scenario in scenarios][:10] == [f"C{number}" for number in range(1, 11)]
    assert len({scenario.id for scenario in scenarios}) == len(scenarios)


def test_every_tool_a_script_or_expectation_names_is_a_registered_tool() -> None:
    from keigan.ai.tool_registry import tool_registry
    from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools

    known = {tool.name for scope in ("global", "investigation") for tool in tool_registry.tools_for(_scope(scope))}
    named = {request.tool for scenario in load_scenarios() for turn in scenario.offline_script for request in turn.tool_requests or []}
    named |= {call.tool for scenario in load_scenarios() for call in scenario.expect.calls or []} | {tool for scenario in load_scenarios() for tool in scenario.expect.forbidden_tools}
    assert named <= known, named - known


def _scope(name: str) -> Any:
    from keigan.ai.tool_registry import AskKeiganScope

    return AskKeiganScope(name)


def test_a_scenario_that_runs_scripted_needs_a_script() -> None:
    with pytest.raises(ValidationError, match="needs an offline_script"):
        Scenario.model_validate(scenario_data(runs_in=["native"]))


def test_a_scenario_may_only_lower_settings_that_exist() -> None:
    with pytest.raises(ValidationError, match="do not exist"):
        Scenario.model_validate(scenario_data(limits={"ask_keigan_no_such_limit": 1}))


def test_a_scripted_turn_is_exactly_one_kind_of_turn() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Scenario.model_validate(scenario_data(runs_in=["native"], offline_script=[{"answer": "x", "raw": "y"}]))
    with pytest.raises(ValidationError, match="exactly one"):
        Scenario.model_validate(scenario_data(runs_in=["native"], offline_script=[{}]))


def test_an_unknown_key_in_the_file_is_an_error_not_ignored() -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate(scenario_data(expects={}))


def test_placeholders_are_filled_in_the_script_and_the_expectations_and_unknown_ones_are_left() -> None:
    scenario = Scenario.model_validate(scenario_data(
        runs_in=["native"], offline_script=[{"answer": "Hello ${name}, ${unknown}."}], expect={"forbidden_text": ["${name}"]},
    ))
    resolved = scenario.resolved({"name": "Hanako"})
    assert resolved.offline_script[0].answer == "Hello Hanako, ${unknown}." and resolved.expect.forbidden_text == ["Hanako"]


def test_scenarios_are_selected_by_mode_and_by_id() -> None:
    assert all(ScenarioMode.PROMPTED in scenario.runs_in for scenario in scenarios_for(ScenarioMode.PROMPTED))
    assert [scenario.id for scenario in scenarios_for(ScenarioMode.NATIVE, only="C3")] == ["C3"]
    assert scenarios_for(ScenarioMode.MOCK, only="C14") == []  # a scenario about the prompted protocol does not run with the planner

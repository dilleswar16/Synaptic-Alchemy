"""The offline model's fixes follow the rules of spec 33 (AC-26): templates with slots, no placeholder, nothing withheld, no chained command, for every simulator scenario."""

from __future__ import annotations

from typing import Any

import pytest

from keigan.ai.fix_step_validator import FixValidationContext, validate_fix_step
from keigan.ai.investigation_mock_responses import SCENARIO_SCRIPTS, MockInvestigationContext, MockServiceInfo, _restart_action, _rollback_action
from keigan.ai.fix_plan import build_fix_plan


def services() -> list[MockServiceInfo]:
    """One of every service type the mock writes commands for, with and without a resource group."""
    return [
        MockServiceInfo("s1", "claims-api", "aks", namespace="claims-prod"), MockServiceInfo("s2", "claims-web", "app-service-placeholder", resource_group="rg-claims-jp-prod"),
        MockServiceInfo("s3", "claims-func", "function_app", resource_group="rg-claims-jp-prod"), MockServiceInfo("s4", "no-group-web", "app_service"), MockServiceInfo("s5", "no-group-func", "function_app"),
        MockServiceInfo("s6", "claims-web2", "app_service", resource_group="rg-claims-jp-prod"),
    ]


def context_for(scenario_key: str, primary: str = "claims-api", dependency: str = "claims-func") -> MockInvestigationContext:
    evidence = [
        {"code": f"E{number}", "service_name": primary, "category": category, "strength": "high", "title": "t", "summary": "s", "is_rule_out": False}
        for number, category in enumerate(("error_logs", "failed_requests", "exceptions", "metrics", "pod_restarts", "failed_dependencies", "change_event"), start=1)
    ]
    return MockInvestigationContext("Claims", services(), evidence, scenario_key=scenario_key, primary_service_name=primary, dependency_service_name=dependency)


def validator_context(mock: MockInvestigationContext) -> FixValidationContext:
    catalogue = {value for service in mock.services for value in (service.name, service.namespace, service.resource_group, service.resource_identifier) if value}
    return FixValidationContext(
        catalogue_values=frozenset(catalogue), evidence_texts={item["code"]: "BATCH_IMPORT_PARALLELISM 4 to 16" for item in mock.evidence}, evidence_codes_with_query=frozenset(item["code"] for item in mock.evidence),
        knowledge_text="", maximum_command_characters=600, maximum_parameters_per_command=8, clean_markdown=lambda text: text, clean_line=lambda text: text,
    )


def validated_steps(scenario_key: str, primary: str = "claims-api") -> list[dict[str, Any]]:
    mock = context_for(scenario_key, primary)
    fix = SCENARIO_SCRIPTS[scenario_key]["fix"](mock)
    return [validate_fix_step(step, f"application-{number}", validator_context(mock)) for number, step in enumerate(fix.steps, start=1)]


@pytest.mark.parametrize("scenario_key", sorted(SCENARIO_SCRIPTS))
def test_no_step_the_offline_model_writes_is_withheld_or_has_a_placeholder(scenario_key: str) -> None:
    for primary in ("claims-api", "claims-web2", "no-group-web", "no-group-func"):
        for step in validated_steps(scenario_key, primary):
            for action in (step["action"], step["check"], step["revert"]):
                assert action is None or action["withheld_reason"] is None, (scenario_key, primary, step["title"], action and action["withheld_reason"])
                command = action["command"] if action else None
                if command:
                    assert "<" not in command["template"] and ";" not in command["template"] and "&&" not in command["template"], command["template"]


@pytest.mark.parametrize("scenario_key", sorted(SCENARIO_SCRIPTS))
def test_every_scenario_has_a_plan_and_every_step_that_changes_something_has_a_check_and_a_way_back(scenario_key: str) -> None:
    steps = validated_steps(scenario_key)
    assert steps and build_fix_plan("", [("application", number) for number in range(1, len(steps) + 1)], [{"analysis_perspective": "application", "proposed_fix": {"steps": steps}}], "application", 8)["step_references"]
    for step in steps:
        if step["purpose"] != "diagnose" and step["action"]["action_kind"] in ("command", "configuration_change"):
            assert "no_validation" not in step["warnings"] and "no_revert" not in step["warnings"], (scenario_key, step["title"], step["warnings"])


def test_a_service_without_a_resource_group_gets_a_fill_in_field_and_no_guess() -> None:
    action = _restart_action(MockServiceInfo("s4", "no-group-web", "app_service"))
    assert action.command is not None and "<" not in action.command.template
    group = next(parameter for parameter in action.command.parameters if parameter.name == "resource_group")
    assert group.value is None and group.value_source == "unknown"
    stored = validate_fix_step(
        __import__("keigan.ai.investigation_mock_responses", fromlist=["_step"])._step("Restart", "mitigate", "medium", action), "application-1",
        validator_context(context_for("database_connection_pool_exhaustion")),
    )
    assert stored["missing_value_count"] == 1 and stored["action"]["command"]["renderings"][0]["text"] is None


def test_a_service_with_a_resource_group_still_gets_its_command() -> None:
    action = _restart_action(MockServiceInfo("s2", "claims-web", "app_service", resource_group="rg-claims-jp-prod"))
    assert action.command is not None and action.command.template == "az webapp restart --name {{service}} --resource-group {{resource_group}}"
    assert [parameter.value for parameter in action.command.parameters] == ["claims-web", "rg-claims-jp-prod"]


def test_the_rollback_of_a_kubernetes_service_is_an_undo_of_its_deployment() -> None:
    action = _rollback_action(MockServiceInfo("s1", "claims-api", "aks", namespace="claims-prod"), "release 41")
    assert action.command is not None and action.command.template == "kubectl rollout undo deployment/{{deployment}} -n {{namespace}}"

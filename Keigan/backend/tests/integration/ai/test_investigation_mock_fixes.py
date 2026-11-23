"""The offline model's fixes follow the rules of spec 33 (AC-26): no placeholder, nothing withheld, no chained command, for every simulator scenario."""

from __future__ import annotations

from keigan.ai.fix_command_check import check_suggested_command
from keigan.ai.investigation_ai_schemas import FixStep
from keigan.ai.investigation_mock_responses import MockServiceInfo, _restart_command, _rollback_command, _setting_command


def services() -> list[MockServiceInfo]:
    """One of every service type the mock writes commands for, with and without a resource group."""
    return [
        MockServiceInfo("s1", "claims-api", "aks", namespace="claims-prod"), MockServiceInfo("s2", "claims-web", "app_service", resource_group="rg-claims-jp-prod"),
        MockServiceInfo("s3", "claims-func", "function_app", resource_group="rg-claims-jp-prod"), MockServiceInfo("s4", "no-group-web", "app_service"), MockServiceInfo("s5", "no-group-func", "function_app"),
    ]


def every_step() -> list[FixStep]:
    steps: list[FixStep] = []
    for service in [*services(), None]:
        steps += [_restart_command(service), _rollback_command(service, "release 41"), _setting_command(service, "Database__MaxPoolSize", "200")]
    return steps


def test_no_command_the_offline_model_writes_is_withheld_or_has_a_placeholder() -> None:
    for step in every_step():
        if step.command_text:
            assert "<" not in step.command_text and check_suggested_command(step.command_text, step.command_language, 600) is None, step.command_text


def test_a_service_without_a_resource_group_gets_a_description_to_look_it_up_and_no_command() -> None:
    step = _restart_command(MockServiceInfo("s4", "no-group-web", "app_service"))
    assert step.command_text is None and "resource group" in step.description


def test_a_service_with_a_resource_group_still_gets_its_command() -> None:
    step = _restart_command(MockServiceInfo("s2", "claims-web", "app_service", resource_group="rg-claims-jp-prod"))
    assert step.command_text == "az webapp restart --name claims-web --resource-group rg-claims-jp-prod"

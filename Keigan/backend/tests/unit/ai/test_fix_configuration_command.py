"""keigan/ai/fix_configuration_command.py: the command a setting change becomes, from the service's type and the catalogue (spec 33, 4.2.3)."""

from __future__ import annotations

import re

import pytest

from keigan.ai.fix_command_shape import SLOT_PATTERN, FixCommandTool
from keigan.ai.fix_configuration_command import ServiceFacts, command_for_change, configuration_command_entries
from keigan.ai.fix_parameter_kinds import kind_names
from keigan.ai.investigation_ai_schemas import ConfigurationChangeOutput, FixParameterOutput

APP_SERVICE = ServiceFacts(service_type="app_service", resource_group="rg-claims-jp-prod", namespace=None)
AKS_SERVICE = ServiceFacts(service_type="aks", resource_group="rg-claims-jp-prod", namespace="claims-prod")


def parameter(name: str, kind: str, value: str | None, source: str = "evidence", code: str | None = "E3") -> FixParameterOutput:
    return FixParameterOutput(name=name, value_kind=kind, value=value, value_source=source, source_code=code)  # type: ignore[arg-type]


def change(kind: str = "app_setting", service: str = "claims-web-jp", setting: str | None = "Database__MaxPoolSize", after: str | None = "16") -> ConfigurationChangeOutput:
    return ConfigurationChangeOutput(
        target_kind=kind, service_name=service, setting_name=parameter("setting", "configuration_key", setting, "knowledge", "K1"),  # type: ignore[arg-type]
        before_value=parameter("before", "configuration_value", "4"), after_value=parameter("after", "configuration_value", after, "runbook", "R1"),
    )


def by_name(command_parameters: list[FixParameterOutput]) -> dict[str, FixParameterOutput]:
    return {entry.name: entry for entry in command_parameters}


def test_an_app_service_setting_becomes_an_az_webapp_command() -> None:
    command = command_for_change(change(), {"claims-web-jp": APP_SERVICE})
    assert command is not None
    assert command.tool == FixCommandTool.AZ
    assert command.template == "az webapp config appsettings set --name {{service}} --resource-group {{resource_group}} --settings {{setting}}={{value}}"
    values = by_name(command.parameters)
    assert (values["service"].value, values["service"].value_kind, values["service"].value_source) == ("claims-web-jp", "azure_resource_name", "service_catalogue")
    assert (values["resource_group"].value, values["resource_group"].value_kind, values["resource_group"].value_source) == ("rg-claims-jp-prod", "azure_resource_group", "service_catalogue")


def test_the_setting_and_its_new_value_keep_the_source_the_model_gave() -> None:
    values = by_name(command_for_change(change(), {"claims-web-jp": APP_SERVICE}).parameters)  # type: ignore[union-attr]
    assert (values["setting"].value, values["setting"].value_source, values["setting"].source_code) == ("Database__MaxPoolSize", "knowledge", "K1")
    assert (values["value"].value, values["value"].value_source, values["value"].source_code) == ("16", "runbook", "R1")


def test_a_function_app_setting_uses_the_functionapp_command() -> None:
    facts = ServiceFacts(service_type="function_app", resource_group="rg-pay", namespace=None)
    command = command_for_change(change(service="payment-func"), {"payment-func": facts})
    assert command is not None and command.template.startswith("az functionapp config appsettings set --name {{service}}")


def test_a_kubernetes_environment_variable_becomes_kubectl_set_env_with_the_namespace_from_the_catalogue() -> None:
    command = command_for_change(change(kind="kubernetes_environment_variable", service="claims-api"), {"claims-api": AKS_SERVICE})
    assert command is not None and command.tool == FixCommandTool.KUBECTL
    assert command.template == "kubectl set env deployment/{{deployment}} -n {{namespace}} {{setting}}={{value}}"
    assert by_name(command.parameters)["namespace"].value == "claims-prod"


def test_the_deployment_name_is_the_service_name_but_not_claimed_to_come_from_the_catalogue() -> None:
    values = by_name(command_for_change(change(kind="kubernetes_environment_variable", service="claims-api"), {"claims-api": AKS_SERVICE}).parameters)  # type: ignore[union-attr]
    assert values["deployment"].value == "claims-api" and values["deployment"].value_source == "unknown"


def test_a_value_the_catalogue_does_not_have_is_left_empty_so_the_person_fills_it_in() -> None:
    facts = ServiceFacts(service_type="app_service", resource_group=None, namespace=None)
    values = by_name(command_for_change(change(), {"claims-web-jp": facts}).parameters)  # type: ignore[union-attr]
    assert values["resource_group"].value is None


@pytest.mark.parametrize("target", ["helm_value", "file"])
def test_a_helm_value_or_a_file_stays_an_edit(target: str) -> None:
    assert command_for_change(change(kind=target), {"claims-web-jp": APP_SERVICE}) is None


def test_a_service_the_catalogue_does_not_know_stays_an_edit() -> None:
    assert command_for_change(change(service="claims-web-us"), {"claims-web-jp": APP_SERVICE}) is None


def test_a_service_type_without_an_entry_stays_an_edit() -> None:
    assert command_for_change(change(), {"claims-web-jp": ServiceFacts(service_type="sql_database", resource_group="rg", namespace=None)}) is None


@pytest.mark.parametrize("setting, after", [(None, "16"), ("Database__MaxPoolSize", None)])
def test_a_change_without_its_setting_or_its_new_value_has_no_command(setting: str | None, after: str | None) -> None:
    assert command_for_change(change(setting=setting, after=after), {"claims-web-jp": APP_SERVICE}) is None


def test_the_catalogue_is_consistent() -> None:
    entries = configuration_command_entries()
    assert entries
    for entry in entries:
        slots = set(SLOT_PATTERN.findall(entry.template))
        assert slots == set(entry.parameters), entry.template
        assert entry.tool in {tool.value for tool in FixCommandTool}
        assert {definition.kind for definition in entry.parameters.values()} <= set(kind_names())
        assert len({(other.target_kind, other.service_type) for other in entries}) == len(entries)
        assert re.fullmatch(r"[a-z_]+", entry.service_type)

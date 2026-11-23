"""The command a configuration change becomes (spec 33, 4.2.3).

A suggested setting change names the service, the setting and the new value. For a service type the catalogue (``resources/catalogs/fix_configuration_commands.yaml``) knows, this module writes
the command that sets it, with every value taken from where it is known: the service's own name, resource group and namespace from the catalogue, the setting and its new value from what the
model named. Nothing is invented: a value the catalogue does not hold stays empty (a fill-in field), and a deployment name, which the catalogue does not hold, is the service's name marked unverified.
The command goes through the same checks as any other (``validate_command``); this module only builds it. Pure: no model, no database.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import yaml

from keigan.ai.fix_command_shape import FixCommandTool
from keigan.ai.investigation_ai_schemas import ConfigurationChangeOutput, FixCommandOutput, FixParameterOutput
from keigan.config.settings import RESOURCES_DIRECTORY

ParameterOrigin = Literal["service_name", "service_name_as_deployment", "resource_group", "namespace", "setting_name", "after_value"]


@dataclass(frozen=True)
class ServiceFacts:
    """What the application's catalogue holds about one service."""

    service_type: str
    resource_group: str | None
    namespace: str | None


@dataclass(frozen=True)
class ParameterDefinition:
    kind: str
    origin: ParameterOrigin


@dataclass(frozen=True)
class ConfigurationCommandEntry:
    target_kind: str
    service_type: str
    tool: str
    template: str
    parameters: dict[str, ParameterDefinition]


@lru_cache
def configuration_command_entries() -> tuple[ConfigurationCommandEntry, ...]:
    document = yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "fix_configuration_commands.yaml").read_text(encoding="utf-8"))
    return tuple(
        ConfigurationCommandEntry(
            entry["target_kind"], entry["service_type"], entry["tool"], entry["template"],
            {name: ParameterDefinition(definition["kind"], definition["from"]) for name, definition in entry["parameters"].items()},
        )
        for entry in document["entries"]
    )


def _entry_for(target_kind: str, service_type: str) -> ConfigurationCommandEntry | None:
    return next((entry for entry in configuration_command_entries() if entry.target_kind == target_kind and entry.service_type == service_type), None)


def _parameter(name: str, definition: ParameterDefinition, change: ConfigurationChangeOutput, facts: ServiceFacts) -> FixParameterOutput:
    origin = definition.origin
    if origin == "setting_name":
        given = change.setting_name
        return FixParameterOutput(name=name, value_kind=definition.kind, value=given.value, value_source=given.value_source, source_code=given.source_code)  # type: ignore[arg-type]
    if origin == "after_value":
        given = change.after_value
        return FixParameterOutput(name=name, value_kind=definition.kind, value=given.value, value_source=given.value_source, source_code=given.source_code)  # type: ignore[arg-type]
    if origin == "service_name_as_deployment":
        return FixParameterOutput(name=name, value_kind=definition.kind, value=change.service_name, value_source="unknown")  # type: ignore[arg-type]
    value = {"service_name": change.service_name, "resource_group": facts.resource_group, "namespace": facts.namespace}[origin]
    return FixParameterOutput(name=name, value_kind=definition.kind, value=value, value_source="service_catalogue" if value else "unknown")  # type: ignore[arg-type]


def command_for_change(change: ConfigurationChangeOutput, services: Mapping[str, ServiceFacts]) -> FixCommandOutput | None:
    """The command that makes ``change``, or None when the change stays an edit (no entry for its target and service type, an unknown service, or no setting or new value)."""
    facts = services.get(change.service_name)
    if facts is None or not change.setting_name.value or not change.after_value.value:
        return None
    entry = _entry_for(change.target_kind, facts.service_type)
    if entry is None:
        return None
    parameters = [_parameter(name, definition, change, facts) for name, definition in entry.parameters.items()]
    return FixCommandOutput(tool=FixCommandTool(entry.tool), dialect="any", template=entry.template, parameters=parameters)  # type: ignore[arg-type]

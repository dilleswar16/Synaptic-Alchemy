"""The action item settings are documented where an operator looks (``.env.example`` with one comment line each, and the Helm values), with the defaults of ``settings.py``, and are validated."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import ENV_EXAMPLE, HELM_VALUES, environment_lines

ACTION_ITEM_FIELDS = sorted(name for name in Settings.model_fields if name.startswith("action_items_"))


def default_text(field_name: str) -> str:
    default = Settings.model_fields[field_name].default
    return str(default).lower() if isinstance(default, bool) else str(default)


def test_there_are_settings_to_document() -> None:
    assert len(ACTION_ITEM_FIELDS) >= 12 and ENV_EXAMPLE.exists()


@pytest.mark.parametrize("field_name", ACTION_ITEM_FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value is not None, f"{field_name.upper()} is missing from .env.example"
    assert value == default_text(field_name)
    assert line_above.startswith("# ") and len(line_above) > 10, f"{field_name.upper()} needs its own comment line above it"


@pytest.mark.parametrize("field_name", ACTION_ITEM_FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    backend_environment = yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"]
    assert field_name.upper() in backend_environment, f"{field_name.upper()} is missing from the Helm backendEnvironment"
    assert str(backend_environment[field_name.upper()]).lower() == default_text(field_name).lower()


def test_an_unknown_escalation_role_stops_startup() -> None:
    with pytest.raises(ValidationError, match="unknown team roles: captain"):
        Settings(action_items_escalation_roles="lead,captain")


def test_the_escalation_roles_are_a_list() -> None:
    assert Settings(action_items_escalation_roles="lead, manager ,").action_items_escalation_role_list == ["lead", "manager"]


def test_an_invalid_external_reference_pattern_stops_startup() -> None:
    with pytest.raises(ValidationError, match="not a valid regular expression"):
        Settings(action_items_external_reference_pattern="([")


@pytest.mark.parametrize(("name", "value"), [("action_items_reminder_hour_local", 24), ("action_items_overdue_reminder_interval_days", 0), ("action_items_maximum_per_postmortem", 21)])
def test_a_value_outside_its_range_stops_startup(name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{name: value})

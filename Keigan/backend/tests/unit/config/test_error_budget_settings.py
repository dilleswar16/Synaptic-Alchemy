"""The error budget policy settings are documented (.env.example with a comment line each, Helm values) with the defaults of settings.py, and validated (spec 30, AC-18)."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import HELM_VALUES, environment_lines

FIELDS = sorted(name for name in Settings.model_fields if name.startswith("error_budget_policy_"))


def default_text(field_name: str) -> str:
    default = Settings.model_fields[field_name].default
    return str(default).lower() if isinstance(default, bool) else str(default)


def test_there_are_settings_to_document() -> None:
    assert len(FIELDS) == 12


@pytest.mark.parametrize("field_name", FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value is not None, f"{field_name.upper()} is missing from .env.example"
    assert value == default_text(field_name)
    assert line_above.startswith("# ") and len(line_above) > 10


@pytest.mark.parametrize("field_name", FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    backend_environment = yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"]
    assert str(backend_environment[field_name.upper()]).lower() == default_text(field_name).lower()


def test_the_class_window_cannot_exceed_the_raw_measurement_retention() -> None:
    with pytest.raises(ValidationError, match="cannot exceed SLI_RAW_RETENTION_DAYS"):
        Settings(error_budget_policy_outage_class_window_days=120, sli_raw_retention_days=90)
    assert Settings(error_budget_policy_outage_class_window_days=120, sli_raw_retention_days=120).error_budget_policy_outage_class_window_days == 120


def test_an_unknown_notification_role_stops_startup() -> None:
    with pytest.raises(ValidationError, match="unknown team roles: boss"):
        Settings(error_budget_policy_notification_roles="lead,boss")
    assert Settings(error_budget_policy_notification_roles="lead, manager").error_budget_policy_notification_role_list == ["lead", "manager"]


@pytest.mark.parametrize(("name", "value"), [("error_budget_policy_single_incident_threshold_percent", 0.5), ("error_budget_policy_final_after_hours", 0), ("error_budget_policy_minimum_data_coverage_percent", 5)])
def test_a_value_outside_its_range_stops_startup(name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{name: value})

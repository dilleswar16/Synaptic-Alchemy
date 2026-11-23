"""The similar incident memory settings are documented where an operator looks (``.env.example`` with one comment line each, and the Helm values), with the defaults of ``settings.py``, and are validated."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import ENV_EXAMPLE, HELM_VALUES, environment_lines

MEMORY_FIELDS = sorted(name for name in Settings.model_fields if name.startswith("incident_memory_"))


def default_text(field_name: str) -> str:
    default = Settings.model_fields[field_name].default
    return str(default).lower() if isinstance(default, bool) else str(default)


def test_there_are_settings_to_document() -> None:
    assert len(MEMORY_FIELDS) >= 5 and ENV_EXAMPLE.exists()


@pytest.mark.parametrize("field_name", MEMORY_FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value is not None, f"{field_name.upper()} is missing from .env.example"
    assert value == default_text(field_name)
    assert line_above.startswith("# ") and len(line_above) > 10, f"{field_name.upper()} needs its own comment line above it"


@pytest.mark.parametrize("field_name", MEMORY_FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    backend_environment = yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"]
    assert field_name.upper() in backend_environment, f"{field_name.upper()} is missing from the Helm backendEnvironment"
    assert str(backend_environment[field_name.upper()]).lower() == default_text(field_name).lower()


@pytest.mark.parametrize(
    ("name", "value"),
    [("incident_memory_maximum_shown", 0), ("incident_memory_maximum_shown", 21), ("incident_memory_minimum_score", 1.1), ("incident_memory_stale_after_days", 6),
     ("incident_memory_text_maximum_characters", 99), ("incident_memory_keyword_candidate_limit", 49)],
)
def test_a_value_outside_its_range_stops_startup(name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{name: value})

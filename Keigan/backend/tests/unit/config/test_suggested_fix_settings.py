"""The suggested fix settings are documented (.env.example with a comment line each, Helm values) with the defaults of settings.py and validated (spec 33, AC-25)."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import HELM_VALUES, environment_lines

FIELDS = sorted(name for name in Settings.model_fields if name.startswith("suggested_fix_"))


def default_text(field_name: str) -> str:
    return str(getattr(Settings.model_fields[field_name].default, "value", Settings.model_fields[field_name].default))


def test_there_are_five_settings_to_document() -> None:
    assert len(FIELDS) == 5


@pytest.mark.parametrize("field_name", FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value == default_text(field_name) and line_above.startswith("# ") and len(line_above) > 10


@pytest.mark.parametrize("field_name", FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    assert str(yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"][field_name.upper()]) == default_text(field_name)


@pytest.mark.parametrize(("name", "value"), [
    ("suggested_fix_maximum_command_characters", 79), ("suggested_fix_maximum_command_characters", 4001), ("suggested_fix_maximum_steps", 0), ("suggested_fix_maximum_steps", 13),
    ("suggested_fix_plan_maximum_steps", 21), ("suggested_fix_maximum_parameters_per_command", 0), ("suggested_fix_default_shell_dialect", "zsh"),
])
def test_a_value_outside_its_range_stops_startup(name: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{name: value})

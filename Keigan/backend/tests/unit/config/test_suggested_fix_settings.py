"""The suggested fix setting is documented (.env.example with a comment line, Helm values) with the default of settings.py and validated (spec 33, AC-25)."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import HELM_VALUES, environment_lines

FIELD = "suggested_fix_maximum_command_characters"


def test_env_example_has_the_setting_with_its_default_and_a_comment_line() -> None:
    value, line_above = environment_lines().get(FIELD.upper(), (None, ""))
    assert value == str(Settings.model_fields[FIELD].default) and line_above.startswith("# ") and len(line_above) > 10


def test_helm_values_have_the_setting_with_its_default() -> None:
    assert str(yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"][FIELD.upper()]) == str(Settings.model_fields[FIELD].default)


@pytest.mark.parametrize("value", [79, 4001])
def test_a_value_outside_its_range_stops_startup(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(suggested_fix_maximum_command_characters=value)

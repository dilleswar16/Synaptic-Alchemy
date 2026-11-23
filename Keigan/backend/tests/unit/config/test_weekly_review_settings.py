"""The weekly review setting is documented (.env.example with a comment line, Helm values) with the default of settings.py and validated (spec 31, AC-8)."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import HELM_VALUES, environment_lines

FIELD = "weekly_review_maximum_listed_items"


def test_env_example_has_the_setting_with_its_default_and_a_comment_line() -> None:
    value, line_above = environment_lines().get(FIELD.upper(), (None, ""))
    assert value == str(Settings.model_fields[FIELD].default) and line_above.startswith("# ") and len(line_above) > 10


def test_helm_values_have_the_setting_with_its_default() -> None:
    assert str(yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"][FIELD.upper()]) == str(Settings.model_fields[FIELD].default)


@pytest.mark.parametrize("value", [0, 51])
def test_a_value_outside_one_to_fifty_stops_startup(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(weekly_review_maximum_listed_items=value)

"""The runbook health settings are documented (.env.example with a comment line each, Helm values) with the defaults of settings.py and validated (spec 32, AC-7)."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from keigan.config.settings import Settings
from tests.unit.config.test_ask_keigan_deployment_settings import HELM_VALUES, environment_lines

FIELDS = sorted(name for name in Settings.model_fields if name.startswith("runbook_health_"))


def test_there_are_four_settings() -> None:
    assert len(FIELDS) == 4


@pytest.mark.parametrize("field_name", FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value == str(Settings.model_fields[field_name].default) and line_above.startswith("# ") and len(line_above) > 10


@pytest.mark.parametrize("field_name", FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    assert str(yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"][field_name.upper()]) == str(Settings.model_fields[field_name].default)


@pytest.mark.parametrize(("name", "value"), [("runbook_health_unused_after_days", 3), ("runbook_health_stale_after_days", 10), ("runbook_health_minimum_rated_investigations", 0), ("runbook_health_wrong_share_percent", 5)])
def test_a_value_outside_its_range_stops_startup(name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{name: value})

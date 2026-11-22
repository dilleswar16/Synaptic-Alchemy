"""Every Ask Keigan setting is documented where an operator looks: ``.env.example`` (one comment line each) and the Helm values.

The defaults written there must equal the defaults in ``keigan/config/settings.py``, so the three cannot drift apart.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from keigan.config.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_EXAMPLE = PROJECT_ROOT / "backend" / ".env.example"
HELM_VALUES = PROJECT_ROOT / "deploy" / "helm" / "keigan" / "values.yaml"

# The Ask Keigan fields, plus the model-capability overrides that belong to it.
DOCUMENTED_FIELDS = sorted(
    [name for name in Settings.model_fields if name.startswith("ask_keigan_")] + ["llm_model_capabilities_json"]
)


def documented_default(field_name: str) -> str:
    default = Settings.model_fields[field_name].default
    return "" if default is None else str(default)


def environment_lines() -> dict[str, tuple[str, str]]:
    """Variable name -> (value, the line above it) for every ``NAME=value`` line of ``.env.example``."""
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    found: dict[str, tuple[str, str]] = {}
    for index, line in enumerate(lines):
        name, separator, value = line.partition("=")
        if separator and name.isupper() and not line.startswith("#"):
            found[name] = (value, lines[index - 1] if index else "")
    return found


@pytest.mark.parametrize("field_name", DOCUMENTED_FIELDS)
def test_env_example_has_the_setting_with_its_default_and_a_comment_line(field_name: str) -> None:
    value, line_above = environment_lines().get(field_name.upper(), (None, ""))
    assert value is not None, f"{field_name.upper()} is missing from .env.example"
    assert value == documented_default(field_name)
    assert line_above.startswith("# ") and len(line_above) > 10, f"{field_name.upper()} needs its own comment line above it"


@pytest.mark.parametrize("field_name", DOCUMENTED_FIELDS)
def test_helm_values_have_the_setting_with_its_default(field_name: str) -> None:
    backend_environment = yaml.safe_load(HELM_VALUES.read_text(encoding="utf-8"))["backendEnvironment"]
    assert field_name.upper() in backend_environment, f"{field_name.upper()} is missing from the Helm backendEnvironment"
    assert str(backend_environment[field_name.upper()]) == documented_default(field_name)


def test_the_documented_fields_are_not_empty() -> None:
    assert len(DOCUMENTED_FIELDS) >= 24

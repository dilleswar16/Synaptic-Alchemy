"""keigan/config/settings.py: the longest operating notes an application may have is a validated setting."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keigan.config.settings import Settings


def build_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, environment="test", **overrides)  # type: ignore[arg-type]


def test_by_default_operating_notes_can_have_four_thousand_characters() -> None:
    assert build_settings().application_operating_notes_maximum_characters == 4000


def test_the_maximum_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPLICATION_OPERATING_NOTES_MAXIMUM_CHARACTERS", "1500")
    assert build_settings().application_operating_notes_maximum_characters == 1500


@pytest.mark.parametrize("value", [0, 99, 20_001, -5])
def test_a_maximum_below_one_hundred_or_above_twenty_thousand_is_refused_at_start_up(value: int) -> None:
    with pytest.raises(ValidationError):
        build_settings(application_operating_notes_maximum_characters=value)


@pytest.mark.parametrize("value", [100, 20_000])
def test_the_bounds_themselves_are_allowed(value: int) -> None:
    assert build_settings(application_operating_notes_maximum_characters=value).application_operating_notes_maximum_characters == value

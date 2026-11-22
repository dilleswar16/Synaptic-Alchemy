"""keigan/config/settings.py: the three settings of the reliability metrics page are validated and default to honest values."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from keigan.config.settings import ModelPrice, Settings


def build_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, environment="test", **overrides)  # type: ignore[arg-type]


def test_by_default_the_minimum_sample_is_five_the_window_is_a_year_and_no_prices_are_configured() -> None:
    settings = build_settings()
    assert settings.metrics_minimum_rating_sample == 5
    assert settings.metrics_maximum_window_days == 365
    assert settings.llm_model_prices == {}


def test_an_empty_price_variable_means_no_prices_not_a_start_up_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_PRICES_JSON", "")
    assert build_settings().llm_model_prices == {}


@pytest.mark.parametrize("name", ["metrics_minimum_rating_sample", "metrics_maximum_window_days"])
@pytest.mark.parametrize("value", [0, -1])
def test_the_sample_and_window_limits_must_be_at_least_one(name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        build_settings(**{name: value})


def test_prices_are_read_from_a_json_mapping_of_model_name_to_prices_per_million_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_PRICES_JSON", '{"gemini-2.5-pro": {"input_per_million": 1.25, "output_per_million": 10}}')
    assert build_settings().llm_model_prices == {"gemini-2.5-pro": ModelPrice(input_per_million=1.25, output_per_million=10)}


@pytest.mark.parametrize(
    "prices",
    [
        {"m": {"input_per_million": -1, "output_per_million": 1}},  # negative price
        {"m": {"input_per_million": 1}},  # output price missing
        {"": {"input_per_million": 1, "output_per_million": 1}},  # empty model name
        {"m": {"input_per_million": 1, "output_per_million": 1, "extra": 1}},  # unknown field
        {"m": {"input_per_million": "cheap", "output_per_million": 1}},  # not a number
        ["not", "a", "mapping"],
    ],
)
def test_an_invalid_price_mapping_is_refused_at_start_up(prices: object) -> None:
    with pytest.raises(ValidationError):
        build_settings(llm_model_prices_json=json.dumps(prices))


def test_text_that_is_not_json_is_refused_at_start_up() -> None:
    with pytest.raises(ValidationError):
        build_settings(llm_model_prices_json="gemini=1.25")

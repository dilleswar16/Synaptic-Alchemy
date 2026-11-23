"""keigan/ai/fix_parameter_kinds.py: which values may enter a command and how they are quoted (spec 33, AC-2, AC-4, AC-5, AC-14)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keigan.ai.fix_parameter_kinds import ValueRefusal, check_value, is_secret_setting_name, kind_catalogue, kind_names, needs_quotes, quote

VECTORS = json.loads((Path(__file__).resolve().parents[2] / "support" / "fix_value_quoting_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("value", VECTORS["bare_safe"])
def test_a_bare_safe_value_is_inserted_without_quotes(value: str) -> None:
    assert not needs_quotes(value) and quote(value) == value


@pytest.mark.parametrize("case", VECTORS["needs_quotes"], ids=lambda case: case["value"])
def test_any_other_value_is_wrapped_in_single_quotes(case: dict[str, str]) -> None:
    assert needs_quotes(case["value"]) and quote(case["value"]) == case["quoted"]


@pytest.mark.parametrize("case", VECTORS["insertable"], ids=lambda case: f"{case['kind']}={case['value']}")
def test_a_well_formed_value_of_its_kind_is_accepted(case: dict[str, str]) -> None:
    assert check_value(case["kind"], case["value"]) is None


@pytest.mark.parametrize("case", VECTORS["never_insertable"], ids=lambda case: f"{case['kind']}={case['value']!r}")
def test_a_hostile_or_masked_value_is_refused_with_its_reason(case: dict[str, str]) -> None:
    assert check_value(case["kind"], case["value"]) == ValueRefusal(case["refusal"])


def test_no_pattern_admits_a_quote_a_shell_special_character_or_a_leading_dash() -> None:
    """The renderer relies on this: single quotes are safe in both shells only because no kind can contain a quote."""
    forbidden = ["'", '"', "`", "‘", "’", "‚", "‛", "“", "”", "„", "‟", "$", ";", "&", "|", "<", ">", "\\", "\n", "\r", "\t", "\x00"]
    for kind in kind_names():
        for character in forbidden:
            for candidate in (f"a{character}", f"a{character}b", f"{character}a"):
                assert check_value(kind, candidate) is not None, f"{kind} admitted {candidate!r}"
        assert check_value(kind, "-a") is not None


def test_the_catalogue_sent_to_the_browser_has_a_pattern_and_a_length_for_every_kind() -> None:
    catalogue = kind_catalogue()
    assert set(catalogue) == set(kind_names()) and all({"pattern", "maximum_length", "label_key"} <= set(entry) for entry in catalogue.values())


@pytest.mark.parametrize(("name", "is_secret"), [("Db__Password", True), ("ConnectionStrings:Main", True), ("Api-Key", True), ("StorageAccountKey", True), ("Database__MaxPoolSize", False), ("Retry.Count", False)])
def test_secret_like_setting_names_are_recognised(name: str, is_secret: bool) -> None:
    assert is_secret_setting_name(name) is is_secret

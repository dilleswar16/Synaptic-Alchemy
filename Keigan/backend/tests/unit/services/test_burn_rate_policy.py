"""keigan/services/burn_rate_policy.py: the burn-rate thresholds and windows an SLO's own policy sets (roadmap C2 gap: the stored policy was ignored)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from keigan.services.burn_rate_policy import DEFAULT_POLICIES, BurnPolicy, parse_iso_duration, policy_for


def test_the_default_page_and_ticket_policies_are_the_multiwindow_pair_the_proposals_store() -> None:
    assert DEFAULT_POLICIES["page"] == BurnPolicy(14.4, timedelta(hours=1), timedelta(minutes=5))
    assert DEFAULT_POLICIES["ticket"] == BurnPolicy(6.0, timedelta(hours=6), timedelta(minutes=30))


@pytest.mark.parametrize("text, expected", [
    ("PT5M", timedelta(minutes=5)), ("PT1H", timedelta(hours=1)), ("PT6H", timedelta(hours=6)), ("PT1H30M", timedelta(hours=1, minutes=30)),
    ("P1D", timedelta(days=1)), ("P1DT12H", timedelta(days=1, hours=12)), ("PT90S", timedelta(seconds=90)),
])
def test_an_iso_duration_is_read(text: str, expected: timedelta) -> None:
    assert parse_iso_duration(text) == expected


@pytest.mark.parametrize("text", ["", "5m", "PT", "P", "PT-5M", "PT1.5H", "P1W", "PT5M junk", "pt5m", None, 5])
def test_anything_else_is_not_a_duration(text: Any) -> None:
    assert parse_iso_duration(text) is None


def test_an_slos_own_policy_replaces_the_default_for_that_severity() -> None:
    stored = {"page": {"burnRate": 10, "longWindow": "PT2H", "shortWindow": "PT10M"}, "ticket": {"burnRate": 3, "longWindow": "P1D", "shortWindow": "PT2H"}}
    assert policy_for(stored, "page") == BurnPolicy(10.0, timedelta(hours=2), timedelta(minutes=10))
    assert policy_for(stored, "ticket") == BurnPolicy(3.0, timedelta(days=1), timedelta(hours=2))


@pytest.mark.parametrize("stored", [None, {}, {"page": None}, {"ticket": {"burnRate": 3, "longWindow": "P1D", "shortWindow": "PT2H"}}])
def test_a_missing_policy_falls_back_to_the_default(stored: Any) -> None:
    assert policy_for(stored, "page") == DEFAULT_POLICIES["page"]


@pytest.mark.parametrize("entry", [
    {"burnRate": 0, "longWindow": "PT1H", "shortWindow": "PT5M"},            # a threshold that never means anything
    {"burnRate": -2, "longWindow": "PT1H", "shortWindow": "PT5M"},
    {"burnRate": "fast", "longWindow": "PT1H", "shortWindow": "PT5M"},
    {"burnRate": True, "longWindow": "PT1H", "shortWindow": "PT5M"},         # a boolean is not a number here
    {"burnRate": 14.4, "longWindow": "PT5M", "shortWindow": "PT1H"},         # the short window must be shorter
    {"burnRate": 14.4, "longWindow": "PT1H", "shortWindow": "PT1H"},
    {"burnRate": 14.4, "longWindow": "PT1H", "shortWindow": "bad"},
    {"burnRate": 14.4, "longWindow": "P90D", "shortWindow": "PT5M"},         # longer than any rolling window
    {"burnRate": 5000, "longWindow": "PT1H", "shortWindow": "PT5M"},
    {"longWindow": "PT1H", "shortWindow": "PT5M"},
    "not a mapping",
])
def test_a_policy_that_cannot_be_used_falls_back_to_the_default_instead_of_silencing_the_alert(entry: Any) -> None:
    assert policy_for({"page": entry}, "page") == DEFAULT_POLICIES["page"]

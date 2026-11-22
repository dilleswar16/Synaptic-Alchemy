"""keigan/ai/alert_ai_schemas.py: the fallback group sentence states no alert count (the count is stored and shown separately, and grows after the sentence is written)."""

from __future__ import annotations

from keigan.ai.alert_ai_schemas import deterministic_group_title


def test_the_fallback_summary_does_not_state_an_alert_count_that_goes_stale_as_alerts_join() -> None:
    title, summary = deterministic_group_title(["claims-sql"], ["Connection pool exhausted"])
    assert title == "claims-sql: Connection pool exhausted"
    assert summary == "Started with an alert on claims-sql."
    assert not any(character.isdigit() for character in summary)


def test_the_fallback_without_a_service_names_the_application() -> None:
    _, summary = deterministic_group_title([], [])
    assert summary == "Started with an alert on Application."

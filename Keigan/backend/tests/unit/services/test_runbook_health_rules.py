"""keigan/services/runbook_health_rules.py: which runbooks need attention and why (spec 32, AC-1 to AC-3)."""

from __future__ import annotations

from datetime import date

from keigan.services.runbook_health_rules import RunbookFacts, RunbookHealthThresholds, findings_for

TODAY = date(2026, 11, 23)
THRESHOLDS = RunbookHealthThresholds(unused_after_days=60, stale_after_days=180, minimum_rated_investigations=3, wrong_share_percent=50.0)


def facts(**overrides: object) -> RunbookFacts:
    values: dict[str, object] = dict(
        has_trigger_symptoms=True, has_steps=True, times_referenced_count=4, created_on=date(2025, 1, 1), updated_on=date(2026, 11, 1), rated_investigation_count=0, incorrect_rated_count=0,
    )
    values.update(overrides)
    return RunbookFacts(**values)  # type: ignore[arg-type]


def kinds(**overrides: object) -> list[str]:
    return [finding.kind for finding in findings_for(facts(**overrides), TODAY, THRESHOLDS)]


def test_a_used_recently_edited_complete_runbook_has_no_findings() -> None:
    assert kinds() == []


def test_a_runbook_without_symptoms_or_steps_is_flagged() -> None:
    assert kinds(has_trigger_symptoms=False, has_steps=False) == ["no_trigger_symptoms", "no_steps"]


def test_never_used_needs_the_runbook_to_be_old_enough() -> None:
    assert kinds(times_referenced_count=0, created_on=date(2026, 9, 1)) == ["never_used"]  # 83 days
    assert kinds(times_referenced_count=0, created_on=date(2026, 10, 1)) == []  # 53 days
    assert kinds(times_referenced_count=1, created_on=date(2025, 1, 1)) == []


def test_not_updated_counts_from_the_last_update() -> None:
    assert kinds(updated_on=date(2026, 5, 1)) == ["not_updated"]  # 206 days
    assert kinds(updated_on=date(2026, 6, 1)) == []  # 175 days


def test_often_wrong_needs_the_minimum_sample_and_the_share() -> None:
    assert kinds(rated_investigation_count=5, incorrect_rated_count=3) == ["often_wrong"]
    assert kinds(rated_investigation_count=5, incorrect_rated_count=2) == []  # 40 %
    assert kinds(rated_investigation_count=2, incorrect_rated_count=2) == []  # below the minimum of 3


def test_the_findings_carry_their_figures() -> None:
    (finding,) = findings_for(facts(times_referenced_count=0, created_on=date(2026, 9, 1)), TODAY, THRESHOLDS)
    assert finding.parameters == {"days": 83}
    (wrong,) = findings_for(facts(rated_investigation_count=4, incorrect_rated_count=3), TODAY, THRESHOLDS)
    assert wrong.parameters == {"incorrect": 3, "rated": 4}

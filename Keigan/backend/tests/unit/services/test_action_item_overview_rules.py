"""keigan/services/action_item_overview_rules.py: completion figures, repeated incidents and the order of the needs-attention list (spec 29, 4.4; AC-18)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from keigan.services.action_item_overview_rules import (
    AttentionEntry, AttentionKind, IncidentFacts, ItemFacts, PreventItemFacts, PreventItemState, RepeatOutcome, attention_order, completion_figures, prevent_item_state_at,
    repeat_groups, repeat_outcome,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


def item(status: str = "open", *, due: date | None = date(2026, 11, 30), original: date | None = None, accepted: float | None = 10, completed: float | None = None, zone: str = "UTC") -> ItemFacts:
    return ItemFacts(status=status, due_on=due, original_due_on=original or due, accepted_at=at(accepted) if accepted is not None else None, completed_at=at(completed) if completed is not None else None, time_zone_name=zone)


# ── Completion figures ───────────────────────────────────────────────────────────────────────────


def test_the_rate_is_done_over_accepted_without_the_dropped_items() -> None:
    accepted = [item("done", accepted=10, completed=5), item("done", accepted=9, completed=3), item("open"), item("wont_do", completed=2)]
    figures = completion_figures(accepted, [item("open")], NOW)
    assert (figures.accepted_count, figures.done_count, figures.wont_do_count) == (4, 2, 1)
    assert figures.completion_rate == pytest.approx(66.7, abs=0.05) and figures.completion_rate_sample_count == 3


def test_a_rate_with_nothing_to_divide_is_unknown_not_zero() -> None:
    figures = completion_figures([item("wont_do", completed=2)], [], NOW)
    assert figures.completion_rate is None and figures.completion_rate_sample_count == 0


def test_the_median_days_to_complete_counts_only_finished_items_and_says_how_many() -> None:
    figures = completion_figures([item("done", accepted=10, completed=6), item("done", accepted=10, completed=2), item("done", accepted=10, completed=4), item("open")], [], NOW)
    assert figures.median_days_to_complete == 6.0 and figures.median_sample_count == 3


def test_an_item_that_finished_before_it_was_accepted_is_left_out_of_the_median() -> None:
    figures = completion_figures([item("done", accepted=2, completed=5)], [], NOW)
    assert figures.median_days_to_complete is None and figures.median_sample_count == 0


def test_on_time_is_judged_against_the_first_due_date_in_the_applications_own_zone() -> None:
    late_in_utc_but_on_time_in_tokyo = ItemFacts("done", date(2026, 11, 20), date(2026, 11, 20), at(10), datetime(2026, 11, 20, 14, 0, tzinfo=UTC), "Asia/Tokyo")  # 23:00 on the 20th in Tokyo
    moved_but_first_date_missed = ItemFacts("done", date(2026, 12, 1), date(2026, 11, 10), at(15), at(1), "UTC")
    figures = completion_figures([late_in_utc_but_on_time_in_tokyo, moved_but_first_date_missed], [], NOW)
    assert figures.on_time_share == 50.0 and figures.on_time_sample_count == 2


def test_open_and_overdue_are_counted_over_every_unfinished_item_not_only_those_accepted_in_the_period() -> None:
    old_overdue = item("in_progress", due=date(2026, 9, 1), accepted=80)
    due_later = item("open", due=date(2026, 12, 1))
    done_item = item("done", completed=3)
    figures = completion_figures([], [old_overdue, due_later, done_item], NOW)
    assert (figures.open_count, figures.overdue_count) == (2, 1)


def test_an_item_due_today_is_not_overdue_until_the_day_has_passed_in_its_own_zone() -> None:
    due_today_in_tokyo = item("open", due=date(2026, 11, 20), zone="Asia/Tokyo")
    figures = completion_figures([], [due_today_in_tokyo], datetime(2026, 11, 20, 20, 0, tzinfo=UTC))  # already the 21st in Tokyo
    assert figures.overdue_count == 1


# ── Repeated incidents ───────────────────────────────────────────────────────────────────────────


def prevent(identifier: str, status: str = "open", *, accepted: float | None = 50, completed: float | None = None) -> PreventItemFacts:
    return PreventItemFacts(identifier, f"Fix {identifier}", status, at(accepted) if accepted is not None else None, at(completed) if completed is not None else None)


def test_the_state_of_a_follow_up_is_the_state_at_the_moment_of_the_repeat() -> None:
    finished_later = prevent("a", "done", accepted=50, completed=3)
    assert prevent_item_state_at(finished_later, at(10)) is PreventItemState.NOT_DONE  # done after the repeat
    assert prevent_item_state_at(finished_later, at(2)) is PreventItemState.DONE
    assert prevent_item_state_at(prevent("b", "wont_do", completed=20), at(10)) is PreventItemState.WONT_DO
    assert prevent_item_state_at(prevent("c", accepted=5), at(10)) is None  # accepted after the repeat: it was not tracked then
    assert prevent_item_state_at(prevent("d", accepted=None), at(10)) is None  # never accepted


def test_a_repeat_with_no_final_postmortem_before_it_is_a_missing_postmortem() -> None:
    assert repeat_outcome(False, [prevent("a")], at(1)) is RepeatOutcome.NO_POSTMORTEM


def test_a_repeat_whose_earlier_postmortem_tracked_nothing_to_prevent_it() -> None:
    assert repeat_outcome(True, [], at(1)) is RepeatOutcome.NO_PREVENT_ITEM
    assert repeat_outcome(True, [prevent("a", accepted=None)], at(1)) is RepeatOutcome.NO_PREVENT_ITEM


def test_a_repeat_while_a_follow_up_was_still_open() -> None:
    assert repeat_outcome(True, [prevent("a", "done", completed=30), prevent("b", "in_progress")], at(1)) is RepeatOutcome.REPEATED_WHILE_OPEN


def test_a_follow_up_dropped_as_wont_do_counts_as_not_done() -> None:
    assert repeat_outcome(True, [prevent("a", "wont_do", completed=30)], at(1)) is RepeatOutcome.REPEATED_WHILE_OPEN


def test_a_repeat_after_every_follow_up_was_done_says_the_fix_may_not_have_worked() -> None:
    assert repeat_outcome(True, [prevent("a", "done", completed=30), prevent("b", "done", completed=20)], at(1)) is RepeatOutcome.REPEATED_AFTER_DONE


def incident(identifier: str, category: str, service: str, days_ago: float) -> IncidentFacts:
    return IncidentFacts(identifier, (category, service), at(days_ago))


def test_groups_need_two_incidents_of_the_same_category_and_service_and_a_named_service() -> None:
    groups = repeat_groups([
        incident("i1", "capacity", "svc-a", 30), incident("i2", "capacity", "svc-a", 10), incident("i3", "capacity", "svc-b", 5),
        incident("i4", "deployment", "", 9), incident("i5", "deployment", "", 3),
    ])
    assert [[member.incident_id for member in group] for group in groups] == [["i1", "i2"]]


def test_a_group_lists_its_incidents_in_time_order_and_the_most_recent_group_comes_first() -> None:
    groups = repeat_groups([
        incident("late", "capacity", "svc-a", 2), incident("early", "capacity", "svc-a", 40), incident("x1", "network", "svc-c", 20), incident("x2", "network", "svc-c", 9),
    ])
    assert [[member.incident_id for member in group] for group in groups] == [["early", "late"], ["x1", "x2"]]


# ── Needs attention ──────────────────────────────────────────────────────────────────────────────


def entry(kind: AttentionKind, record_id: str, **parameters: object) -> AttentionEntry:
    return AttentionEntry(kind, "app-1", "action_item", record_id, f"Title {record_id}", dict(parameters))


def test_overdue_top_priority_items_come_first_then_by_days_overdue() -> None:
    ordered = attention_order([
        entry(AttentionKind.PROPOSED_WAITING, "w1", daysWaiting=9),
        entry(AttentionKind.OVERDUE_ITEM, "n5", priority="normal", daysOverdue=5),
        entry(AttentionKind.TOP_PRIORITY_UNOWNED, "u1"),
        entry(AttentionKind.OVERDUE_ITEM, "t2", priority="top", daysOverdue=2),
        entry(AttentionKind.OVERDUE_ITEM, "n9", priority="normal", daysOverdue=9),
        entry(AttentionKind.OVERDUE_ITEM, "t8", priority="top", daysOverdue=8),
        entry(AttentionKind.POLICY_BREACH_OPEN, "b1"),
        entry(AttentionKind.POSTMORTEM_MISSING, "m1"),
    ])
    assert [each.record_id for each in ordered] == ["t8", "t2", "n9", "n5", "u1", "b1", "m1", "w1"]

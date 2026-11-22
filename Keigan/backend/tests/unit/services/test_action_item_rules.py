"""keigan/services/action_item_rules.py: who may move an action item where, and what counts as overdue (spec 29, 4.3; AC-5 to AC-7, AC-13)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from keigan.entities.status_values import ActionItemStatus as Status
from keigan.services.action_item_rules import (
    ActionItemRuleError, Actor, can_transition, days_overdue, is_overdue, local_today, proposed_due_on, validate_due_date, validate_reason,
)

ADMIN, OWNER, READER = Actor.ADMIN, Actor.OWNER, Actor.READER


# ── Transitions (AC-6) ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("actor", "from_status", "to_status", "allowed"), [
    (ADMIN, Status.PROPOSED, Status.OPEN, True), (OWNER, Status.PROPOSED, Status.OPEN, False),
    (ADMIN, Status.OPEN, Status.IN_PROGRESS, True), (OWNER, Status.OPEN, Status.IN_PROGRESS, True),
    (OWNER, Status.IN_PROGRESS, Status.BLOCKED, True), (OWNER, Status.BLOCKED, Status.OPEN, True), (OWNER, Status.BLOCKED, Status.IN_PROGRESS, True),
    (OWNER, Status.OPEN, Status.DONE, True), (OWNER, Status.IN_PROGRESS, Status.DONE, True), (OWNER, Status.BLOCKED, Status.DONE, True),
    (ADMIN, Status.OPEN, Status.WONT_DO, True), (OWNER, Status.OPEN, Status.WONT_DO, False),
    (ADMIN, Status.DONE, Status.OPEN, True), (OWNER, Status.DONE, Status.OPEN, False), (ADMIN, Status.WONT_DO, Status.OPEN, True), (OWNER, Status.WONT_DO, Status.OPEN, False),
    (ADMIN, Status.DONE, Status.IN_PROGRESS, False), (ADMIN, Status.OPEN, Status.PROPOSED, False), (ADMIN, Status.DONE, Status.WONT_DO, False),
    (ADMIN, Status.OPEN, Status.OPEN, False), (READER, Status.OPEN, Status.IN_PROGRESS, False), (READER, Status.OPEN, Status.DONE, False),
])
def test_each_transition_is_allowed_or_refused_for_each_role(actor: Actor, from_status: Status, to_status: Status, allowed: bool) -> None:
    assert can_transition(actor, from_status, to_status) is allowed


# ── Reasons (AC-7) ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [Status.BLOCKED, Status.WONT_DO])
def test_blocked_and_wont_do_need_a_reason_of_the_minimum_length(status: Status) -> None:
    with pytest.raises(ActionItemRuleError, match="reason"):
        validate_reason(status, None, minimum_characters=10)
    with pytest.raises(ActionItemRuleError, match="reason"):
        validate_reason(status, "too short", minimum_characters=10)
    assert validate_reason(status, "  waiting on the vendor  ", minimum_characters=10) == "waiting on the vendor"


@pytest.mark.parametrize("status", [Status.OPEN, Status.IN_PROGRESS, Status.DONE])
def test_other_statuses_need_no_reason(status: Status) -> None:
    assert validate_reason(status, None, minimum_characters=10) is None


# ── Dates (AC-5, AC-13) ──────────────────────────────────────────────────────────────────────────


def test_today_is_the_date_in_the_applications_time_zone() -> None:
    moment = datetime(2026, 11, 30, 15, 1, tzinfo=UTC)  # 00:01 on 1 December in Tokyo
    assert local_today("Asia/Tokyo", moment) == date(2026, 12, 1)
    assert local_today("UTC", moment) == date(2026, 11, 30)
    assert local_today("Not/AZone", moment) == date(2026, 11, 30)  # an unknown zone falls back to UTC


def test_an_item_due_today_in_tokyo_is_not_overdue_at_23_00_and_is_at_00_01() -> None:
    due = date(2026, 12, 1)
    at_23_00 = datetime(2026, 12, 1, 14, 0, tzinfo=UTC)  # 23:00 on 1 December in Tokyo
    at_00_01 = datetime(2026, 12, 1, 15, 1, tzinfo=UTC)  # 00:01 on 2 December in Tokyo
    assert is_overdue(Status.OPEN, due, local_today("Asia/Tokyo", at_23_00)) is False
    assert is_overdue(Status.OPEN, due, local_today("Asia/Tokyo", at_00_01)) is True
    assert days_overdue(Status.OPEN, due, local_today("Asia/Tokyo", at_00_01)) == 1


@pytest.mark.parametrize("status", [Status.DONE, Status.WONT_DO, Status.PROPOSED])
def test_only_tracked_unfinished_items_can_be_overdue(status: Status) -> None:
    assert is_overdue(status, date(2020, 1, 1), date(2026, 1, 1)) is False and days_overdue(status, date(2020, 1, 1), date(2026, 1, 1)) == 0


def test_an_item_with_no_due_date_is_never_overdue() -> None:
    assert is_overdue(Status.OPEN, None, date(2026, 1, 1)) is False


def test_a_due_date_must_not_be_in_the_past_or_beyond_the_maximum() -> None:
    today = date(2026, 11, 23)
    assert validate_due_date(date(2026, 11, 23), today, maximum_days=180) == date(2026, 11, 23)
    with pytest.raises(ActionItemRuleError, match="new date"):
        validate_due_date(date(2026, 11, 22), today, maximum_days=180)
    with pytest.raises(ActionItemRuleError, match="180"):
        validate_due_date(date(2027, 6, 1), today, maximum_days=180)


def test_the_ai_suggested_days_become_a_local_date_clamped_to_the_range() -> None:
    resolved = datetime(2026, 11, 30, 20, 0, tzinfo=UTC)  # 05:00 on 1 December in Tokyo
    assert proposed_due_on(resolved, 14, "Asia/Tokyo", maximum_days=180) == date(2026, 12, 15)
    assert proposed_due_on(resolved, 0, "UTC", maximum_days=180) == date(2026, 12, 1)  # at least one day
    assert proposed_due_on(resolved, 9999, "UTC", maximum_days=180) == date(2027, 5, 29)


# ── Reminders (AC-14, AC-15) ─────────────────────────────────────────────────────────────────────

from keigan.entities.status_values import ActionItemPriority as Priority
from keigan.services.action_item_rules import ReminderKind, reminder_kind

TODAY = date(2026, 12, 10)
LIMITS = dict(days_before_due=2, overdue_interval_days=7, escalate_after_days=14)


def kind_of(due_on: date | None, *, status: Status = Status.OPEN, priority: Priority = Priority.NORMAL, last_reminded_on: date | None = None, today: date = TODAY, **limits: int) -> ReminderKind | None:
    return reminder_kind(status, priority, due_on, today, last_reminded_on, **{**LIMITS, **limits})


def test_an_item_due_in_the_configured_number_of_days_gets_a_due_soon_reminder_once() -> None:
    assert kind_of(date(2026, 12, 12)) is ReminderKind.DUE_SOON
    assert kind_of(date(2026, 12, 12), last_reminded_on=TODAY) is None
    assert kind_of(date(2026, 12, 13)) is None and kind_of(date(2026, 12, 11)) is None
    assert kind_of(date(2026, 12, 12), days_before_due=0) is None


def test_the_first_overdue_day_reminds_and_then_only_every_interval() -> None:
    assert kind_of(date(2026, 12, 9)) is ReminderKind.OVERDUE
    assert kind_of(date(2026, 12, 9), last_reminded_on=date(2026, 12, 7)) is ReminderKind.OVERDUE  # the earlier reminder was the due-soon one
    assert kind_of(date(2026, 12, 3), last_reminded_on=date(2026, 12, 4)) is None
    assert kind_of(date(2026, 12, 1), last_reminded_on=date(2026, 12, 3)) is ReminderKind.OVERDUE  # seven days since the last
    assert kind_of(date(2026, 12, 1), last_reminded_on=date(2026, 12, 4)) is None


def test_a_long_overdue_top_or_high_item_escalates_instead() -> None:
    long_ago = date(2026, 11, 20)
    assert kind_of(long_ago, priority=Priority.TOP) is ReminderKind.ESCALATE and kind_of(long_ago, priority=Priority.HIGH) is ReminderKind.ESCALATE
    assert kind_of(long_ago, priority=Priority.NORMAL) is ReminderKind.OVERDUE and kind_of(long_ago, priority=Priority.LOW) is ReminderKind.OVERDUE
    assert kind_of(date(2026, 12, 1), priority=Priority.TOP) is ReminderKind.OVERDUE  # nine days: not yet
    assert kind_of(long_ago, priority=Priority.TOP, last_reminded_on=date(2026, 12, 8)) is None


@pytest.mark.parametrize("status", [Status.PROPOSED, Status.DONE, Status.WONT_DO])
def test_only_tracked_items_are_reminded(status: Status) -> None:
    assert kind_of(date(2026, 12, 1), status=status) is None and kind_of(date(2026, 12, 12), status=status) is None


def test_an_item_with_no_due_date_is_never_reminded() -> None:
    assert kind_of(None) is None

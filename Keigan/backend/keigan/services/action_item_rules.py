"""The rules of action items (spec 29, 4.3): who may move an item to which status, what a reason must be, and what overdue means. Pure functions, no database.

A due date is a calendar date in the application's own time zone: a Tokyo team's "due 1 December" ends at midnight Tokyo time, not at midnight UTC.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from keigan.entities.status_values import ActionItemStatus as Status

logger = logging.getLogger(__name__)
_UNKNOWN_ZONES_LOGGED: set[str] = set()
TRACKED_STATUSES = frozenset({Status.OPEN, Status.IN_PROGRESS, Status.BLOCKED})  # the unfinished items a team is accountable for (not proposed, not closed)
CLOSED_STATUSES = frozenset({Status.DONE, Status.WONT_DO})
STATUSES_NEEDING_A_REASON = frozenset({Status.BLOCKED, Status.WONT_DO})


class ActionItemRuleError(ValueError):
    """A rule was broken; the message is written for the person who asked and is returned as is."""


class Actor(StrEnum):
    ADMIN = "admin"  # an application admin (or a Keigan admin)
    OWNER = "owner"  # the team member the item is assigned to, who may only read the application
    READER = "reader"


_WORK_STATUSES = {Status.OPEN, Status.IN_PROGRESS, Status.BLOCKED}
_ANYONE_WITH_THE_WORK = {Actor.ADMIN, Actor.OWNER}
_ADMIN_ONLY = {Actor.ADMIN}


def _transitions() -> dict[tuple[Status, Status], set[Actor]]:
    allowed: dict[tuple[Status, Status], set[Actor]] = {(Status.PROPOSED, Status.OPEN): _ADMIN_ONLY}  # accepting a suggestion is a team decision
    for from_status in _WORK_STATUSES:
        for to_status in _WORK_STATUSES - {from_status}:
            allowed[(from_status, to_status)] = _ANYONE_WITH_THE_WORK
        allowed[(from_status, Status.DONE)] = _ANYONE_WITH_THE_WORK  # whoever does the work may close it
        allowed[(from_status, Status.WONT_DO)] = _ADMIN_ONLY  # dropping work is a team decision
    for closed_status in CLOSED_STATUSES:
        allowed[(closed_status, Status.OPEN)] = _ADMIN_ONLY  # reopening
    return allowed


ALLOWED_TRANSITIONS = _transitions()


def can_transition(actor: Actor, from_status: Status, to_status: Status) -> bool:
    return actor in ALLOWED_TRANSITIONS.get((from_status, to_status), set())


def validate_reason(status: Status, reason_text: str | None, *, minimum_characters: int) -> str | None:
    """``blocked`` and ``won't do`` say why; every other status needs none. Returns the text trimmed."""
    cleaned = (reason_text or "").strip()
    if status in STATUSES_NEEDING_A_REASON and len(cleaned) < minimum_characters:
        raise ActionItemRuleError(f"Say why in a reason of at least {minimum_characters} characters.")
    return cleaned or None


def local_today(time_zone_name: str | None, moment: datetime) -> date:
    """Today's date in the application's time zone (an unknown zone name falls back to UTC, and is logged once)."""
    try:
        zone = ZoneInfo(time_zone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        if time_zone_name not in _UNKNOWN_ZONES_LOGGED:
            _UNKNOWN_ZONES_LOGGED.add(time_zone_name or "")
            logger.warning("Unknown time zone %r on an application: action item dates use UTC for it.", time_zone_name)
        zone = ZoneInfo("UTC")
    return moment.astimezone(zone).date()


def is_overdue(status: Status | str, due_on: date | None, today: date) -> bool:
    return Status(status) in TRACKED_STATUSES and due_on is not None and due_on < today


def days_overdue(status: Status | str, due_on: date | None, today: date) -> int:
    return (today - due_on).days if is_overdue(status, due_on, today) and due_on is not None else 0


def validate_due_date(due_on: date, today: date, *, maximum_days: int) -> date:
    if due_on < today:
        raise ActionItemRuleError("That due date has already passed. Choose a new date.")
    if due_on > today + timedelta(days=maximum_days):
        raise ActionItemRuleError(f"The due date can be at most {maximum_days} days from today.")
    return due_on


def proposed_due_on(base_moment: datetime, due_in_days: int, time_zone_name: str | None, *, maximum_days: int) -> date:
    """The AI's suggested number of days as a local date, kept between one day and the maximum."""
    days = max(1, min(due_in_days, maximum_days))
    return local_today(time_zone_name, base_moment) + timedelta(days=days)

"""The rules behind the action items overview (spec 29, 4.4): completion figures, which incidents repeated and what happened to their follow-ups, and the order of the needs-attention list.

Pure functions, no database. Every figure carries its sample size, as on the metrics page, so a screen can say "n = 24" and never shows a percentage from one item.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from keigan.entities.status_values import ActionItemPriority, ActionItemStatus as Status
from keigan.services.action_item_rules import CLOSED_STATUSES, TRACKED_STATUSES, is_overdue, local_today
from keigan.services.reliability_metrics import summarize

SECONDS_PER_DAY = 86_400
PERCENT = 100


@dataclass(frozen=True)
class ItemFacts:
    """What the figures need to know about one item."""

    status: str
    due_on: date | None
    original_due_on: date | None
    accepted_at: datetime | None
    completed_at: datetime | None
    time_zone_name: str | None


@dataclass(frozen=True)
class CompletionFigures:
    accepted_count: int
    done_count: int
    wont_do_count: int
    open_count: int  # every unfinished tracked item now, not only those accepted in the period: an old overdue item must not drop out of the count
    overdue_count: int
    completion_rate: float | None  # percent; done / (accepted - wont do) among the items accepted in the period
    completion_rate_sample_count: int
    median_days_to_complete: float | None
    median_sample_count: int
    on_time_share: float | None  # percent of done items finished on or before their first due date
    on_time_sample_count: int


def _percent(part: int, whole: int) -> float | None:
    return round(PERCENT * part / whole, 1) if whole > 0 else None


def completion_figures(accepted_in_period: Iterable[ItemFacts], tracked_now: Iterable[ItemFacts], now: datetime) -> CompletionFigures:
    """``accepted_in_period``: items accepted in the chosen period (any status since). ``tracked_now``: every unfinished tracked item at ``now``, whenever it was accepted."""
    accepted = list(accepted_in_period)
    done = [item for item in accepted if item.status == Status.DONE]
    wont_do_count = sum(1 for item in accepted if item.status == Status.WONT_DO)
    tracked = [item for item in tracked_now if item.status in TRACKED_STATUSES]
    overdue_count = sum(1 for item in tracked if is_overdue(item.status, item.due_on, local_today(item.time_zone_name, now)))
    rate_denominator = len(accepted) - wont_do_count
    days_to_complete = [(item.completed_at - item.accepted_at).total_seconds() / SECONDS_PER_DAY for item in done if item.accepted_at and item.completed_at and item.completed_at >= item.accepted_at]
    median = summarize(days_to_complete, digits=1).median
    judged_on_time = [item for item in done if item.completed_at and item.original_due_on]
    on_time = sum(1 for item in judged_on_time if local_today(item.time_zone_name, item.completed_at) <= item.original_due_on)  # type: ignore[arg-type]
    return CompletionFigures(
        accepted_count=len(accepted), done_count=len(done), wont_do_count=wont_do_count, open_count=len(tracked), overdue_count=overdue_count,
        completion_rate=_percent(len(done), rate_denominator), completion_rate_sample_count=max(rate_denominator, 0),
        median_days_to_complete=median, median_sample_count=len(days_to_complete),
        on_time_share=_percent(on_time, len(judged_on_time)), on_time_sample_count=len(judged_on_time),
    )


# ── Repeated incidents ───────────────────────────────────────────────────────────────────────────


class RepeatOutcome(StrEnum):
    NO_POSTMORTEM = "no_postmortem"  # none of the earlier incidents has a final postmortem
    NO_PREVENT_ITEM = "no_prevent_item"  # earlier postmortems exist, but nothing was tracked to prevent a repeat
    REPEATED_WHILE_OPEN = "repeated_while_open"  # a follow-up to prevent it was still not done when it came back
    REPEATED_AFTER_DONE = "repeated_after_done"  # every follow-up was done and it came back anyway: the fix may not have worked


class PreventItemState(StrEnum):
    DONE = "done"
    NOT_DONE = "not_done"  # still open, in progress or blocked at that moment
    WONT_DO = "wont_do"


@dataclass(frozen=True)
class PreventItemFacts:
    action_item_id: str
    title: str
    status: str
    accepted_at: datetime | None
    completed_at: datetime | None


def prevent_item_state_at(item: PreventItemFacts, moment: datetime) -> PreventItemState | None:
    """The item as it stood at ``moment``. None when it was not accepted yet: a follow-up nobody had accepted was not tracked, so it is not part of the story."""
    if item.accepted_at is None or item.accepted_at > moment:
        return None
    if item.status in CLOSED_STATUSES and item.completed_at is not None and item.completed_at <= moment:
        return PreventItemState.DONE if item.status == Status.DONE else PreventItemState.WONT_DO
    return PreventItemState.NOT_DONE


def repeat_outcome(has_final_postmortem: bool, prevent_items: Sequence[PreventItemFacts], repeat_opened_at: datetime) -> RepeatOutcome:
    """What happened to the follow-ups of the earlier incidents of the same kind when it came back. A follow-up closed as won't do counts as not done."""
    if not has_final_postmortem:
        return RepeatOutcome.NO_POSTMORTEM
    states = [state for state in (prevent_item_state_at(item, repeat_opened_at) for item in prevent_items) if state is not None]
    if not states:
        return RepeatOutcome.NO_PREVENT_ITEM
    return RepeatOutcome.REPEATED_AFTER_DONE if all(state == PreventItemState.DONE for state in states) else RepeatOutcome.REPEATED_WHILE_OPEN


@dataclass(frozen=True)
class IncidentFacts:
    incident_id: str
    recurrence_key: tuple[str, str]  # (category, first affected service id)
    opened_at: datetime


def repeat_groups(incidents: Iterable[IncidentFacts]) -> list[list[IncidentFacts]]:
    """Groups of two or more incidents of the same kind (same category on the same primary service), each in time order. An incident naming no service is never grouped."""
    grouped: dict[tuple[str, str], list[IncidentFacts]] = defaultdict(list)
    for incident in incidents:
        if incident.recurrence_key[1]:
            grouped[incident.recurrence_key].append(incident)
    return sorted(
        ([sorted(members, key=lambda member: member.opened_at) for members in grouped.values() if len(members) >= 2]),
        key=lambda members: members[-1].opened_at, reverse=True,
    )


# ── Needs attention ──────────────────────────────────────────────────────────────────────────────


class AttentionKind(StrEnum):
    OVERDUE_ITEM = "overdue_item"
    TOP_PRIORITY_UNOWNED = "top_priority_unowned"
    POLICY_BREACH_OPEN = "policy_breach_open"
    POSTMORTEM_MISSING = "postmortem_missing"
    PROPOSED_WAITING = "proposed_waiting"


_KIND_ORDER = {kind: position for position, kind in enumerate(AttentionKind)}


@dataclass(frozen=True)
class AttentionEntry:
    kind: AttentionKind
    application_id: str
    record_kind: str  # action_item, incident, postmortem or error_budget_policy_breach
    record_id: str
    title: str
    parameters: dict[str, Any] = field(default_factory=dict)


def attention_order(entries: Iterable[AttentionEntry]) -> list[AttentionEntry]:
    """Overdue top-priority items first, then the other overdue items by days overdue, then the other kinds in a fixed order, oldest first within a kind."""
    def sort_key(entry: AttentionEntry) -> tuple[int, int, int, str]:
        is_top = entry.parameters.get("priority") == ActionItemPriority.TOP
        days = int(entry.parameters.get("daysOverdue", entry.parameters.get("daysWaiting", 0)))
        return (0 if entry.kind == AttentionKind.OVERDUE_ITEM and is_top else 1, _KIND_ORDER[entry.kind], -days, entry.record_id)

    return sorted(entries, key=sort_key)

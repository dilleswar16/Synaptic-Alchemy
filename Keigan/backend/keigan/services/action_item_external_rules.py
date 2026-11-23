"""How an action item and the ServiceNow task that tracks it fit together (spec 29, 4.7). Pure: no database, no network.

Once an item is linked to a task, ServiceNow owns its status: a sync reads the task's state and moves the item to match. Keigan never closes a ServiceNow task. A suggestion is never linked
and never changed here. An open task does not undo the team's own "in progress" or "blocked" (those say more than "open" does), but a task that was reopened reopens a finished item.
"""

from __future__ import annotations

from enum import StrEnum

from keigan.entities.status_values import ActionItemStatus

# ServiceNow task states by their numeric value and by the display text that ``sysparm_display_value=all`` returns (the values of the ``task`` table).
_COMPLETE_STATES = frozenset({"3", "closed complete"})
_INCOMPLETE_STATES = frozenset({"4", "7", "closed incomplete", "closed skipped", "cancelled"})
_FINISHED = frozenset({ActionItemStatus.DONE, ActionItemStatus.WONT_DO})


class ExternalTaskOutcome(StrEnum):
    OPEN = "open"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"  # closed without being done: skipped, cancelled


def outcome_of_state(state_text: str | None) -> ExternalTaskOutcome:
    state = (state_text or "").strip().lower()
    if state in _COMPLETE_STATES:
        return ExternalTaskOutcome.COMPLETE
    if state in _INCOMPLETE_STATES:
        return ExternalTaskOutcome.INCOMPLETE
    return ExternalTaskOutcome.OPEN


def status_after_sync(current: ActionItemStatus | str, outcome: ExternalTaskOutcome) -> ActionItemStatus | None:
    """The status the item moves to when its task is in this state, or None when it stays as it is."""
    status = ActionItemStatus(current)
    if status == ActionItemStatus.PROPOSED:
        return None
    if outcome == ExternalTaskOutcome.COMPLETE:
        return None if status == ActionItemStatus.DONE else ActionItemStatus.DONE
    if outcome == ExternalTaskOutcome.INCOMPLETE:
        return None if status == ActionItemStatus.WONT_DO else ActionItemStatus.WONT_DO
    return ActionItemStatus.OPEN if status in _FINISHED else None

"""keigan/services/action_item_external_rules.py: how a ServiceNow task's state and an action item's status fit together once the item is tracked there (spec 29, 4.7)."""

from __future__ import annotations

import pytest

from keigan.entities.status_values import ActionItemPriority, ActionItemStatus
from keigan.services.action_item_external_rules import ExternalTaskOutcome, outcome_of_state, status_after_sync
from keigan.utils.action_item_priority_map import parse_priority_map


@pytest.mark.parametrize("text, outcome", [
    ("Closed Complete", ExternalTaskOutcome.COMPLETE), ("closed complete", ExternalTaskOutcome.COMPLETE), ("3", ExternalTaskOutcome.COMPLETE),
    ("Closed Incomplete", ExternalTaskOutcome.INCOMPLETE), ("Closed Skipped", ExternalTaskOutcome.INCOMPLETE), ("Cancelled", ExternalTaskOutcome.INCOMPLETE), ("4", ExternalTaskOutcome.INCOMPLETE), ("7", ExternalTaskOutcome.INCOMPLETE),
    ("Open", ExternalTaskOutcome.OPEN), ("Work in Progress", ExternalTaskOutcome.OPEN), ("Pending", ExternalTaskOutcome.OPEN), ("1", ExternalTaskOutcome.OPEN), ("", ExternalTaskOutcome.OPEN), (None, ExternalTaskOutcome.OPEN),
])
def test_a_task_state_is_complete_incomplete_or_still_open(text: str | None, outcome: ExternalTaskOutcome) -> None:
    assert outcome_of_state(text) == outcome


def test_the_priority_map_covers_every_priority() -> None:
    assert parse_priority_map("top:1,high:2,normal:3,low:4") == {ActionItemPriority.TOP: "1", ActionItemPriority.HIGH: "2", ActionItemPriority.NORMAL: "3", ActionItemPriority.LOW: "4"}
    assert parse_priority_map(" top : 1 , high:2,normal:3 ,low:4 ")[ActionItemPriority.TOP] == "1"


@pytest.mark.parametrize("text", ["", "top:1,high:2,normal:3", "top:1,high:2,normal:3,low:4,extra:5", "top:1,high:2,normal:3,low", "top:1,high:2,normal:3,low:", "top:1,top:2,normal:3,low:4", "top:one,high:2,normal:3,low:4", "urgent:1,high:2,normal:3,low:4"])
def test_a_priority_map_that_misses_one_or_names_another_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_priority_map(text)


@pytest.mark.parametrize("current, outcome, expected", [
    (ActionItemStatus.OPEN, ExternalTaskOutcome.COMPLETE, ActionItemStatus.DONE),
    (ActionItemStatus.IN_PROGRESS, ExternalTaskOutcome.COMPLETE, ActionItemStatus.DONE),
    (ActionItemStatus.BLOCKED, ExternalTaskOutcome.COMPLETE, ActionItemStatus.DONE),
    (ActionItemStatus.WONT_DO, ExternalTaskOutcome.COMPLETE, ActionItemStatus.DONE),
    (ActionItemStatus.DONE, ExternalTaskOutcome.COMPLETE, None),
    (ActionItemStatus.OPEN, ExternalTaskOutcome.INCOMPLETE, ActionItemStatus.WONT_DO),
    (ActionItemStatus.DONE, ExternalTaskOutcome.INCOMPLETE, ActionItemStatus.WONT_DO),
    (ActionItemStatus.WONT_DO, ExternalTaskOutcome.INCOMPLETE, None),
    (ActionItemStatus.DONE, ExternalTaskOutcome.OPEN, ActionItemStatus.OPEN),   # ServiceNow reopened it
    (ActionItemStatus.WONT_DO, ExternalTaskOutcome.OPEN, ActionItemStatus.OPEN),
    (ActionItemStatus.OPEN, ExternalTaskOutcome.OPEN, None),
    (ActionItemStatus.IN_PROGRESS, ExternalTaskOutcome.OPEN, None),            # an open task does not undo the team's own "in progress" or "blocked"
    (ActionItemStatus.BLOCKED, ExternalTaskOutcome.OPEN, None),
])
def test_what_a_sync_changes_in_the_items_status(current: ActionItemStatus, outcome: ExternalTaskOutcome, expected: ActionItemStatus | None) -> None:
    assert status_after_sync(current, outcome) == expected


def test_a_suggestion_is_never_changed_by_a_sync() -> None:
    for outcome in ExternalTaskOutcome:
        assert status_after_sync(ActionItemStatus.PROPOSED, outcome) is None

"""The seam between action items and the system that tracks them as tasks (spec 29, 4.7).

Keigan sends a task only what the task needs: the item's title, its details, its type, its priority, its due date and the incident number. Never the postmortem text. The other system
owns the task once it exists; Keigan reads its state and never closes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from keigan.services.action_item_external_rules import ExternalTaskOutcome


@dataclass(frozen=True)
class ActionItemSnapshot:
    title: str
    details: str | None
    action_type: str
    priority: str  # an ActionItemPriority value
    due_on: date | None
    incident_reference: str | None


@dataclass(frozen=True)
class ExternalTaskReference:
    number: str  # what people call the task (TASK0012345)
    record_identifier: str  # the system's own id of it
    url: str | None


@dataclass(frozen=True)
class ExternalTaskState:
    status_text: str  # the state as the system says it
    outcome: ExternalTaskOutcome


@runtime_checkable
class ExternalTaskTracker(Protocol):
    system_name: str

    async def create_task(self, item: ActionItemSnapshot) -> ExternalTaskReference: ...

    async def read_task_states(self, record_identifiers: list[str]) -> dict[str, ExternalTaskState]:
        """The state of each task that still exists; a task that was deleted is absent."""
        ...

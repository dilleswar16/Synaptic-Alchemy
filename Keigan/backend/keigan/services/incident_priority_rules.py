"""Deterministic priority rules shared by the ServiceNow poller and the investigation triage (doc 01 section 7.2)."""

from __future__ import annotations

PRIORITY_NAMES = ("P1", "P2", "P3", "P4")
PRIORITY_RANK = {name: index for index, name in enumerate(PRIORITY_NAMES)}  # lower index = more severe
# ServiceNow impact x urgency matrix (1 = high, 2 = medium, 3 = low) -> ServiceNow priority 1..5
_IMPACT_URGENCY_MATRIX = {(1, 1): 1, (1, 2): 2, (2, 1): 2, (2, 2): 3, (1, 3): 3, (3, 1): 3, (2, 3): 4, (3, 2): 4, (3, 3): 5}


def _to_number(value: str | None) -> int | None:
    digits = "".join(character for character in (value or "") if character.isdigit())[:1]
    return int(digits) if digits else None


def map_servicenow_priority(impact: str | None, urgency: str | None, priority: str | None) -> str:
    """Keigan priority (P1..P4) from ServiceNow impact x urgency, falling back to the ServiceNow priority field."""
    impact_number, urgency_number = _to_number(impact), _to_number(urgency)
    servicenow_priority = _IMPACT_URGENCY_MATRIX.get((impact_number or 0, urgency_number or 0)) or _to_number(priority) or 3
    return PRIORITY_NAMES[min(servicenow_priority, 4) - 1]


def most_severe_priority(*priority_names: str | None) -> str | None:
    known_priorities = [name for name in priority_names if name in PRIORITY_RANK]
    return min(known_priorities, key=lambda name: PRIORITY_RANK[name]) if known_priorities else None

"""The ServiceNow priority of each action item priority, as the setting writes it (``top:1,high:2,normal:3,low:4``). Lives in ``utils`` because the settings validate it at startup."""

from __future__ import annotations

from keigan.entities.status_values import ActionItemPriority


def parse_priority_map(text: str) -> dict[ActionItemPriority, str]:
    """``top:1,high:2,normal:3,low:4``: the ServiceNow priority of each Keigan priority. Every priority is named exactly once and no other word is accepted."""
    mapping: dict[ActionItemPriority, str] = {}
    for part in text.split(","):
        name, separator, value = (piece.strip() for piece in part.partition(":"))
        if not separator or not value:
            raise ValueError(f"Priority map entry {part.strip()!r} must look like name:value.")
        try:
            priority = ActionItemPriority(name)
        except ValueError as error:
            raise ValueError(f"Priority map names {name!r}, which is not an action item priority.") from error
        if priority in mapping or not value.isdigit():
            raise ValueError(f"Priority map entry for {name!r} is repeated or its value is not a number.")
        mapping[priority] = value
    missing = [priority.value for priority in ActionItemPriority if priority not in mapping]
    if missing:
        raise ValueError(f"Priority map must name every priority; missing: {', '.join(missing)}.")
    return mapping

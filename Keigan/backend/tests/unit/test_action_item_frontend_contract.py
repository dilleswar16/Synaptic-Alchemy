"""The action item words the screen offers are the words the server accepts, and each has a label in every screen language and a status chip (spec 29)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keigan.entities.status_values import ActionItemPriority, ActionItemStatus, ActionItemType

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"
ACTION_ITEMS_API = (FRONTEND_SOURCE / "api" / "actionItemsApi.ts").read_text(encoding="utf-8")
LOCALES = sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX")


def typescript_union(name: str) -> list[str]:
    match = re.search(rf"export type {name} =\s*(.*?);", ACTION_ITEMS_API, re.DOTALL)
    assert match, f"{name} not found in frontend/src/api/actionItemsApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def typescript_list(name: str) -> list[str]:
    match = re.search(rf"export const {name}:[^=]*=\s*\[(.*?)\];", ACTION_ITEMS_API, re.DOTALL)
    assert match, f"{name} not found in frontend/src/api/actionItemsApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


@pytest.mark.parametrize(("type_name", "list_name", "enum"), [
    ("ActionItemStatus", "actionItemStatuses", ActionItemStatus), ("ActionItemType", "actionItemTypes", ActionItemType), ("ActionItemPriority", "actionItemPriorities", ActionItemPriority),
])
def test_the_screen_words_are_the_server_words(type_name: str, list_name: str, enum: type) -> None:
    expected = sorted(member.value for member in enum)  # type: ignore[attr-defined]
    assert sorted(typescript_union(type_name)) == expected and sorted(typescript_list(list_name)) == expected


@pytest.mark.parametrize("locale", LOCALES)
def test_every_status_priority_and_type_has_a_label_in_every_screen_language(locale: str) -> None:
    labels = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "actionItems.json").read_text(encoding="utf-8"))
    assert sorted(labels["status"]) == sorted(member.value for member in ActionItemStatus)
    assert sorted(labels["priority"]) == sorted(member.value for member in ActionItemPriority)
    assert sorted(labels["type"]) == sorted(member.value for member in ActionItemType) and sorted(labels["typeHelp"]) == sorted(labels["type"])
    assert sorted(labels["statusAction"]) == sorted(member.value for member in ActionItemStatus if member not in (ActionItemStatus.PROPOSED,))


def test_the_status_chip_has_a_tone_for_every_status_and_priority() -> None:
    source = (FRONTEND_SOURCE / "features" / "action-items" / "components" / "ActionItemList.tsx").read_text(encoding="utf-8")
    for member in [*ActionItemStatus, *ActionItemPriority]:
        assert re.search(rf"\b{member.value}:\s*\"", source), f"no tone for {member.value}"

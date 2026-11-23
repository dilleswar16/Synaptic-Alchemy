"""The words of the error budget policy the screen knows are the words the server sends, and the screen has a label for each state it shows (spec 30)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keigan.entities.status_values import ErrorBudgetBreachKind, ErrorBudgetRequirementStatus, IncidentBudgetImpactState

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"
API = (FRONTEND_SOURCE / "api" / "errorBudgetApi.ts").read_text(encoding="utf-8")
LOCALES = sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX")


def typescript_list(name: str) -> list[str]:
    match = re.search(rf"export const {name}:[^=]*=\s*\[(.*?)\];", API, re.DOTALL)
    assert match, f"{name} not found in frontend/src/api/errorBudgetApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


@pytest.mark.parametrize(("list_name", "enum"), [("budgetImpactStates", IncidentBudgetImpactState), ("breachKinds", ErrorBudgetBreachKind), ("requirementStatuses", ErrorBudgetRequirementStatus)])
def test_the_screen_words_are_the_server_words(list_name: str, enum: type) -> None:
    assert sorted(typescript_list(list_name)) == sorted(member.value for member in enum)  # type: ignore[attr-defined]


@pytest.mark.parametrize("locale", LOCALES)
def test_every_impact_state_has_a_label_in_every_screen_language(locale: str) -> None:
    labels = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "errorBudgetPolicy.json").read_text(encoding="utf-8"))
    assert sorted(labels["state"]) == sorted(member.value for member in IncidentBudgetImpactState)

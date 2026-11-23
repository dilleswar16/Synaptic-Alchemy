"""The finding kinds the screen knows are the kinds the rules produce, and each has a label in every screen language (spec 32)."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from keigan.services.runbook_health_rules import RunbookFacts, RunbookHealthThresholds, findings_for

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"
API = (FRONTEND_SOURCE / "api" / "knowledgeApi.ts").read_text(encoding="utf-8")
LOCALES = sorted(path.name for path in (FRONTEND_SOURCE / "i18n" / "locales").iterdir() if path.is_dir() and path.name != "es-MX")


def screen_kinds() -> list[str]:
    match = re.search(r"export const runbookFindingKinds:[^=]*=\s*\[(.*?)\];", API, re.DOTALL)
    assert match, "runbookFindingKinds not found in frontend/src/api/knowledgeApi.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def the_kinds_the_rules_can_produce() -> set[str]:
    """Every rule fired at once: an empty, old, never-used, often-wrong runbook."""
    worst = RunbookFacts(has_trigger_symptoms=False, has_steps=False, times_referenced_count=0, created_on=date(2020, 1, 1), updated_on=date(2020, 1, 1), rated_investigation_count=10, incorrect_rated_count=10)
    return {finding.kind for finding in findings_for(worst, date(2026, 11, 23), RunbookHealthThresholds(60, 180, 3, 50.0))} | {finding.kind for finding in findings_for(replace(worst, times_referenced_count=1), date(2026, 11, 23), RunbookHealthThresholds(60, 180, 3, 50.0))}


def test_the_screen_kinds_are_the_rule_kinds() -> None:
    assert set(screen_kinds()) == the_kinds_the_rules_can_produce()


@pytest.mark.parametrize("locale", LOCALES)
def test_every_kind_has_a_chip_label_and_a_sentence_in_every_screen_language(locale: str) -> None:
    health = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / locale / "knowledge.json").read_text(encoding="utf-8"))["health"]
    assert set(health["kind"]) == set(screen_kinds()) and set(health["finding"]) == set(screen_kinds())

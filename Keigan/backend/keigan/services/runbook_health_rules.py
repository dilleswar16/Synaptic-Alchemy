"""Which runbooks need attention and why (spec 32, 4.2). Pure functions, no database, no model: a finding is a fact with its figures, never an opinion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RunbookFacts:
    has_trigger_symptoms: bool
    has_steps: bool
    times_referenced_count: int
    created_on: date
    updated_on: date
    rated_investigation_count: int  # investigations that matched the runbook and got a verdict from a person
    incorrect_rated_count: int


@dataclass(frozen=True)
class RunbookHealthThresholds:
    unused_after_days: int
    stale_after_days: int
    minimum_rated_investigations: int
    wrong_share_percent: float


@dataclass(frozen=True)
class RunbookFinding:
    kind: str
    parameters: dict[str, Any]


def findings_for(facts: RunbookFacts, today: date, thresholds: RunbookHealthThresholds) -> list[RunbookFinding]:
    findings: list[RunbookFinding] = []
    if not facts.has_trigger_symptoms:
        findings.append(RunbookFinding("no_trigger_symptoms", {}))  # without symptoms the runbook cannot be matched to an incident
    if not facts.has_steps:
        findings.append(RunbookFinding("no_steps", {}))
    age_days = (today - facts.created_on).days
    if facts.times_referenced_count == 0 and age_days >= thresholds.unused_after_days:
        findings.append(RunbookFinding("never_used", {"days": age_days}))
    since_update = (today - facts.updated_on).days
    if since_update >= thresholds.stale_after_days:
        findings.append(RunbookFinding("not_updated", {"days": since_update}))
    if facts.rated_investigation_count >= thresholds.minimum_rated_investigations and facts.incorrect_rated_count / facts.rated_investigation_count * 100 >= thresholds.wrong_share_percent:
        findings.append(RunbookFinding("often_wrong", {"incorrect": facts.incorrect_rated_count, "rated": facts.rated_investigation_count}))
    return findings

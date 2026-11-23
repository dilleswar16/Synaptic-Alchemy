"""keigan/services/weekly_review_facts.py, the pure part: the open policy requirements are named in the facts for the narration and in the digest's Markdown (spec 31, 4.3)."""

from __future__ import annotations

from typing import Any

from keigan.services.weekly_review_facts import review_fact_lines, review_markdown_lines


def sections_with(open_breaches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "budget": {"policyIsEnabled": True, "incidents": [], "incidentsWithoutFigureCount": 0, "breachesOpenedCount": len(open_breaches), "openBreaches": open_breaches},
        "actionItems": {"openCount": 0, "overdueCount": 0, "overdue": [], "doneThisWeekCount": 0, "acceptedThisWeekCount": 0, "topPriorityWithoutOwner": [], "suggestedWaitingCount": 0},
        "runbooks": {"withFindingsCount": 0, "runbooks": []},
    }


OPEN = [
    {"kind": "single_incident", "sharePercent": 41.7, "incidentNumber": "INC0002", "sliName": "availability"},
    {"kind": "budget_exhausted", "sharePercent": None, "incidentNumber": None, "sliName": "latency"},
]


def test_each_open_requirement_is_named_in_the_markdown_with_its_kind_what_it_concerns_and_its_share() -> None:
    markdown = "\n".join(review_markdown_lines(sections_with(OPEN)))
    assert "- Open policy requirement (single incident): INC0002, 41.7 % of the budget" in markdown
    assert "- Open policy requirement (budget exhausted): latency" in markdown


def test_the_narration_is_given_the_same_open_requirements() -> None:
    facts = "\n".join(review_fact_lines(sections_with(OPEN)))
    assert "Open policy requirements: single incident INC0002 (41.7%); budget exhausted latency." in facts


def test_nothing_is_added_when_no_requirement_is_open() -> None:
    assert not any("Open policy requirement" in line for line in review_markdown_lines(sections_with([])) + review_fact_lines(sections_with([])))

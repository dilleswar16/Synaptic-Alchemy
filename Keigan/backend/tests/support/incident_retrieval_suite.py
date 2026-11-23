"""The retrieval suite of similar-incident memory (spec 34, 4.10): labelled cases, run through the real retriever, scored without any model.

A case says what is known about the current incident, which past incidents exist (and in which application, how old, how trusted, whether hidden), which applications the reader may read,
which past incidents must be found and which must never be. ``run_cases`` builds each case's past incidents in the database, asks the real ``StructuredKeywordRetriever``, removes them again
and returns what came back; ``summarise`` turns that into recall@1, recall@3, mean reciprocal rank, the two gates (access and cross-application wording-only, both must be zero) and a
classification of the misses (4.9: is the miss about vocabulary or about missing facts?).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryKey
from keigan.services.incident_memory_builder import InvestigationFacts
from keigan.services.incident_memory_keys import MemoryFacts, build_match_keys
from keigan.services.incident_memory_retention import delete_incident_memory
from keigan.services.incident_memory_retriever import CurrentInvestigation, StructuredKeywordRetriever
from keigan.services.incident_memory_scoring import catalogue
from keigan.utils.text_utils import term_frequencies, tokenize_for_search
from keigan.utils.time_utils import utc_now

CASES_PATH = Path(__file__).with_name("incident_retrieval_cases.yaml")
LOW_OVERLAP = 0.2  # spec 34, 4.9: a miss with no shared key and less word overlap than this is about vocabulary


@dataclass(frozen=True)
class PastIncident:
    case_incident_id: str
    application: str
    days_ago: int
    verdict: str | None
    status: str
    title: str
    wording: str
    facts: dict[str, Any]


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    description: str
    current_application: str
    current_wording: str
    current_facts: dict[str, Any]
    readable_applications: list[str]
    past: list[PastIncident]
    expect: list[str]  # must all come back, in this order when ``expect_order``
    must_not_appear: list[str]
    expect_order: bool
    expect_rejected: list[str]  # of the expected ones, those that must come back labelled "marked incorrect"


@dataclass
class CaseOutcome:
    case: RetrievalCase
    returned: list[str] = field(default_factory=list)  # case incident ids, in the order the retriever gave them
    rejected: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    forbidden_returned: list[str] = field(default_factory=list)
    access_violations: list[str] = field(default_factory=list)  # returned though the reader may not read their application
    cross_application_wording_only: list[str] = field(default_factory=list)  # returned from another application with no hard fact in common
    out_of_order: bool = False
    miss_classes: dict[str, str] = field(default_factory=dict)  # missed incident -> "vocabulary" or "missing_facts"
    first_expected_rank: int | None = None


def load_cases(path: Path = CASES_PATH) -> list[RetrievalCase]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[RetrievalCase] = []
    for raw in document["cases"]:
        current = raw["current"]
        past = [
            PastIncident(item["id"], item["application"], item["days_ago"], item.get("verdict"), item.get("status", "active"), item.get("title", item["id"]), item.get("wording", ""), item.get("facts", {}))
            for item in raw.get("past", [])
        ]
        cases.append(RetrievalCase(
            raw["id"], raw["description"], current["application"], current.get("wording", ""), current.get("facts", {}), raw["reader_can_read"], past, raw.get("expect", []), raw.get("must_not_appear", []),
            raw.get("expect_order", False), raw.get("expect_rejected", []),
        ))
    return cases


def _facts(values: dict[str, Any]) -> MemoryFacts:
    return MemoryFacts(
        services={f"svc:{name}": name for name in values.get("services", [])}, resource_identifiers=values.get("resources", []), error_templates=values.get("errors", []),
        incident_category=values.get("category"), alert_rules=[(rule.lower(), rule) for rule in values.get("alert_rules", [])], change_operations=values.get("change_operations", []),
        dependency_targets=values.get("dependency_targets", []),
    )


def _key_pairs(values: dict[str, Any]) -> set[tuple[str, str]]:
    return {(key.kind, key.value_hash) for key in build_match_keys(_facts(values))}


def _word_overlap(current_wording: str, past_wording: str) -> float:
    current_terms = set(tokenize_for_search(current_wording))
    return len(current_terms & set(tokenize_for_search(past_wording))) / len(current_terms) if current_terms else 0.0


async def run_cases(session: AsyncSession, cases: list[RetrievalCase], application_ids: dict[str, str]) -> list[CaseOutcome]:
    """``application_ids`` maps the case files' application names to real application ids. Each case's past incidents are removed again before the next case."""
    retriever = StructuredKeywordRetriever(session, get_settings())
    required_kinds = set(catalogue()["cross_application_required_key_kinds"])
    outcomes: list[CaseOutcome] = []
    for case in cases:
        investigation_ids: list[str] = []
        entry_to_case_id: dict[str, str] = {}
        for item in case.past:
            investigation = Investigation(application_id=application_ids[item.application], investigation_status="completed", user_feedback_verdict=item.verdict)
            session.add(investigation)
            await session.flush()
            occurred_at = utc_now() - timedelta(days=item.days_ago)
            entry = IncidentMemoryEntry(
                application_id=application_ids[item.application], investigation_id=investigation.investigation_id, entry_status=item.status, occurred_at=occurred_at, incident_title_text=item.title,
                cause_source="none", fix_source="none", search_terms_json=term_frequencies(f"{item.title}\n{item.wording}"), service_ids_json=[],
            )
            session.add(entry)
            await session.flush()
            for key in build_match_keys(_facts(item.facts)):
                session.add(IncidentMemoryKey(incident_memory_entry_id=entry.incident_memory_entry_id, key_kind=key.kind, key_value_hash=key.value_hash, key_display_text=key.display_text))
            investigation_ids.append(investigation.investigation_id)
            entry_to_case_id[entry.incident_memory_entry_id] = item.case_incident_id
        await session.flush()
        current = CurrentInvestigation(
            f"suite-{uuid4().hex}",
            InvestigationFacts(application_ids[case.current_application], None, case.case_id, case.current_wording, utc_now(), [], _facts(case.current_facts)),
        )
        found = await retriever.find(current, {application_ids[name] for name in case.readable_applications})
        ours = [item for item in found if item.entry.incident_memory_entry_id in entry_to_case_id]  # an entry the seed built is not part of the case
        outcome = CaseOutcome(case, returned=[entry_to_case_id[item.entry.incident_memory_entry_id] for item in ours], rejected=[entry_to_case_id[item.entry.incident_memory_entry_id] for item in ours if item.match.is_rejected])
        by_id = {item.case_incident_id: item for item in case.past}
        current_keys = _key_pairs(case.current_facts)
        readable = set(case.readable_applications)
        for returned_id in outcome.returned:
            past = by_id[returned_id]
            if past.application not in readable:
                outcome.access_violations.append(returned_id)
            shared_kinds = {kind for kind, _ in current_keys & _key_pairs(past.facts)}
            if past.application != case.current_application and not shared_kinds & required_kinds:
                outcome.cross_application_wording_only.append(returned_id)
        outcome.forbidden_returned = [item for item in outcome.returned if item in case.must_not_appear]
        outcome.missed = [item for item in case.expect if item not in outcome.returned]
        ranks = [outcome.returned.index(item) + 1 for item in case.expect if item in outcome.returned]
        outcome.first_expected_rank = min(ranks) if ranks else None
        present = [item for item in outcome.returned if item in case.expect]
        outcome.out_of_order = case.expect_order and present != [item for item in case.expect if item in present]
        for missed_id in outcome.missed:
            past = by_id[missed_id]
            shares_a_key = bool(current_keys & _key_pairs(past.facts))
            outcome.miss_classes[missed_id] = "vocabulary" if not shares_a_key and _word_overlap(case.current_wording, f"{past.title} {past.wording}") < LOW_OVERLAP else "missing_facts"
        outcomes.append(outcome)
        await delete_incident_memory(session, investigation_ids)
        await session.execute(delete(Investigation).where(Investigation.investigation_id.in_(investigation_ids)))
        await session.flush()
    return outcomes


@dataclass(frozen=True)
class SuiteReport:
    case_count: int
    cases_with_expectations: int
    recall_at_1: float
    recall_at_3: float
    mean_reciprocal_rank: float
    access_violation_count: int  # gate: must be 0
    cross_application_keyword_only_count: int  # gate: must be 0
    forbidden_returned_count: int
    out_of_order_cases: list[str]
    wrongly_unlabelled_or_labelled: list[str]
    missed_cases: dict[str, dict[str, str]]  # case id -> {incident id: miss class}


def summarise(outcomes: list[CaseOutcome]) -> SuiteReport:
    expecting = [outcome for outcome in outcomes if outcome.case.expect]
    wanted = len(expecting)  # recall@k counts a case as found when at least one of the incidents it expects is in the first k
    in_top_1 = sum(1 for outcome in expecting if any(item in outcome.returned[:1] for item in outcome.case.expect))
    in_top_3 = sum(1 for outcome in expecting if any(item in outcome.returned[:3] for item in outcome.case.expect))
    reciprocal_ranks = [1 / outcome.first_expected_rank if outcome.first_expected_rank else 0.0 for outcome in expecting]
    return SuiteReport(
        case_count=len(outcomes), cases_with_expectations=len(expecting),
        recall_at_1=in_top_1 / wanted if wanted else 1.0, recall_at_3=in_top_3 / wanted if wanted else 1.0, mean_reciprocal_rank=sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 1.0,
        access_violation_count=sum(len(outcome.access_violations) for outcome in outcomes),
        cross_application_keyword_only_count=sum(len(outcome.cross_application_wording_only) for outcome in outcomes),
        forbidden_returned_count=sum(len(outcome.forbidden_returned) for outcome in outcomes),
        out_of_order_cases=[outcome.case.case_id for outcome in outcomes if outcome.out_of_order],
        wrongly_unlabelled_or_labelled=[outcome.case.case_id for outcome in outcomes if set(outcome.rejected) & set(outcome.case.expect) != set(outcome.case.expect_rejected) & set(outcome.returned)],
        missed_cases={outcome.case.case_id: outcome.miss_classes for outcome in outcomes if outcome.missed},
    )

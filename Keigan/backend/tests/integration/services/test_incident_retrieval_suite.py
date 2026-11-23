"""The retrieval suite of similar-incident memory (spec 34, 4.10): the shipped labelled cases, run through the real retriever, and the gates they must meet."""

from __future__ import annotations

import pytest

from keigan.config.database_config import open_session
from support.incident_retrieval_suite import CaseOutcome, RetrievalCase, SuiteReport, load_cases, run_cases, summarise

KNOWN_MISSES = {"wording_only_inside_one_application_is_a_known_miss"}  # documented in the case file: words alone score at most 0.30 against a minimum of 0.35


@pytest.fixture(scope="module")
async def outcomes(seed_context) -> list[CaseOutcome]:
    application_ids = {"claims": seed_context.application_ids_by_code["CLMJP"], "payments": seed_context.application_ids_by_code["PAYAU"], "chad": seed_context.application_ids_by_code["CHAD"]}
    async with open_session() as session:
        return await run_cases(session, load_cases(), application_ids)


@pytest.fixture(scope="module")
async def report(outcomes: list[CaseOutcome]) -> SuiteReport:
    result = summarise(outcomes)
    print(f"\nincident retrieval suite: {result}")  # shown with -s; the numbers a person reads when calibrating the weights
    return result


def test_the_case_file_loads_and_every_case_names_what_it_expects_or_forbids() -> None:
    cases: list[RetrievalCase] = load_cases()
    assert len(cases) >= 12 and len({case.case_id for case in cases}) == len(cases)
    assert all(case.expect or case.must_not_appear for case in cases)


async def test_nothing_is_ever_returned_from_an_application_the_reader_cannot_read(report: SuiteReport) -> None:
    assert report.access_violation_count == 0


async def test_wording_alone_never_brings_in_another_application(report: SuiteReport) -> None:
    assert report.cross_application_keyword_only_count == 0


async def test_no_case_returns_an_incident_it_must_not(outcomes: list[CaseOutcome]) -> None:
    assert {outcome.case.case_id: outcome.forbidden_returned for outcome in outcomes if outcome.forbidden_returned} == {}


async def test_the_order_and_the_incorrect_label_are_as_labelled(report: SuiteReport) -> None:
    assert report.out_of_order_cases == [] and report.wrongly_unlabelled_or_labelled == []


async def test_the_only_miss_is_the_documented_one_and_it_is_about_weights_not_vocabulary(report: SuiteReport) -> None:
    assert set(report.missed_cases) == KNOWN_MISSES
    assert report.missed_cases["wording_only_inside_one_application_is_a_known_miss"] == {"same_words_no_facts": "missing_facts"}  # high overlap, so more weight on words would find it, not vectors


async def test_the_scores_have_not_dropped(report: SuiteReport) -> None:
    assert report.recall_at_3 >= 0.85 and report.recall_at_1 >= 0.85 and report.mean_reciprocal_rank >= 0.85  # 6 of the 7 cases that expect something (the seventh is the documented miss)

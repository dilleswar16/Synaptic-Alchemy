"""keigan/services/ask_keigan_memory_tools.py: find_similar_incidents, "have we seen this before?" (spec 34, 4.7)."""

from __future__ import annotations

import pytest

from keigan.ai.tool_registry import AskKeiganScope
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from support.ask_keigan_tool_calls import ADMIN, CLMJP_AND_PAYAU_READER, CLMJP_READER, NO_ACCESS, run_tool
from tests.integration.services.test_incident_memory import build, investigated, unique_error

pytestmark = pytest.mark.usefixtures("seed_context")
GLOBAL = AskKeiganScope.GLOBAL


async def a_past_and_a_current(seed_context):  # noqa: ANN001, ANN201
    error = unique_error()
    past = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=40, title="Past pool exhaustion", template=error, verdict="correct", resolution_note="Raised the pool size.")
    current = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Current pool exhaustion", template=error)
    await build(past.investigation_id)
    return past, current


async def test_an_investigation_gets_the_past_incident_with_its_cause_its_fix_and_why_it_matched(seed_context) -> None:
    past, current = await a_past_and_a_current(seed_context)
    outcome = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, CLMJP_READER, scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    [item] = [item for item in outcome.output.items if item.investigation_id == past.investigation_id]
    assert (item.reviewed_as, item.fix_text, item.fix_source, item.was_marked_incorrect, item.is_same_application) == ("correct", "Raised the pool size.", "resolution_note", False, True)
    assert any(line.startswith("error_signature:") for line in item.matched_on)
    assert outcome.output.summary.startswith("Found ") and outcome.output.is_available is True
    assert ("investigation", past.investigation_id) in {(record.kind, record.id) for record in outcome.records}
    assert seed_context.application_ids_by_code["CLMJP"] in outcome.applications_read


async def test_an_incident_is_compared_through_its_latest_finished_investigation_and_one_not_yet_investigated_has_nothing_to_compare(seed_context) -> None:
    past, current = await a_past_and_a_current(seed_context)
    found = await run_tool("find_similar_incidents", {"incident_id": current.incident_id}, CLMJP_READER, scope=GLOBAL)
    assert past.investigation_id in {item.investigation_id for item in found.output.items}
    waiting = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=0, title="Not investigated yet", status="running")
    nothing = await run_tool("find_similar_incidents", {"incident_id": waiting.incident_id}, CLMJP_READER, scope=GLOBAL)
    assert nothing.output.items == [] and nothing.output.is_available is False and "not finished" in nothing.output.summary


async def test_words_alone_find_a_past_incident_of_the_named_application_only(seed_context) -> None:
    word = f"quokka{unique_error()[6:14]}"
    past = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=30, title=f"{word} outage in the claims batch", verdict="correct", why=f"The {word} queue was full.")
    await build(past.investigation_id)
    outcome = await run_tool("find_similar_incidents", {"text": f"{word} outage in the claims batch", "application_code": "CLMJP"}, CLMJP_READER, scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert past.investigation_id in {item.investigation_id for item in outcome.output.items}
    elsewhere = await run_tool("find_similar_incidents", {"text": f"{word} outage in the claims batch", "application_code": "PAYAU"}, CLMJP_AND_PAYAU_READER, scope=GLOBAL)
    assert past.investigation_id not in {item.investigation_id for item in elsewhere.output.items}  # wording never crosses applications


async def test_exactly_one_way_to_ask_and_a_description_needs_its_application(seed_context) -> None:
    _, current = await a_past_and_a_current(seed_context)
    for arguments in ({}, {"investigation_id": current.investigation_id, "incident_id": current.incident_id}, {"text": "pool exhaustion again"}):
        outcome = await run_tool("find_similar_incidents", arguments, CLMJP_READER, scope=GLOBAL)
        assert outcome.status is not ChatRunStepStatus.SUCCEEDED and outcome.output is None, arguments


async def test_a_person_without_access_gets_nothing_and_an_unknown_investigation_is_not_found(seed_context) -> None:
    _, current = await a_past_and_a_current(seed_context)
    refused = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, NO_ACCESS, scope=GLOBAL)
    assert (refused.status, refused.outcome_code, refused.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)
    missing = await run_tool("find_similar_incidents", {"investigation_id": "nope"}, CLMJP_READER, scope=GLOBAL)
    assert (missing.status, missing.outcome_code) == (ChatRunStepStatus.FAILED, "not_found")


async def test_a_past_incident_of_an_application_the_person_cannot_read_is_not_returned_but_an_admin_gets_it(seed_context) -> None:
    error = unique_error()
    elsewhere = await investigated(seed_context.application_ids_by_code["CHAD"], days_ago=40, title="Chad outage", template=error, verdict="correct")
    current = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Claims outage", template=error)
    await build(elsewhere.investigation_id)
    reader = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, CLMJP_READER, scope=GLOBAL)
    assert elsewhere.investigation_id not in {item.investigation_id for item in reader.output.items}
    admin = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, ADMIN, scope=GLOBAL)
    [item] = [item for item in admin.output.items if item.investigation_id == elsewhere.investigation_id]
    assert item.is_same_application is False and seed_context.application_ids_by_code["CHAD"] in admin.applications_read


async def test_a_conversation_that_covers_fewer_applications_searches_only_those(seed_context) -> None:
    error = unique_error()
    payments = await investigated(seed_context.application_ids_by_code["PAYAU"], days_ago=40, title="Payments outage", template=error, verdict="correct")
    current = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Claims outage", template=error)
    await build(payments.investigation_id)
    both = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, CLMJP_AND_PAYAU_READER, scope=GLOBAL)
    assert payments.investigation_id in {item.investigation_id for item in both.output.items}
    narrowed = await run_tool("find_similar_incidents", {"investigation_id": current.investigation_id}, CLMJP_AND_PAYAU_READER, scope=GLOBAL, profile_user=CLMJP_READER)
    assert payments.investigation_id not in {item.investigation_id for item in narrowed.output.items}

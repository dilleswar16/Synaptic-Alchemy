"""keigan/services/ask_keigan_investigation_tools.py: the investigation and incident tools of the global scope (spec 23, 5, 9.2, 9.4).

Each tool reads through its service as the asking person, adds every application it read to the answer's applications, and refuses an application
the person cannot read in the same way the first eight tools do.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from keigan.ai.tool_registry import AskKeiganScope
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from keigan.utils.time_utils import utc_now
from support.ask_keigan_global_tool_data import add_evidence, add_hypothesis, create_incident, create_investigation
from support.ask_keigan_tool_calls import run_tool, user
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")
GLOBAL = AskKeiganScope.GLOBAL


def reader_of(*applications) -> object:  # type: ignore[no-untyped-def]
    return user(f"reader.{uuid.uuid4().hex[:6]}@keigan.local", *(f"{application.application_code}_reader" for application in applications))


async def investigation_with_two_hypotheses(incident_id: str | None = None) -> tuple[object, str]:
    application = await create_scoped_application()
    investigation_id = await create_investigation(application.application_id, incident_id=incident_id, executive_summary="Checkout failed after release 41.")
    await add_evidence(investigation_id, code="E1", title="Error rate spike")
    await add_evidence(investigation_id, code="E2", title="Slow database calls", signal_strength="low")
    await add_hypothesis(investigation_id, title="Release 41 broke the connection pool", confidence=0.8, leading=True, supporting_codes=["E1"], contradicting_codes=["E2"])
    await add_hypothesis(investigation_id, title="Database saturation", confidence=0.3, leading=False, supporting_codes=["E2"])
    return application, investigation_id


# ── get_investigation ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_get_investigation_summarises_the_hypotheses_and_the_evidence_index() -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.summary == f"Completed investigation of Scope {application.application_code}: 2 hypotheses, 2 evidence items"
    assert [(item.hypothesis_title, item.confidence_score, item.is_leading_hypothesis) for item in outcome.output.hypotheses] == [
        ("Release 41 broke the connection pool", 0.8, True), ("Database saturation", 0.3, False),
    ]
    assert outcome.output.hypotheses[0].supporting_evidence_codes == ["E1"] and outcome.output.hypotheses[0].contradicting_evidence_codes == ["E2"]
    assert [(item.evidence_code, item.evidence_title) for item in outcome.output.evidence] == [("E1", "Error rate spike"), ("E2", "Slow database calls")]
    assert (outcome.output.evidence_count, outcome.output.total_evidence_count, outcome.output.evidence_is_truncated) == (2, 2, False)
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("investigation", investigation_id, application.application_id)]


async def test_get_investigation_does_not_send_who_asked_or_the_model_names() -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader_of(application), scope=GLOBAL)
    assert "requester@keigan.local" not in outcome.model_view_text and "requested_by" not in outcome.model_view_text
    assert "model_names" not in outcome.model_view_text and "token" not in outcome.model_view_text


async def test_get_investigation_masks_an_address_in_its_ai_written_summary() -> None:
    application = await create_scoped_application()
    investigation_id = await create_investigation(application.application_id, executive_summary="Ask ops.lead@keigan.local before the rollback.")
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED
    assert "ops.lead@keigan.local" not in outcome.model_view_text and "<EMAIL_1>" in outcome.output.executive_summary


async def test_get_investigation_cuts_its_evidence_index_to_the_list_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 1)
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader_of(application), scope=GLOBAL)
    assert [item.evidence_code for item in outcome.output.evidence] == ["E1"]
    assert (outcome.output.evidence_count, outcome.output.total_evidence_count, outcome.output.evidence_is_truncated) == (1, 2, True)


async def test_get_investigation_of_an_unknown_id_is_not_found() -> None:
    application = await create_scoped_application()
    outcome = await run_tool("get_investigation", {"investigation_id": str(uuid.uuid4())}, reader_of(application), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.FAILED, "not_found", None)


async def test_get_investigation_of_an_application_the_person_cannot_read_is_refused() -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    other = await create_scoped_application()
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader_of(other), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output, outcome.model_view_text) == (ChatRunStepStatus.REFUSED, "access_denied", None, None)
    assert application.application_code not in outcome.model_message and "Completed investigation" not in outcome.model_message


async def test_a_reader_of_two_applications_reads_the_investigation_of_either_and_reports_its_application(monkeypatch: pytest.MonkeyPatch) -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    second = await create_scoped_application()
    both = reader_of(application, second)
    outcome = await run_tool("get_investigation", {"investigation_id": investigation_id}, both, scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED and outcome.applications_read == frozenset({application.application_id})


async def test_get_investigation_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application, investigation_id = await investigation_with_two_hypotheses()
    reader = reader_of(application)
    before = await run_tool("get_investigation", {"investigation_id": investigation_id}, reader, scope=GLOBAL)
    after = await run_tool("get_investigation", {"investigation_id": investigation_id}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert before.status is ChatRunStepStatus.SUCCEEDED
    assert (after.status, after.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── list_investigations ───────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_list_investigations_lists_the_readable_ones_newest_first_with_a_summary() -> None:
    application = await create_scoped_application()
    older = await create_investigation(application.application_id, status="completed", created_at=utc_now() - timedelta(days=2))
    newer = await create_investigation(application.application_id, status="running", created_at=utc_now() - timedelta(hours=1))
    outcome = await run_tool("list_investigations", {}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert [item.investigation_id for item in outcome.output.items] == [newer, older]
    assert outcome.output.summary == "2 investigations in the last 168 hours"
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (2, 2, False)
    assert {(record.kind, record.application_id) for record in outcome.records} == {("investigation", application.application_id)}


async def test_list_investigations_can_be_limited_to_some_statuses_and_an_incident() -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Checkout errors")
    linked = await create_investigation(application.application_id, status="failed", incident_id=incident_id)
    await create_investigation(application.application_id, status="completed")
    outcome = await run_tool("list_investigations", {"statuses": ["failed"], "incident_id": incident_id}, reader_of(application), scope=GLOBAL)
    assert [item.investigation_id for item in outcome.output.items] == [linked]
    assert outcome.output.items[0].incident_title == "Checkout errors"


async def test_list_investigations_of_the_named_application_only_and_none_for_an_application_without_any() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_investigation(first.application_id)
    outcome = await run_tool("list_investigations", {"application_codes": [second.application_code]}, reader_of(first, second), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED
    assert outcome.output.summary == "No investigations in the last 168 hours" and outcome.output.items == []
    assert outcome.applications_read == frozenset({second.application_id})


async def test_list_investigations_refuses_a_code_the_person_cannot_read_and_returns_nothing_of_the_others() -> None:
    readable = await create_scoped_application()
    hidden = await create_scoped_application()
    await create_investigation(hidden.application_id)
    outcome = await run_tool("list_investigations", {"application_codes": [readable.application_code, hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output, outcome.model_view_text) == (ChatRunStepStatus.REFUSED, "access_denied", None, None)


async def test_list_investigations_reports_every_application_it_covered_and_cuts_to_the_list_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    for _ in range(3):
        await create_investigation(first.application_id)
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 2)
    outcome = await run_tool("list_investigations", {}, reader_of(first, second), scope=GLOBAL)
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (2, 3, True)
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})


async def test_list_investigations_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    await create_investigation(application.application_id)
    reader = reader_of(application)
    outcome = await run_tool("list_investigations", {}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── list_incidents ────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_list_incidents_lists_them_with_their_priority_status_and_source() -> None:
    application = await create_scoped_application()
    await create_incident(application.application_id, title="Checkout errors", number="INC0000201", status="investigating", priority="P1", source="alert")
    await create_incident(application.application_id, title="Old batch", number="INC0000202", status="closed", priority="P4")
    outcome = await run_tool("list_incidents", {}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.summary == "2 incidents in the last 168 hours"
    first = next(item for item in outcome.output.items if item.incident_number == "INC0000201")
    assert (first.title, first.status, first.keigan_priority, first.source, first.application_code) == ("Checkout errors", "investigating", "P1", "alert", application.application_code)
    assert outcome.applications_read == frozenset({application.application_id})


async def test_list_incidents_filters_by_status_priority_source_and_words_in_the_title_or_number() -> None:
    application = await create_scoped_application()
    await create_incident(application.application_id, title="Checkout errors", number="INC0000301", status="investigating", priority="P1", source="servicenow")
    await create_incident(application.application_id, title="Claims backlog", number="INC0000302", status="investigating", priority="P1", source="alert")
    await create_incident(application.application_id, title="Checkout slow", number="INC0000303", status="resolved", priority="P2", source="servicenow")
    by_status_and_priority = await run_tool("list_incidents", {"statuses": ["investigating"], "priorities": ["P1"]}, reader_of(application), scope=GLOBAL)
    by_source = await run_tool("list_incidents", {"sources": ["alert"]}, reader_of(application), scope=GLOBAL)
    by_text = await run_tool("list_incidents", {"text": "checkout"}, reader_of(application), scope=GLOBAL)
    by_number = await run_tool("list_incidents", {"text": "INC0000302"}, reader_of(application), scope=GLOBAL)
    assert sorted(item.incident_number for item in by_status_and_priority.output.items) == ["INC0000301", "INC0000302"]
    assert [item.incident_number for item in by_source.output.items] == ["INC0000302"]
    assert sorted(item.incident_number for item in by_text.output.items) == ["INC0000301", "INC0000303"]
    assert [item.incident_number for item in by_number.output.items] == ["INC0000302"]


async def test_list_incidents_refuses_an_application_code_the_person_cannot_read() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_incident(hidden.application_id, title="Hidden incident")
    outcome = await run_tool("list_incidents", {"application_codes": [hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)


async def test_list_incidents_reports_every_application_it_covered(  ) -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_incident(first.application_id, title="First incident")
    outcome = await run_tool("list_incidents", {}, reader_of(first, second), scope=GLOBAL)
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})


async def test_list_incidents_cuts_to_the_list_limit_and_says_how_many_there_are(monkeypatch: pytest.MonkeyPatch) -> None:
    application = await create_scoped_application()
    for number in range(3):
        await create_incident(application.application_id, title=f"Incident {number}", number=f"INC000040{number}")
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 2)
    outcome = await run_tool("list_incidents", {}, reader_of(application), scope=GLOBAL)
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (2, 3, True)
    assert len(outcome.records) == 2


# ── get_incident ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_get_incident_by_its_keigan_id_gives_the_record_and_its_latest_investigation() -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Checkout errors", number="INC0000501", description="Customers see 500 errors.", priority="P2")
    investigation_id = await create_investigation(application.application_id, incident_id=incident_id, executive_summary="Release 41 broke the pool.")
    outcome = await run_tool("get_incident", {"incident_reference": incident_id}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.summary == "Incident INC0000501: Checkout errors (P2, investigating)"
    assert outcome.output.description == "Customers see 500 errors."
    assert outcome.output.latest_investigation_id == investigation_id
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("incident", incident_id, application.application_id)]


async def test_get_incident_by_its_servicenow_number_finds_the_same_record() -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Checkout errors", number="INC0000502")
    outcome = await run_tool("get_incident", {"incident_reference": "inc0000502"}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED and outcome.output.incident_id == incident_id


async def test_get_incident_with_an_unknown_number_or_id_is_not_found() -> None:
    application = await create_scoped_application()
    by_number = await run_tool("get_incident", {"incident_reference": "INC9999999"}, reader_of(application), scope=GLOBAL)
    by_id = await run_tool("get_incident", {"incident_reference": str(uuid.uuid4())}, reader_of(application), scope=GLOBAL)
    assert (by_number.status, by_number.outcome_code) == (ChatRunStepStatus.FAILED, "not_found")
    assert (by_id.status, by_id.outcome_code) == (ChatRunStepStatus.FAILED, "not_found")


async def test_get_incident_by_the_number_of_an_application_the_person_cannot_read_is_not_found_not_a_leak() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_incident(hidden.application_id, title="Hidden incident", number="INC0000503")
    outcome = await run_tool("get_incident", {"incident_reference": "INC0000503"}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.FAILED, "not_found", None)
    assert "Hidden incident" not in outcome.model_message


async def test_get_incident_by_the_id_of_an_application_the_person_cannot_read_is_refused() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    incident_id = await create_incident(hidden.application_id, title="Hidden incident", number="INC0000504")
    outcome = await run_tool("get_incident", {"incident_reference": incident_id}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)
    assert "Hidden incident" not in outcome.model_message


async def test_get_incident_reports_the_application_of_the_record_as_read() -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Checkout errors", number="INC0000506")
    outcome = await run_tool("get_incident", {"incident_reference": incident_id}, reader_of(application), scope=GLOBAL)
    assert outcome.applications_read == frozenset({application.application_id})


async def test_get_incident_cuts_its_description_to_the_passage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Long", number="INC0000505", description="x" * 900)
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_passage_characters", 200)
    outcome = await run_tool("get_incident", {"incident_reference": incident_id}, reader_of(application), scope=GLOBAL)
    assert len(outcome.output.description) == 202 and outcome.output.description.endswith("...")  # 199 characters and the ellipsis, which the masker's NFKC pass writes as three dots

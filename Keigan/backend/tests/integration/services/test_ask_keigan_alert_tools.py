"""keigan/services/ask_keigan_alert_tools.py: the alert tools of the global scope (spec 23, 5, 9.2, 9.4): list_alert_groups, get_alert_group, get_alert_noise_summary."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from keigan.ai.tool_registry import AskKeiganScope
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from keigan.utils.time_utils import utc_now
from support.ask_keigan_global_tool_data import create_alert_group, create_incident
from support.ask_keigan_tool_calls import run_tool, user
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")
GLOBAL = AskKeiganScope.GLOBAL


def reader_of(*applications) -> object:  # type: ignore[no-untyped-def]
    return user(f"reader.{uuid.uuid4().hex[:6]}@keigan.local", *(f"{application.application_code}_reader" for application in applications))


# ── list_alert_groups ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_list_alert_groups_lists_the_groups_of_the_readable_applications_by_last_activity_with_a_summary() -> None:
    application = await create_scoped_application()
    older = await create_alert_group(application.application_id, title="Queue backlog", last_activity_at=utc_now() - timedelta(hours=2))
    newer = await create_alert_group(application.application_id, title="Checkout errors", last_activity_at=utc_now() - timedelta(minutes=5))
    outcome = await run_tool("list_alert_groups", {}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert [item.alert_group_id for item in outcome.output.items] == [newer, older]
    assert outcome.output.summary == "2 alert groups in the last 24 hours"
    first = outcome.output.items[0]
    assert (first.group_title, first.group_status, first.application_code, first.member_alert_count) == ("Checkout errors", "open", application.application_code, 1)
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("alert_group", newer, application.application_id), ("alert_group", older, application.application_id)]


async def test_list_alert_groups_filters_by_status_score_and_the_window() -> None:
    application = await create_scoped_application()
    wanted = await create_alert_group(application.application_id, title="Checkout errors", status="resolved", priority_score=80.0)
    await create_alert_group(application.application_id, title="Low score", status="resolved", priority_score=20.0)
    await create_alert_group(application.application_id, title="Open one", status="open", priority_score=90.0)
    await create_alert_group(application.application_id, title="Last week", status="resolved", priority_score=95.0, last_activity_at=utc_now() - timedelta(days=5))
    outcome = await run_tool("list_alert_groups", {"statuses": ["resolved"], "minimum_priority_score": 50}, reader_of(application), scope=GLOBAL)
    assert [item.alert_group_id for item in outcome.output.items] == [wanted]


async def test_list_alert_groups_of_the_named_application_only() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_alert_group(first.application_id, title="First app group")
    second_group = await create_alert_group(second.application_id, title="Second app group")
    outcome = await run_tool("list_alert_groups", {"application_codes": [second.application_code]}, reader_of(first, second), scope=GLOBAL)
    assert [item.alert_group_id for item in outcome.output.items] == [second_group]
    assert outcome.applications_read == frozenset({second.application_id})


async def test_list_alert_groups_refuses_a_code_the_person_cannot_read_and_returns_nothing_of_the_others() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_alert_group(hidden.application_id, title="Hidden group")
    outcome = await run_tool("list_alert_groups", {"application_codes": [readable.application_code, hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output, outcome.model_view_text) == (ChatRunStepStatus.REFUSED, "access_denied", None, None)


async def test_list_alert_groups_reports_every_application_it_covered_and_cuts_to_the_list_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    for _ in range(3):
        await create_alert_group(first.application_id, title="Repeating group")
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 2)
    outcome = await run_tool("list_alert_groups", {}, reader_of(first, second), scope=GLOBAL)
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (2, 3, True)
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})


async def test_list_alert_groups_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    await create_alert_group(application.application_id, title="Checkout errors")
    reader = reader_of(application)
    outcome = await run_tool("list_alert_groups", {"application_codes": [application.application_code]}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── get_alert_group ───────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_get_alert_group_gives_its_members_and_the_pipeline_decisions() -> None:
    application = await create_scoped_application()
    incident_id = await create_incident(application.application_id, title="Checkout errors")
    group_id = await create_alert_group(application.application_id, title="Checkout errors", incident_id=incident_id)
    outcome = await run_tool("get_alert_group", {"alert_group_id": group_id}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert outcome.output.summary == "1 alert in Checkout errors (open), priority score 60"
    assert (outcome.output.incident_id, outcome.output.member_count, outcome.output.total_member_count) == (incident_id, 1, 1)
    member = outcome.output.members[0]
    assert (member.rule_name, member.alert_status, member.occurrence_count, member.alert_summary) == ("High error rate", "firing", 3, "High error rate on the checkout service")
    assert [(decision.pipeline_stage, decision.decision_outcome) for decision in outcome.output.decisions] == [("decide", "investigation_started")]
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("alert_group", group_id, application.application_id)]


async def test_get_alert_group_does_not_send_the_alert_links() -> None:
    application = await create_scoped_application()
    group_id = await create_alert_group(application.application_id, title="Checkout errors")
    outcome = await run_tool("get_alert_group", {"alert_group_id": group_id}, reader_of(application), scope=GLOBAL)
    assert "http" not in outcome.model_view_text and "alert_link" not in outcome.model_view_text


async def test_get_alert_group_of_an_unknown_id_is_not_found() -> None:
    application = await create_scoped_application()
    outcome = await run_tool("get_alert_group", {"alert_group_id": str(uuid.uuid4())}, reader_of(application), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.FAILED, "not_found", None)


async def test_get_alert_group_of_an_application_the_person_cannot_read_is_refused() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    group_id = await create_alert_group(hidden.application_id, title="Hidden group")
    outcome = await run_tool("get_alert_group", {"alert_group_id": group_id}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)
    assert "Hidden group" not in outcome.model_message


async def test_a_reader_of_two_applications_opens_the_group_of_either_and_reports_its_application() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    group_id = await create_alert_group(second.application_id, title="Second app group")
    outcome = await run_tool("get_alert_group", {"alert_group_id": group_id}, reader_of(first, second), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED and outcome.applications_read == frozenset({second.application_id})


# ── get_alert_noise_summary ───────────────────────────────────────────────────────────────────────────────────────────────────
async def test_the_noise_summary_counts_alerts_groups_and_investigations_of_the_window() -> None:
    application = await create_scoped_application()
    await create_alert_group(application.application_id, title="Checkout errors")
    outcome = await run_tool("get_alert_noise_summary", {}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert [(step.step_key, step.count) for step in outcome.output.steps] == [("received", 3), ("deduplicated", 1), ("filtered", 1), ("groups", 1), ("investigations", 1)]
    assert outcome.output.summary == "3 alerts received in the last 168 hours: 1 alert group, 1 investigation"
    assert outcome.applications_read == frozenset({application.application_id})
    assert [(record.kind, record.id) for record in outcome.records] == [("application", application.application_id)]


async def test_the_noise_summary_of_an_application_without_alerts_says_so_with_zero_counts() -> None:
    application = await create_scoped_application()
    outcome = await run_tool("get_alert_noise_summary", {}, reader_of(application), scope=GLOBAL)
    assert outcome.output.summary == "0 alerts received in the last 168 hours: 0 alert groups, 0 investigations"


async def test_the_noise_summary_refuses_a_code_the_person_cannot_read() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_alert_group(hidden.application_id, title="Hidden group")
    outcome = await run_tool("get_alert_noise_summary", {"application_codes": [hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)


async def test_the_noise_summary_of_two_applications_reports_both_as_read() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_alert_group(first.application_id, title="First group")
    outcome = await run_tool("get_alert_noise_summary", {}, reader_of(first, second), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})
    assert outcome.output.summary == "3 alerts received in the last 168 hours: 1 alert group, 1 investigation"


async def test_the_noise_summary_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    reader = reader_of(application)
    outcome = await run_tool("get_alert_noise_summary", {"application_codes": [application.application_code]}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


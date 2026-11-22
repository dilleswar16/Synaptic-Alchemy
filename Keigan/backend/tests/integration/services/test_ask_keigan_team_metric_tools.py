"""keigan/services/ask_keigan_team_metric_tools.py: list_team_members and get_reliability_metrics of the global scope (spec 23, 5, 9.2, 9.4, decision D2)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from keigan.ai.tool_registry import AskKeiganScope
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ChatRunStepStatus
from keigan.services import ask_keigan_tools  # noqa: F401 — registers the tools
from keigan.utils.time_utils import utc_now
from support.ask_keigan_global_tool_data import add_team_member, create_incident
from support.ask_keigan_tool_calls import run_tool, user
from support.telemetry_scope import create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")
GLOBAL = AskKeiganScope.GLOBAL
REAL_LOOKING_PEOPLE = ("Aiko Appadmin", "Ben Builder", "Cara Owner")
REAL_LOOKING_EMAILS = ("aiko.appadmin@keigan.local", "ben.builder@keigan.local", "cara.owner@keigan.local")


def reader_of(*applications) -> object:  # type: ignore[no-untyped-def]
    return user(f"reader.{uuid.uuid4().hex[:6]}@keigan.local", *(f"{application.application_code}_reader" for application in applications))


async def team_of_three(application_id: str) -> None:
    await add_team_member(application_id, display_name=REAL_LOOKING_PEOPLE[0], email=REAL_LOOKING_EMAILS[0], role="sre")
    await add_team_member(application_id, display_name=REAL_LOOKING_PEOPLE[1], email=REAL_LOOKING_EMAILS[1], role="developer")
    await add_team_member(application_id, display_name=REAL_LOOKING_PEOPLE[2], email=REAL_LOOKING_EMAILS[2], role="sre", is_active=False)


async def entra_ids_of(application_id: str) -> list[str]:
    async with open_session() as session:
        return [row for row in (await session.scalars(select(Stakeholder.entra_object_id).where(Stakeholder.application_id == application_id))).all() if row]


# ── list_team_members ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async def test_team_members_are_aliased_by_role_and_no_name_email_or_identity_reaches_the_output() -> None:
    application = await create_scoped_application()
    await team_of_three(application.application_id)
    entra_ids = await entra_ids_of(application.application_id)
    outcome = await run_tool("list_team_members", {"application_code": application.application_code}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    assert [item.alias for item in outcome.output.items] == ["sre 1", "developer 1", "sre 2"]
    leaked_words = [*REAL_LOOKING_PEOPLE, *REAL_LOOKING_EMAILS, *entra_ids]
    for text in (outcome.output.model_dump_json(), outcome.output.summary, outcome.model_view_text, outcome.model_message):
        for leaked in leaked_words:
            assert leaked not in text, leaked


async def test_team_members_list_their_role_and_status_without_their_contact_details() -> None:
    application = await create_scoped_application()
    await team_of_three(application.application_id)
    outcome = await run_tool("list_team_members", {"application_code": application.application_code}, reader_of(application), scope=GLOBAL)
    assert [(item.alias, item.stakeholder_role, item.is_active, item.team_member_status) for item in outcome.output.items] == [
        ("sre 1", "sre", True, "listed"), ("developer 1", "developer", True, "listed"), ("sre 2", "sre", False, "inactive"),
    ]
    assert outcome.output.summary == "3 team members: 1 developer, 2 sre"
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (3, 3, False)


async def test_team_members_can_be_limited_to_some_roles() -> None:
    application = await create_scoped_application()
    await team_of_three(application.application_id)
    outcome = await run_tool("list_team_members", {"application_code": application.application_code, "roles": ["developer"]}, reader_of(application), scope=GLOBAL)
    assert [item.alias for item in outcome.output.items] == ["developer 1"]


async def test_the_team_record_is_the_application_team_and_the_application_is_reported_as_read() -> None:
    application = await create_scoped_application()
    await team_of_three(application.application_id)
    outcome = await run_tool("list_team_members", {"application_code": application.application_code}, reader_of(application), scope=GLOBAL)
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("team", application.application_id, application.application_id)]
    assert outcome.applications_read == frozenset({application.application_id})


async def test_the_team_of_an_application_the_person_cannot_read_is_refused() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await team_of_three(hidden.application_id)
    outcome = await run_tool("list_team_members", {"application_code": hidden.application_code}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output, outcome.model_view_text) == (ChatRunStepStatus.REFUSED, "access_denied", None, None)
    assert REAL_LOOKING_PEOPLE[0] not in outcome.model_message


async def test_a_reader_of_two_applications_gets_the_team_of_the_one_asked_for_only() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await add_team_member(first.application_id, display_name="Dana First", email="dana.first@keigan.local", role="manager")
    await add_team_member(second.application_id, display_name="Eli Second", email="eli.second@keigan.local", role="lead")
    outcome = await run_tool("list_team_members", {"application_code": second.application_code}, reader_of(first, second), scope=GLOBAL)
    assert [item.alias for item in outcome.output.items] == ["lead 1"]
    assert "Dana First" not in outcome.model_view_text and outcome.applications_read == frozenset({second.application_id})


async def test_the_team_is_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    await team_of_three(application.application_id)
    reader = reader_of(application)
    outcome = await run_tool("list_team_members", {"application_code": application.application_code}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")


# ── get_reliability_metrics ───────────────────────────────────────────────────────────────────────────────────────────────────
async def test_reliability_metrics_give_each_application_its_figures_and_no_acknowledgement_figure() -> None:
    application = await create_scoped_application()
    await create_incident(application.application_id, title="Checkout errors")
    await create_incident(application.application_id, title="Queue backlog")
    outcome = await run_tool("get_reliability_metrics", {"application_codes": [application.application_code]}, reader_of(application), scope=GLOBAL)
    assert outcome.status is ChatRunStepStatus.SUCCEEDED, outcome.outcome_message
    item = outcome.output.items[0]
    assert (item.application_code, item.incidents_opened_count, item.incidents_resolved_count) == (application.application_code, 2, 0)
    assert item.share_correct is None and item.rated_count == 0 and item.minimum_rating_sample == get_settings().metrics_minimum_rating_sample
    assert outcome.output.summary == "2 incidents opened and 0 resolved in the last 720 hours"
    for text in (outcome.output.summary, outcome.model_view_text):
        assert "acknowledg" not in text.lower() and "mtta" not in text.lower()
    assert [(record.kind, record.id, record.application_id) for record in outcome.records] == [("application", application.application_id, application.application_id)]


async def test_reliability_metrics_count_only_the_window_asked_for() -> None:
    application = await create_scoped_application()
    await create_incident(application.application_id, title="Old incident", opened_at=utc_now() - timedelta(days=3))
    outcome = await run_tool("get_reliability_metrics", {"application_codes": [application.application_code], "lookback_hours": 24}, reader_of(application), scope=GLOBAL)
    assert outcome.output.items[0].incidents_opened_count == 0
    assert outcome.output.summary == "0 incidents opened and 0 resolved in the last 24 hours"


async def test_reliability_metrics_of_every_application_in_scope_when_none_is_named() -> None:
    first, second = await create_scoped_application(), await create_scoped_application()
    await create_incident(first.application_id, title="First incident")
    outcome = await run_tool("get_reliability_metrics", {}, reader_of(first, second), scope=GLOBAL)
    assert {item.application_code for item in outcome.output.items} == {first.application_code, second.application_code}
    assert outcome.applications_read == frozenset({first.application_id, second.application_id})


async def test_reliability_metrics_refuse_an_application_code_the_person_cannot_read() -> None:
    readable, hidden = await create_scoped_application(), await create_scoped_application()
    await create_incident(hidden.application_id, title="Hidden incident")
    outcome = await run_tool("get_reliability_metrics", {"application_codes": [hidden.application_code]}, reader_of(readable), scope=GLOBAL)
    assert (outcome.status, outcome.outcome_code, outcome.output) == (ChatRunStepStatus.REFUSED, "access_denied", None)
    assert "Hidden incident" not in outcome.model_message


async def test_reliability_metrics_report_only_the_applications_they_measured_and_cut_to_the_list_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second, third = await create_scoped_application(), await create_scoped_application(), await create_scoped_application()
    monkeypatch.setattr(get_settings(), "ask_keigan_tool_list_item_limit", 2)
    outcome = await run_tool("get_reliability_metrics", {}, reader_of(first, second, third), scope=GLOBAL)
    assert (outcome.output.item_count, outcome.output.total_count, outcome.output.is_truncated) == (2, 3, True)
    assert len(outcome.applications_read) == 2 and len(outcome.records) == 2


async def test_reliability_metrics_are_refused_to_a_person_whose_access_was_removed_while_the_answer_ran() -> None:
    application = await create_scoped_application()
    reader = reader_of(application)
    outcome = await run_tool("get_reliability_metrics", {"application_codes": [application.application_code]}, user("nobody@keigan.local"), scope=GLOBAL, profile_user=reader)
    assert (outcome.status, outcome.outcome_code) == (ChatRunStepStatus.REFUSED, "access_denied")

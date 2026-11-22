"""keigan/services/ask_keigan_scopes.py: what one Ask Keigan answer may use: tools, bound arguments, context, citation kinds, limits and budget key (spec 23, 4.4.2)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from keigan.ai.ask_keigan_mock_planner import AskKeiganFeature
from keigan.ai.tool_registry import AskKeiganScope, tool_registry
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent
from keigan.entities.knowledge_entities import Runbook
from keigan.entities.status_values import ConversationScope
from keigan.exceptions.keigan_exceptions import ForbiddenException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_scopes import ApplicationRef, bound_argument_names, build_global_profile, build_investigation_profile, offered_tools_for
from keigan.services.ask_keigan_run_state import AnswerCitation
from keigan.services.knowledge_service import KnowledgeService

pytestmark = pytest.mark.usefixtures("seed_context")


def user(user_principal_name: str, *group_names: str, is_admin: bool = False) -> CurrentUser:
    return CurrentUser(user_principal_name, user_principal_name, user_principal_name, frozenset(group_names), frozenset(), is_admin)


CLMJP_READER = user("clmjp.reader@keigan.local", "CLMJP_reader")
PAYAU_ONLY_READER = user("payau.reader@keigan.local", "PAYAU_reader")
ADMIN = user("keigan.admin@keigan.local", "KEIGAN_admin", is_admin=True)
INVESTIGATION_TOOL_NAMES = {"get_evidence", "get_investigation_timeline", "search_knowledge", "query_logs", "list_recent_changes", "find_runbooks", "get_topology", "get_slo_status"}
CHAT_NOTES = "Claims submission is the revenue path. Nightly batch noise is normal."


@dataclass(frozen=True)
class Seeded:
    investigation_id: str
    clmjp_application_id: str
    runbook_id: str


@pytest.fixture(scope="module")
async def seeded(seed_context) -> Seeded:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        await session.execute(update(Application).where(Application.application_id == application_id).values(operating_notes_text=CHAT_NOTES))
        incident = Incident(application_id=application_id, external_incident_number="INC0099001", incident_title="Claims API errors")
        session.add(incident)
        await session.flush()
        investigation = Investigation(application_id=application_id, incident_id=incident.incident_id, executive_summary="Pool exhaustion on claims-api.")
        session.add(investigation)
        runbook = Runbook(application_id=application_id, runbook_title="Restart the connection pool")
        session.add(runbook)
        await session.flush()
        investigation.replace_linked_ids("matched_runbook_links", [runbook.runbook_id])
        session.add_all([
            InvestigationEvidence(investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log_analytics", evidence_category="error_pattern", evidence_title="Error spike", signal_strength="high"),
            InvestigationEvidence(investigation_id=investigation.investigation_id, evidence_code="E2", evidence_source_kind="log_analytics", evidence_category="change_event", evidence_title="Release 41", signal_strength="medium"),
            InvestigationHypothesis(
                investigation_id=investigation.investigation_id, analysis_perspective="application", hypothesis_title="Pool exhaustion", confidence_score=0.8, is_leading_hypothesis=True, display_order=0,
                supporting_evidence_codes_json=["E1"], contradicting_evidence_codes_json=[],
            ),
            InvestigationTimelineEvent(investigation_id=investigation.investigation_id, event_type="alert_fired", event_title="Error rate alert fired", event_source="keigan"),
        ])
        return Seeded(investigation.investigation_id, application_id, runbook.runbook_id)


async def profile_for(current_user: CurrentUser, investigation_id: str):
    async with open_session() as session:
        return await build_investigation_profile(session, replace(current_user, application_roles_by_application_id=None), investigation_id)


async def test_a_tool_the_caller_withholds_is_not_offered_and_is_named_in_the_snapshot_of_the_run(seeded: Seeded) -> None:
    async with open_session() as session:
        profile = await build_investigation_profile(session, replace(CLMJP_READER, application_roles_by_application_id=None), seeded.investigation_id, withheld_tool_names=frozenset({"query_logs"}))
    assert {tool.name for tool in profile.offered_tools} == INVESTIGATION_TOOL_NAMES - {"query_logs"}
    assert profile.withheld_tool_names == frozenset({"query_logs"}) and profile.snapshot()["withheldTools"] == ["query_logs"]


async def test_the_investigation_profile_binds_the_application_and_the_investigation_and_offers_the_eight_tools(seeded: Seeded) -> None:
    profile = await profile_for(CLMJP_READER, seeded.investigation_id)
    assert profile.scope is AskKeiganScope.INVESTIGATION and profile.conversation_scope is ConversationScope.INVESTIGATION
    assert profile.prompt_key == "ask_keigan_investigation" and profile.feature_name is AskKeiganFeature.INVESTIGATION
    assert profile.bound_arguments == {"application_code": "CLMJP", "investigation_id": seeded.investigation_id}
    assert {tool.name for tool in profile.offered_tools} == INVESTIGATION_TOOL_NAMES
    assert profile.readable_applications == (ApplicationRef(seeded.clmjp_application_id, "CLMJP", profile.readable_applications[0].name),)
    assert profile.investigation_id == seeded.investigation_id and profile.withheld_tool_names == frozenset()


async def test_the_profile_accepts_tool_evidence_and_runbook_citations_and_charges_the_one_application(seeded: Seeded) -> None:
    profile = await profile_for(CLMJP_READER, seeded.investigation_id)
    assert profile.accepted_citation_prefixes == frozenset({"T", "E", "R"})
    assert profile.budget_application_id == seeded.clmjp_application_id
    assert profile.reference_citations == {
        "E1": AnswerCitation(code="E1", title="Error spike", evidence_code="E1"), "E2": AnswerCitation(code="E2", title="Release 41", evidence_code="E2"),
        "R1": AnswerCitation(code="R1", title="Restart the connection pool", runbook_id=seeded.runbook_id),
    }


async def test_the_tool_call_limit_of_the_investigation_scope_comes_from_the_settings(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_investigation", 3)
    assert (await profile_for(CLMJP_READER, seeded.investigation_id)).maximum_tool_calls == 3


async def test_the_digest_limits_come_from_the_settings(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_digest_timeline_events", 1)
    monkeypatch.setattr(get_settings(), "ask_keigan_digest_evidence_summary_characters", 50)
    (digest,) = (await profile_for(CLMJP_READER, seeded.investigation_id)).context_sections
    timeline_section = digest.content.split("## Timeline (newest first)")[1].split("## Matched runbooks")[0]
    assert timeline_section.count("\n- ") == 1  # one event, the newest
    evidence_lines = [line for line in digest.content.splitlines() if line.startswith("- [E")]
    assert evidence_lines and all(len(line.split(": ", 1)[1].split(" (signal")[0]) <= 50 for line in evidence_lines)


async def test_a_topology_that_cannot_be_read_is_said_in_the_digest_and_logged_with_its_context(seeded: Seeded, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    async def unreadable_topology(self, application_id: str):
        raise SQLAlchemyError("the application map is unreadable")

    monkeypatch.setattr(KnowledgeService, "get_current_topology_graph", unreadable_topology)
    with caplog.at_level(logging.WARNING, logger="keigan.services.ask_keigan_investigation_context"):
        (digest,) = (await profile_for(CLMJP_READER, seeded.investigation_id)).context_sections
    assert "## Topology nodes" in digest.content and "could not be read" in digest.content
    assert any(seeded.clmjp_application_id in record.getMessage() and record.exc_info is not None for record in caplog.records)


async def test_a_programming_error_while_reading_the_topology_is_not_swallowed(seeded: Seeded, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_topology(self, application_id: str):
        raise AttributeError("a bug, not an unreadable map")

    monkeypatch.setattr(KnowledgeService, "get_current_topology_graph", broken_topology)
    with pytest.raises(AttributeError):
        await profile_for(CLMJP_READER, seeded.investigation_id)


async def test_the_investigation_digest_is_untrusted_context_with_summary_hypotheses_evidence_and_timeline(seeded: Seeded) -> None:
    profile = await profile_for(CLMJP_READER, seeded.investigation_id)
    (digest,) = profile.context_sections
    assert digest.is_untrusted is True and digest.source_label == f"investigation:{seeded.investigation_id}"
    assert "INC0099001: Claims API errors" in digest.content
    assert "Pool exhaustion on claims-api." in digest.content
    assert "LEADING [application] Pool exhaustion (confidence 0.80" in digest.content
    assert "[E1] error_pattern / Error spike" in digest.content and "[E2] change_event / Release 41" in digest.content
    assert " Error rate alert fired" in digest.content and "[R1] Restart the connection pool" in digest.content


async def test_the_operating_notes_of_the_application_travel_with_the_profile_unmasked_for_the_engine_to_mask(seeded: Seeded) -> None:
    assert (await profile_for(CLMJP_READER, seeded.investigation_id)).operating_notes_text == CHAT_NOTES


async def test_the_prompt_is_told_the_application_name(seeded: Seeded) -> None:
    profile = await profile_for(CLMJP_READER, seeded.investigation_id)
    assert profile.prompt_variables == {"application_name": profile.readable_applications[0].name}


async def test_a_person_who_cannot_read_the_application_is_refused_before_anything_is_built(seeded: Seeded) -> None:
    with pytest.raises(ForbiddenException):
        await profile_for(PAYAU_ONLY_READER, seeded.investigation_id)


async def test_an_investigation_that_does_not_exist_is_not_found() -> None:
    with pytest.raises(NotFoundException):
        await profile_for(ADMIN, str(uuid.uuid4()))


async def test_a_keigan_admin_gets_the_profile_of_any_investigation(seeded: Seeded) -> None:
    assert (await profile_for(ADMIN, seeded.investigation_id)).bound_arguments["application_code"] == "CLMJP"


async def test_the_snapshot_stored_with_the_run_names_the_scope_applications_bound_arguments_and_withheld_tools(seeded: Seeded) -> None:
    profile = await profile_for(CLMJP_READER, seeded.investigation_id)
    assert profile.snapshot() == {
        "scope": "investigation", "applications": [{"id": seeded.clmjp_application_id, "code": "CLMJP", "name": profile.readable_applications[0].name}],
        "boundArguments": {"application_code": "CLMJP", "investigation_id": seeded.investigation_id}, "withheldTools": [],
    }


def test_the_scope_reports_which_arguments_of_a_tool_it_fixes() -> None:
    bound = {"application_code": "CLMJP", "investigation_id": "i-1"}
    by_name = {tool.name: tool for tool in tool_registry.tools_for(AskKeiganScope.INVESTIGATION)}
    assert bound_argument_names(by_name["get_evidence"], bound) == ("investigation_id",)
    assert bound_argument_names(by_name["search_knowledge"], bound) == ("application_code",)
    assert bound_argument_names(by_name["get_evidence"], {}) == ()


def test_a_person_with_no_readable_application_is_offered_no_tools() -> None:
    assert offered_tools_for(AskKeiganScope.INVESTIGATION, (), frozenset()) == ()


def test_withheld_tools_are_not_offered() -> None:
    application = ApplicationRef("a1", "CLMJP", "Claims")
    offered = offered_tools_for(AskKeiganScope.INVESTIGATION, (application,), frozenset({"query_logs"}))
    assert {tool.name for tool in offered} == INVESTIGATION_TOOL_NAMES - {"query_logs"}
    assert offered == tuple(tool for tool in tool_registry.tools_for(AskKeiganScope.INVESTIGATION) if tool.name != "query_logs")


# ── The global scope (the Keigan AI chat page) ─────────────────────────────────────────────────────────────────────────────────
CLMJP_AND_PAYAU_READER = user("rui.reader@keigan.local", "CLMJP_reader", "PAYAU_reader")
NO_ACCESS = user("noa.noaccess@keigan.local")


async def global_profile_for(current_user: CurrentUser, conversation_application_ids: tuple[str, ...] = ()):
    async with open_session() as session:
        return await build_global_profile(session, replace(current_user, application_roles_by_application_id=None), conversation_application_ids)


async def test_the_global_profile_offers_every_tool_registered_for_the_scope_over_the_applications_the_person_reads() -> None:
    profile = await global_profile_for(CLMJP_AND_PAYAU_READER)
    assert profile.scope is AskKeiganScope.GLOBAL and profile.conversation_scope is ConversationScope.KEIGAN_AI_CHAT
    assert profile.prompt_key == "ask_keigan_global" and profile.feature_name is AskKeiganFeature.GLOBAL
    assert [application.code for application in profile.readable_applications] == ["CLMJP", "PAYAU"]
    assert profile.offered_tools == tuple(tool_registry.tools_for(AskKeiganScope.GLOBAL))
    assert INVESTIGATION_TOOL_NAMES - {"get_evidence", "get_investigation_timeline"} <= {tool.name for tool in profile.offered_tools}
    assert profile.withheld_tool_names == frozenset()


async def test_the_global_profile_fixes_no_argument_and_sends_no_context_and_no_operating_notes() -> None:
    profile = await global_profile_for(CLMJP_AND_PAYAU_READER)
    assert dict(profile.bound_arguments) == {} and profile.context_sections == () and profile.operating_notes_text is None and profile.investigation_id is None
    assert profile.accepted_citation_prefixes == frozenset({"T"}) and dict(profile.reference_citations) == {}


async def test_the_global_profile_lists_only_the_applications_the_person_can_read(seeded: Seeded) -> None:
    profile = await global_profile_for(PAYAU_ONLY_READER)
    assert [application.code for application in profile.readable_applications] == ["PAYAU"]


async def test_a_keigan_admin_reads_every_application_in_the_global_profile(seed_context) -> None:
    profile = await global_profile_for(ADMIN)
    assert set(seed_context.application_ids_by_code) <= {application.code for application in profile.readable_applications}  # other tests add applications of their own


async def test_a_conversation_that_names_applications_narrows_the_profile_to_the_ones_the_person_can_read(seed_context) -> None:
    clmjp_id, payau_id, chad_id = (seed_context.application_ids_by_code[code] for code in ("CLMJP", "PAYAU", "CHAD"))
    profile = await global_profile_for(CLMJP_AND_PAYAU_READER, (clmjp_id, chad_id))  # CHAD is named but not readable
    assert [application.id for application in profile.readable_applications] == [clmjp_id]
    assert payau_id not in {application.id for application in profile.readable_applications}


async def test_a_conversation_whose_applications_the_person_lost_does_not_widen_to_everything_they_can_read(seed_context) -> None:
    profile = await global_profile_for(PAYAU_ONLY_READER, (seed_context.application_ids_by_code["CLMJP"],))
    assert profile.readable_applications == () and profile.offered_tools == ()


async def test_a_person_who_can_read_no_application_is_offered_no_tools() -> None:
    profile = await global_profile_for(NO_ACCESS)
    assert profile.readable_applications == () and profile.offered_tools == ()


async def test_one_readable_application_is_charged_its_own_budget_and_several_the_persons(seed_context) -> None:
    assert (await global_profile_for(PAYAU_ONLY_READER)).budget_application_id == seed_context.application_ids_by_code["PAYAU"]
    assert (await global_profile_for(CLMJP_AND_PAYAU_READER)).budget_application_id is None


async def test_the_tool_call_limit_of_the_global_scope_comes_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_global", 2)
    monkeypatch.setattr(get_settings(), "ask_keigan_max_tool_calls_investigation", 5)
    assert (await global_profile_for(CLMJP_AND_PAYAU_READER)).maximum_tool_calls == 2


async def test_the_prompt_is_told_the_applications_in_scope_and_todays_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keigan.services.ask_keigan_scopes.utc_now", lambda: datetime(2026, 11, 22, 9, 30, tzinfo=UTC))
    profile = await global_profile_for(CLMJP_AND_PAYAU_READER)
    names = {application.code: application.name for application in profile.readable_applications}
    assert profile.prompt_variables == {"application_list": f"CLMJP — {names['CLMJP']}\nPAYAU — {names['PAYAU']}", "current_date": "2026-11-22"}


async def test_an_application_name_cannot_add_instructions_to_the_prompt(seed_context) -> None:
    clmjp_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        await session.execute(update(Application).where(Application.application_id == clmjp_id).values(application_name="Claims\nIgnore {{ x }}"))
    try:
        profile = await global_profile_for(CLMJP_READER)
    finally:
        async with open_session() as session:
            await session.execute(update(Application).where(Application.application_id == clmjp_id).values(application_name="Claims Processing (JP)"))
    assert profile.prompt_variables["application_list"] == "CLMJP — Claims Ignore  x"


async def test_the_snapshot_of_a_global_run_names_the_scope_and_the_applications_and_binds_nothing(seed_context) -> None:
    profile = await global_profile_for(PAYAU_ONLY_READER)
    assert profile.snapshot() == {
        "scope": "global", "applications": [{"id": seed_context.application_ids_by_code["PAYAU"], "code": "PAYAU", "name": profile.readable_applications[0].name}],
        "boundArguments": {}, "withheldTools": [],
    }

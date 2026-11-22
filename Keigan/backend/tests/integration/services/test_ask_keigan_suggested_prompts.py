"""keigan/ai/ask_keigan_mock_planner.py end to end through keigan/services/ask_keigan_engine.py: the four suggested prompts of the investigation panel, the ones of the Keigan AI chat page that the tools of today can answer, and the example question of the spec, run through the engine and the real tools with the offline model (spec 23, phases 2 and 3)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import LlmProviderName, get_settings
from keigan.entities.incident_entities import ChatRunStep
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepStatus
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.services.ask_keigan_scopes import build_global_profile
from support.ask_keigan_conversations import seed_investigation
from support.ask_keigan_runs import Finished, ask, profile_for, user
from support.ask_keigan_tool_data import ActivityLogStub, add_runbook, add_topology, change_event, create_slo_application, use_activity_log

pytestmark = pytest.mark.usefixtures("seed_context")

OUTSIDE_SCOPE_SENTENCE = "outside what I can answer"
RELEASE_41 = change_event(datetime(2026, 1, 5, 9, 42, tzinfo=UTC), "Release 41 deployed")

# The suggested prompts of the investigation panel (frontend investigations.json chat.prompts) in English and Japanese, and the one tool each is planned onto.
SUGGESTED_PROMPTS = [
    ("Why not the database?", "search_knowledge"),
    ("What changed in the last hour?", "list_recent_changes"),
    ("Draft a status update for executives", "get_investigation_timeline"),
    ("Explain this to a new engineer", "get_topology"),
    ("なぜデータベースではないのですか？", "search_knowledge"),
    ("直近 1 時間で何が変わりましたか？", "list_recent_changes"),
    ("経営層向けの状況報告を下書きして", "get_investigation_timeline"),
    ("新任エンジニア向けに説明して", "get_topology"),
]


@dataclass(frozen=True)
class Scenario:
    investigation_id: str
    application_code: str


@pytest.fixture(scope="module")
async def scenario(seed_context) -> Scenario:
    """One application that has SLOs, a runbook, an application map and an investigation with evidence and a timeline."""
    slo_application = await create_slo_application()
    await add_runbook(slo_application.application_id, "Database connection timeouts", "connection pool exhausted, sql timeouts", "1. Check the pool size.")
    await add_topology(slo_application.application_id, 1, is_current=True, understanding="Claims flow through the API into the database.")
    investigation = await seed_investigation(slo_application.application_id)
    return Scenario(investigation.investigation_id, slo_application.application_code)


@pytest.fixture(autouse=True)
def offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)


async def ask_in_investigation(scenario: Scenario, question: str) -> Finished:
    reader = user("planner.reader@keigan.local", f"{scenario.application_code}_reader")
    return await ask(await profile_for(reader, scenario.investigation_id), question, current_user=reader)


async def effective_arguments(finished: Finished) -> list[dict[str, object]]:
    async with open_session() as session:
        steps = (await session.scalars(select(ChatRunStep).where(ChatRunStep.answer_run_id == finished.run.answer_run_id, ChatRunStep.step_kind == "tool_call").order_by(ChatRunStep.sequence_number))).all()
    return [step.effective_arguments_json for step in steps]


@pytest.mark.parametrize(("prompt", "tool_name"), SUGGESTED_PROMPTS)
async def test_each_suggested_prompt_runs_its_tool_and_ends_in_a_cited_answer(monkeypatch: pytest.MonkeyPatch, scenario: Scenario, prompt: str, tool_name: str) -> None:
    use_activity_log(monkeypatch, ActivityLogStub([RELEASE_41]))
    finished = await ask_in_investigation(scenario, prompt)
    assert (finished.outcome.status, finished.outcome.stop_reason) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED)
    assert [(step.tool_name, step.citation_code, step.step_status) for step in finished.tool_steps] == [(tool_name, "T1", ChatRunStepStatus.SUCCEEDED)]
    (answer,) = finished.assistant_messages
    assert "[T1]" in answer.message_text and OUTSIDE_SCOPE_SENTENCE not in answer.message_text
    assert answer.message_payload_json["isUnverified"] is False and answer.message_payload_json["isRefusal"] is False
    assert [citation["code"] for citation in answer.message_payload_json["citations"]] == ["T1"]
    assert len(answer.message_payload_json["followUps"]) == 3


async def test_what_changed_in_the_last_hour_asks_the_changes_tool_for_one_hour_of_this_application(monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> None:
    use_activity_log(monkeypatch, ActivityLogStub([RELEASE_41]))
    finished = await ask_in_investigation(scenario, "What changed in the last hour?")
    assert await effective_arguments(finished) == [{"application_code": scenario.application_code, "lookback_hours": 1}]
    (answer,) = finished.assistant_messages
    assert "1 change in the last 1 hour; newest 2026-01-05 09:42 UTC [T1]." in answer.message_text


async def test_the_example_question_of_the_spec_checks_the_slos_and_then_the_changes(monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> None:
    use_activity_log(monkeypatch, ActivityLogStub([RELEASE_41]))
    finished = await ask_in_investigation(scenario, "Is claims-api burning its error budget, and did anything change before it started?")
    assert [(step.tool_name, step.citation_code, step.step_status) for step in finished.tool_steps] == [
        ("get_slo_status", "T1", ChatRunStepStatus.SUCCEEDED), ("list_recent_changes", "T2", ChatRunStepStatus.SUCCEEDED),
    ]
    (answer,) = finished.assistant_messages
    assert "4 SLOs: 1 healthy, 1 at risk, 1 breached, 1 without data [T1]." in answer.message_text
    assert "1 change in the last 24 hours; newest 2026-01-05 09:42 UTC [T2]." in answer.message_text


async def test_a_runbook_question_is_answered_from_the_runbooks_of_the_application(scenario: Scenario) -> None:
    finished = await ask_in_investigation(scenario, "Is there a runbook for database connection timeouts?")
    assert [(step.tool_name, step.step_status) for step in finished.tool_steps] == [("find_runbooks", ChatRunStepStatus.SUCCEEDED)]
    (answer,) = finished.assistant_messages
    assert "1 runbook matched [T1]." in answer.message_text


async def test_a_changes_question_whose_activity_log_cannot_be_read_says_it_could_not_check_and_never_says_no_changes(monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> None:
    use_activity_log(monkeypatch, ActivityLogStub(failure=IntegrationException("Azure answered 503", error_code="azure_unavailable")))
    finished = await ask_in_investigation(scenario, "What changed in the last hour?")
    assert [(step.tool_name, step.step_status, step.outcome_code) for step in finished.tool_steps] == [("list_recent_changes", ChatRunStepStatus.FAILED, "source_unavailable")]
    (answer,) = finished.assistant_messages
    assert "I could not check list_recent_changes" in answer.message_text
    assert "no changes" not in answer.message_text.lower() and "0 changes" not in answer.message_text


# The suggested prompts of the Keigan AI chat page (ChatService.suggested_prompts), planned onto the tools the global scope offers. The incident and predictive-signal ones need tools 9 to 19 and the
# failed-requests one needs a configured log source, so they are not run here.
GLOBAL_SUGGESTED_PROMPTS = [
    ("Which SLOs are at risk right now?", "get_slo_status"),
    ("What is the runbook for a database connection failure?", "find_runbooks"),
]


@pytest.mark.parametrize(("prompt", "tool_name"), GLOBAL_SUGGESTED_PROMPTS)
async def test_a_global_suggested_prompt_runs_its_tool_and_ends_in_a_cited_answer(scenario: Scenario, prompt: str, tool_name: str) -> None:
    reader = user("global.reader@keigan.local", f"{scenario.application_code}_reader")
    async with open_session() as session:
        profile = await build_global_profile(session, replace(reader, application_roles_by_application_id=None), ())
    finished = await ask(profile, prompt, current_user=reader)
    assert (finished.outcome.status, finished.outcome.stop_reason) == (ChatAnswerRunStatus.COMPLETED, ChatAnswerStopReason.ANSWERED)
    assert [(step.tool_name, step.citation_code, step.step_status) for step in finished.tool_steps] == [(tool_name, "T1", ChatRunStepStatus.SUCCEEDED)]
    (answer,) = finished.assistant_messages
    assert "[T1]" in answer.message_text and OUTSIDE_SCOPE_SENTENCE not in answer.message_text and answer.message_payload_json["isUnverified"] is False


async def test_the_changes_prompt_of_the_global_page_asks_for_one_day_of_the_application_it_names(monkeypatch: pytest.MonkeyPatch, scenario: Scenario) -> None:
    use_activity_log(monkeypatch, ActivityLogStub([RELEASE_41]))
    reader = user("global.reader@keigan.local", f"{scenario.application_code}_reader")
    async with open_session() as session:
        profile = await build_global_profile(session, replace(reader, application_roles_by_application_id=None), ())
    finished = await ask(profile, f"What changed on {scenario.application_code} in the last day?", current_user=reader)
    assert await effective_arguments(finished) == [{"application_code": scenario.application_code, "lookback_hours": 24}]

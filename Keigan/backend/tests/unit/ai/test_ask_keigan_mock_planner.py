"""keigan/ai/ask_keigan_mock_planner.py: the deterministic stand-in for the model's tool use when LLM_PROVIDER=mock (spec 23, section 4.6.7)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from keigan.ai import ask_keigan_mock_planner, llm_gateway
from keigan.ai.ask_keigan_answer_format import FOLLOW_UP_MARKER
from keigan.ai.ask_keigan_mock_planner import AskKeiganFeature, plan_agent_turn
from keigan.ai.llm_gateway import AgentPlannerInput, AgentToolRequest, AgentToolSpec, AgentTranscriptEntry, AgentTurnResult, LlmGateway, LlmUsageContext, ModelTier, PromptSection
from keigan.config.settings import LlmProviderName, get_settings
from keigan.entities.status_values import ToolCallingMode
from keigan.utils.string_table import string_table

OUTSIDE_SCOPE_ANSWER = "That is outside what I can answer from Keigan's data."


def test_the_outside_scope_sentence_is_read_from_the_string_table_and_not_written_a_second_time_in_the_planner() -> None:
    planner_source = Path(inspect.getsourcefile(ask_keigan_mock_planner)).read_text(encoding="utf-8")  # type: ignore[arg-type]
    assert OUTSIDE_SCOPE_ANSWER not in planner_source
    assert ask_keigan_mock_planner.OUTSIDE_SCOPE_ANSWER == OUTSIDE_SCOPE_ANSWER == string_table("en")["ask_keigan_answers"]["outside_scope"]


def tool(name: str, properties: dict[str, dict[str, object]], required: tuple[str, ...] = ()) -> AgentToolSpec:
    """A tool as the investigation scope offers it: ``application_code`` and ``investigation_id`` are bound by Keigan, so the model-facing schema omits them."""
    return AgentToolSpec(name=name, description=name, parameters_schema={"type": "object", "properties": properties, "required": list(required), "additionalProperties": False})


GET_EVIDENCE = tool("get_evidence", {"evidence_code": {"type": "string"}}, ("evidence_code",))
GET_TIMELINE = tool("get_investigation_timeline", {})
SEARCH_KNOWLEDGE = tool("search_knowledge", {"query": {"type": "string", "maxLength": 300}}, ("query",))
QUERY_LOGS = tool(
    "query_logs",
    {
        "service_name": {"type": "string"}, "question": {"type": "string"}, "lookback_minutes": {"type": "integer"}, "wants_pattern": {"type": "boolean"}, "failures_only": {"type": "boolean"},
    },
    ("service_name", "question"),
)
LIST_RECENT_CHANGES = tool("list_recent_changes", {"lookback_hours": {"type": "integer", "minimum": 1, "maximum": 720}})
FIND_RUNBOOKS = tool("find_runbooks", {"symptoms": {"type": "string", "maxLength": 300}, "maximum_results": {"type": "integer"}}, ("symptoms",))
GET_TOPOLOGY = tool("get_topology", {})
GET_SLO_STATUS = tool("get_slo_status", {"application_codes": {"type": "array"}, "statuses": {"type": "array"}})
PHASE_ONE_TOOLS = (GET_EVIDENCE, GET_TIMELINE, SEARCH_KNOWLEDGE, QUERY_LOGS)
INVESTIGATION_TOOLS = (*PHASE_ONE_TOOLS, LIST_RECENT_CHANGES, FIND_RUNBOOKS, GET_TOPOLOGY, GET_SLO_STATUS)


def question_entry(question: str) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(kind="data", section=PromptSection("Question", question, is_untrusted=True, source_label="chat:user-question"))


def context_entry(text: str) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(kind="data", section=PromptSection("Investigation", text, is_untrusted=True, source_label="investigation:digest"))


def history_entry(text: str) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(kind="data", section=PromptSection("Conversation so far", text, is_untrusted=True, source_label="chat:history"))


def spotlighted(body: str) -> str:
    return f'<untrusted_data source="tool:test" boundary="kg-abc">\n{body}\n</untrusted_data boundary="kg-abc">'


def turn(request: AgentToolRequest, result_text: str) -> tuple[AgentTranscriptEntry, AgentTranscriptEntry]:
    """What the engine appends after executing ``request``: the model turn that asked and the tool result."""
    return (
        AgentTranscriptEntry(kind="assistant", tool_requests=(request,)),
        AgentTranscriptEntry(kind="tool_result", tool_request_id=request.request_id, tool_name=request.tool_name, tool_result_text=result_text),
    )


def plan(*transcript: AgentTranscriptEntry, tools: tuple[AgentToolSpec, ...] = INVESTIGATION_TOOLS, allow_tool_requests: bool = True) -> AgentTurnResult:
    return plan_agent_turn(AgentPlannerInput(AskKeiganFeature.INVESTIGATION, "You are Keigan.", transcript, tools, allow_tool_requests))


def requested(result: AgentTurnResult) -> list[tuple[str, dict[str, object] | None]]:
    return [(request.tool_name, request.arguments) for request in result.tool_requests]


EVIDENCE_E2 = AgentToolRequest("k1", "get_evidence", {"evidence_code": "E2"})
TIMELINE_CALL = AgentToolRequest("k2", "get_investigation_timeline", {})
EVIDENCE_RESULT = spotlighted(json.dumps({"summary": "E2 is a failed-requests spike on claims-api (high strength)", "evidence_code": "E2"}))
TIMELINE_RESULT = spotlighted(json.dumps({"summary": "7 timeline events; newest 09:42 UTC"}))


# ── The example of the spec: two calls, then a cited answer ───────────────────────────────────────


def test_a_question_about_evidence_and_the_timeline_first_opens_the_evidence() -> None:
    result = plan(question_entry("Show me evidence E2 and what the timeline says before it"))
    assert result.finish == "tool_requests"
    assert requested(result) == [("get_evidence", {"evidence_code": "E2"})]
    assert result.tool_calling_mode == ToolCallingMode.SCRIPTED_MOCK and result.text == ""


def test_after_the_evidence_the_second_group_of_the_question_is_planned_as_the_next_turn() -> None:
    question = "Show me evidence E2 and what the timeline says before it"
    result = plan(question_entry(question), *turn(EVIDENCE_E2, EVIDENCE_RESULT))
    assert requested(result) == [("get_investigation_timeline", {})]
    assert result.tool_requests[0].request_id == "k2"


def test_after_both_calls_the_answer_has_one_cited_sentence_per_tool_call() -> None:
    question = "Show me evidence E2 and what the timeline says before it"
    result = plan(question_entry(question), *turn(EVIDENCE_E2, EVIDENCE_RESULT), *turn(TIMELINE_CALL, TIMELINE_RESULT))
    assert result.finish == "answer" and result.tool_requests == ()
    answer = result.text.split(FOLLOW_UP_MARKER)[0].strip()
    assert answer.splitlines() == [
        "E2 is a failed-requests spike on claims-api (high strength) [T1] [E2].",
        "7 timeline events; newest 09:42 UTC [T2].",
    ]


def test_a_question_with_one_group_needs_one_call_even_when_it_contains_and() -> None:
    result = plan(question_entry("Show me evidence E2 and explain it"), *turn(EVIDENCE_E2, EVIDENCE_RESULT))
    assert result.finish == "answer" and result.text.count("[T1]") == 1


def test_the_groups_run_in_the_order_the_question_mentions_them() -> None:
    result = plan(question_entry("What does the timeline say and show me evidence E7"))
    assert requested(result) == [("get_investigation_timeline", {})]


# ── What picks each tool ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("question", ["show me e2", "Open [E2] please", "evidence e2 details"])
def test_an_evidence_code_in_any_spelling_opens_that_evidence_in_capitals(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("get_evidence", {"evidence_code": "E2"})]


@pytest.mark.parametrize("question", ["Give me the timeline", "インシデントのタイムラインを見せて"])
def test_the_word_timeline_in_english_or_japanese_reads_the_timeline(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("get_investigation_timeline", {})]


def test_a_count_question_about_a_named_service_runs_a_log_query_with_the_window_and_the_failures_flag() -> None:
    result = plan(question_entry("How many errors did claims-api log in the last 3 hours?"))
    assert requested(result) == [(
        "query_logs",
        {"service_name": "claims-api", "question": "How many errors did claims-api log in the last 3 hours?", "lookback_minutes": 180, "wants_pattern": False, "failures_only": True},
    )]


def test_a_pattern_word_asks_the_log_query_for_a_pattern_over_time() -> None:
    result = plan(question_entry("Show the error pattern of claims-api over the last 2 days"))
    assert result.tool_requests[0].arguments["wants_pattern"] is True  # type: ignore[index]
    assert result.tool_requests[0].arguments["lookback_minutes"] == 2880  # type: ignore[index]


def test_without_a_stated_window_the_log_query_is_left_to_its_own_default() -> None:
    result = plan(question_entry("How many failures on claims-api?"))
    assert "lookback_minutes" not in result.tool_requests[0].arguments  # type: ignore[operator]


def test_the_service_name_may_come_from_the_investigation_context_when_the_question_names_none() -> None:
    digest = "Services: claims-api (aks), payments-db (sql). Evidence E1 on claims-api, E2 on claims-api, E3 on payments-db."
    result = plan(context_entry(digest), question_entry("How many errors were there?"))
    assert result.tool_requests[0].arguments["service_name"] == "claims-api"  # type: ignore[index]


def test_a_count_question_with_no_service_anywhere_cannot_be_planned_and_is_outside_scope() -> None:
    result = plan(question_entry("How many errors were there?"))
    assert result.tool_requests == () and result.text == OUTSIDE_SCOPE_ANSWER


def test_a_question_about_the_system_without_a_specific_tool_searches_the_knowledge_base() -> None:
    result = plan(question_entry("What does the system do for claims?"))
    assert requested(result) == [("search_knowledge", {"query": "What does the system do for claims?"})]


def test_the_knowledge_query_is_cut_to_the_length_the_tool_accepts() -> None:
    long_question = "Explain the system " + "of the claims platform " * 30
    query = plan(question_entry(long_question)).tool_requests[0].arguments["query"]  # type: ignore[index]
    assert len(query) == 300 and long_question.startswith(query)


def test_a_tool_that_is_not_offered_is_never_requested() -> None:
    result = plan(question_entry("Show me evidence E2"), tools=(SEARCH_KNOWLEDGE,))
    assert result.tool_requests == () and result.text == OUTSIDE_SCOPE_ANSWER


def test_a_tool_whose_required_argument_the_planner_cannot_fill_is_not_requested() -> None:
    needs_an_id = tool("get_investigation_timeline", {"investigation_id": {"type": "string"}}, ("investigation_id",))
    assert plan(question_entry("Give me the timeline"), tools=(needs_an_id,)).tool_requests == ()


def test_earlier_conversation_turns_do_not_decide_the_tools() -> None:
    result = plan(history_entry("User: show me the timeline\nKeigan: here it is"), question_entry("What is the capital of France?"))
    assert result.tool_requests == () and result.text == OUTSIDE_SCOPE_ANSWER


# ── The tools of phase 2 ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("question", ["Is claims-api within its SLO?", "How much error budget is left?", "Are we burning through the budget?", "エラーバジェットはどうですか？"])
def test_slo_and_error_budget_words_check_the_slo_status(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("get_slo_status", {})]


def test_an_error_budget_question_is_not_taken_for_a_log_query_about_errors() -> None:
    assert requested(plan(question_entry("How much of the error budget of claims-api is left?"))) == [("get_slo_status", {})]


@pytest.mark.parametrize("question", ["What changed recently?", "Was anything deployed before the spike?", "直近の変更を教えて"])
def test_change_and_deploy_words_check_the_recent_changes(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("list_recent_changes", {})]


@pytest.mark.parametrize(
    ("question", "lookback_hours"),
    [("What changed in the last hour?", 1), ("What changed in the last 90 minutes?", 2), ("What changed in the past 2 days?", 48), ("What changed in the last 100 days?", 720), ("直近 1 時間で何が変わりましたか？ 変更を教えて", 1)],
)
def test_the_window_of_a_change_question_is_rounded_up_to_whole_hours_within_what_the_tool_accepts(question: str, lookback_hours: int) -> None:
    assert requested(plan(question_entry(question))) == [("list_recent_changes", {"lookback_hours": lookback_hours})]


@pytest.mark.parametrize("question", ["Is there a runbook for this?", "How do I fix the connection timeouts?", "対応手順はありますか"])
def test_runbook_and_fix_words_look_for_runbooks_with_the_question_as_the_symptoms(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("find_runbooks", {"symptoms": question})]


@pytest.mark.parametrize("question", ["What does claims-api depend on?", "Show the topology", "Explain this to a new engineer", "新任エンジニア向けに説明して"])
def test_dependency_architecture_and_new_engineer_words_read_the_application_map(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("get_topology", {})]


@pytest.mark.parametrize("question", ["Draft a status update for executives", "経営層向けの状況報告を下書きして"])
def test_a_status_update_for_executives_reads_the_timeline(question: str) -> None:
    assert requested(plan(question_entry(question))) == [("get_investigation_timeline", {})]


def test_the_question_of_the_spec_plans_the_slo_check_then_the_changes() -> None:
    question = "Is claims-api burning its error budget, and did anything change before it started?"
    assert requested(plan(question_entry(question))) == [("get_slo_status", {})]
    second = plan(question_entry(question), *turn(AgentToolRequest("k1", "get_slo_status", {}), spotlighted(json.dumps({"summary": "6 SLOs: 4 healthy, 1 at risk, 1 breached"}))))
    assert requested(second) == [("list_recent_changes", {})]


def test_the_application_comes_from_the_offered_codes_when_the_scope_does_not_bind_one() -> None:
    changes = tool("list_recent_changes", {"application_code": {"type": "string", "enum": ["CLMJP", "PAYAU"]}, "lookback_hours": {"type": "integer"}})
    assert requested(plan(question_entry("What changed for PAYAU in the last hour?"), tools=(changes,))) == [("list_recent_changes", {"application_code": "PAYAU", "lookback_hours": 1})]


def test_the_answer_cites_each_new_tool_and_offers_follow_ups_that_the_planner_can_answer() -> None:
    results = {
        "get_slo_status": "6 SLOs: 4 healthy, 1 at risk, 1 breached", "list_recent_changes": "3 changes in the last 24 hours; newest 2026-01-05 09:42 UTC",
        "find_runbooks": "1 runbook matched", "get_topology": "Application map version 2: 3 components, 2 dependency links",
    }
    questions = {"get_slo_status": "Check the SLO", "list_recent_changes": "What changed?", "find_runbooks": "Is there a runbook?", "get_topology": "Show the topology"}
    for tool_name, summary in results.items():
        request = AgentToolRequest("k1", tool_name, {})
        answer = plan(question_entry(questions[tool_name]), *turn(request, spotlighted(json.dumps({"summary": summary}))))
        assert answer.finish == "answer" and f"{summary} [T1]." in answer.text
        follow_ups = answer.text.split(FOLLOW_UP_MARKER)[1].strip().splitlines()
        assert follow_ups, tool_name
        for follow_up in follow_ups:
            assert plan(question_entry(follow_up)).tool_requests, (tool_name, follow_up)


# ── Outside the scope, limits and failed tools ────────────────────────────────────────────────────


def test_a_question_that_matches_nothing_gets_no_tool_call_and_no_citation() -> None:
    result = plan(question_entry("What is the capital of France?"))
    assert result.finish == "answer" and result.tool_requests == ()
    assert result.text == OUTSIDE_SCOPE_ANSWER and "[T" not in result.text and FOLLOW_UP_MARKER not in result.text


def test_when_no_more_tool_requests_are_accepted_the_answer_uses_what_was_found() -> None:
    result = plan(question_entry("Show me evidence E2 and what the timeline says"), *turn(EVIDENCE_E2, EVIDENCE_RESULT), allow_tool_requests=False)
    assert result.finish == "answer" and result.tool_requests == ()
    assert "[T1]" in result.text and "timeline" not in result.text.split(FOLLOW_UP_MARKER)[0]


def test_when_no_tool_request_is_accepted_and_nothing_was_found_the_answer_says_so_without_a_citation() -> None:
    result = plan(question_entry("Show me evidence E2"), allow_tool_requests=False)
    assert result.finish == "answer" and "could not look anything up" in result.text and "[T" not in result.text


def test_a_refused_call_is_reported_as_not_done_without_a_citation_and_still_uses_up_its_number() -> None:
    refused = turn(EVIDENCE_E2, spotlighted("refused: that evidence does not exist in this investigation"))
    result = plan(question_entry("Show me evidence E2 and the timeline"), *refused, *turn(TIMELINE_CALL, TIMELINE_RESULT))
    lines = result.text.split(FOLLOW_UP_MARKER)[0].strip().splitlines()
    assert lines[0] == "I could not check get_evidence: that evidence does not exist in this investigation."
    assert lines[1] == "7 timeline events; newest 09:42 UTC [T2]."


def test_a_skipped_call_does_not_use_up_a_citation_number() -> None:
    skipped = turn(EVIDENCE_E2, spotlighted("skipped: the tool call limit was reached"))
    result = plan(question_entry("Show me evidence E2 and the timeline"), *skipped, *turn(TIMELINE_CALL, TIMELINE_RESULT))
    assert "7 timeline events; newest 09:42 UTC [T1]." in result.text


def test_a_failure_in_the_words_of_the_tool_registry_names_the_tool_before_its_status_and_is_still_a_call_that_gave_no_data() -> None:
    failed = turn(EVIDENCE_E2, spotlighted('get_evidence failed (not_found): "Opened evidence": that evidence item was not found.'))
    skipped = turn(TIMELINE_CALL, spotlighted("get_investigation_timeline skipped (tool_limit_reached): the limit of tool calls for this answer is used up"))
    result = plan(question_entry("Show me evidence E2 and the timeline"), *failed, *skipped)
    lines = result.text.split(FOLLOW_UP_MARKER)[0].strip().splitlines()
    assert lines[0] == 'I could not check get_evidence: "Opened evidence": that evidence item was not found.'
    assert lines[1].startswith("I could not check get_investigation_timeline") and "[T" not in result.text


def test_a_result_that_is_plain_text_is_summarised_by_its_first_line() -> None:
    result = plan(question_entry("Show me evidence E2"), *turn(EVIDENCE_E2, spotlighted("E2: spike on claims-api\nmore detail below")))
    assert result.text.splitlines()[0] == "E2: spike on claims-api [T1] [E2]."


# ── Follow-up questions ──────────────────────────────────────────────────────────────────────────


def test_follow_up_questions_follow_the_marker_one_per_line_up_to_the_configured_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_follow_up_question_limit", 2)
    result = plan(question_entry("Show me evidence E2 and what the timeline says before it"), *turn(EVIDENCE_E2, EVIDENCE_RESULT), *turn(TIMELINE_CALL, TIMELINE_RESULT))
    answer, follow_ups = result.text.split(FOLLOW_UP_MARKER)
    assert answer.strip() and len([line for line in follow_ups.strip().splitlines() if line.strip()]) == 2


def test_with_a_limit_of_zero_no_follow_up_section_is_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_follow_up_question_limit", 0)
    result = plan(question_entry("Show me evidence E2"), *turn(EVIDENCE_E2, EVIDENCE_RESULT))
    assert FOLLOW_UP_MARKER not in result.text


# ── Wiring ───────────────────────────────────────────────────────────────────────────────────────


def test_the_planner_is_registered_for_both_scopes() -> None:
    assert llm_gateway._mock_agent_planners[AskKeiganFeature.GLOBAL] is plan_agent_turn
    assert llm_gateway._mock_agent_planners[AskKeiganFeature.INVESTIGATION] is plan_agent_turn
    assert {AskKeiganFeature.GLOBAL.value, AskKeiganFeature.INVESTIGATION.value} == {"ask_keigan_global", "ask_keigan_investigation"}


async def test_through_the_mock_gateway_the_example_question_takes_two_tool_turns_and_a_streamed_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_provider", LlmProviderName.MOCK)
    gateway = LlmGateway(get_settings())
    transcript: list[AgentTranscriptEntry] = [question_entry("Show me evidence E2 and what the timeline says before it")]
    results: list[AgentTurnResult] = []
    for result_text in (EVIDENCE_RESULT, TIMELINE_RESULT, None):
        turn_result = await gateway.run_agent_turn(
            feature_name=AskKeiganFeature.INVESTIGATION, model_tier=ModelTier.DEEP, system_prompt="You are Keigan.", transcript=transcript, tools=PHASE_ONE_TOOLS,
            allow_tool_requests=True, usage_context=LlmUsageContext(enforce_token_budget=False),
        )
        results.append(turn_result)
        if result_text is not None:
            request = turn_result.tool_requests[0]
            transcript.extend(turn(request, result_text))
    assert [result.finish for result in results] == ["tool_requests", "tool_requests", "answer"]
    assert [result.tool_requests[0].tool_name for result in results[:2]] == ["get_evidence", "get_investigation_timeline"]
    assert "[T1]" in results[2].text and "[T2]" in results[2].text


# ── The global tools (tools 9 to 20): each one is planned from a plain question, in English and where the first eight are ──────────
_LOOKBACK = {"type": "integer", "minimum": 1, "maximum": 720}


_CODE_ENUM = {"type": "string", "enum": ["CLMJP", "PAYAU"]}
GET_INVESTIGATION = tool("get_investigation", {"investigation_id": {"type": "string"}}, ("investigation_id",))
LIST_INVESTIGATIONS = tool("list_investigations", {"application_codes": {"type": "array"}, "statuses": {"type": "array"}, "incident_id": {"type": "string"}, "lookback_hours": _LOOKBACK})
LIST_INCIDENTS = tool("list_incidents", {"statuses": {"type": "array"}, "priorities": {"type": "array"}, "sources": {"type": "array"}, "lookback_hours": _LOOKBACK, "text": {"type": "string"}})
GET_INCIDENT = tool("get_incident", {"incident_reference": {"type": "string"}}, ("incident_reference",))
LIST_ALERT_GROUPS = tool("list_alert_groups", {"statuses": {"type": "array"}, "lookback_hours": _LOOKBACK, "minimum_priority_score": {"type": "number"}})
GET_ALERT_GROUP = tool("get_alert_group", {"alert_group_id": {"type": "string"}}, ("alert_group_id",))
GET_ALERT_NOISE_SUMMARY = tool("get_alert_noise_summary", {"application_codes": {"type": "array"}, "lookback_hours": _LOOKBACK})
GET_SLO_HISTORY = tool("get_slo_history", {"slo_id": {"type": "string"}, "lookback_hours": _LOOKBACK}, ("slo_id",))
LIST_PREDICTIVE_SIGNALS = tool("list_predictive_signals", {"application_codes": {"type": "array"}, "severities": {"type": "array"}, "statuses": {"type": "array"}})
GET_HEALTH_SCORE = tool("get_health_score", {"application_code": _CODE_ENUM, "days": {"type": "integer", "minimum": 7, "maximum": 90}}, ("application_code",))
LIST_TEAM_MEMBERS = tool("list_team_members", {"application_code": _CODE_ENUM, "roles": {"type": "array"}}, ("application_code",))
GET_RELIABILITY_METRICS = tool("get_reliability_metrics", {"application_codes": {"type": "array"}, "lookback_hours": _LOOKBACK})
FIND_SIMILAR_INCIDENTS = tool("find_similar_incidents", {"investigation_id": {"type": "string"}, "incident_id": {"type": "string"}, "text": {"type": "string"}, "application_code": _CODE_ENUM})
GLOBAL_TOOLS = (*INVESTIGATION_TOOLS, FIND_SIMILAR_INCIDENTS, GET_INVESTIGATION, LIST_INVESTIGATIONS, LIST_INCIDENTS, GET_INCIDENT, LIST_ALERT_GROUPS, GET_ALERT_GROUP, GET_ALERT_NOISE_SUMMARY, GET_SLO_HISTORY,
                LIST_PREDICTIVE_SIGNALS, GET_HEALTH_SCORE, LIST_TEAM_MEMBERS, GET_RELIABILITY_METRICS)
SAMPLE_ID = "6f1e2c3a-9b1d-4c2e-8f10-3a5b7c9d1e2f"


@pytest.mark.parametrize(("question", "expected"), [
    (f"Show investigation {SAMPLE_ID}", ("get_investigation", {"investigation_id": SAMPLE_ID})),
    ("List the investigations of the last 3 days", ("list_investigations", {"lookback_hours": 72})),
    ("Which incidents are open?", ("list_incidents", {})),
    ("Open INC0012345 and tell me its priority", ("get_incident", {"incident_reference": "INC0012345"})),
    ("Which alert groups fired in the last 2 hours?", ("list_alert_groups", {"lookback_hours": 2})),
    (f"Open alert group {SAMPLE_ID}", ("get_alert_group", {"alert_group_id": SAMPLE_ID})),
    ("How much alert noise did we get in the last 7 days?", ("get_alert_noise_summary", {"lookback_hours": 168})),
    (f"Show the history of SLO {SAMPLE_ID}", ("get_slo_history", {"slo_id": SAMPLE_ID})),
    ("What predictive signals are open?", ("list_predictive_signals", {})),
    ("What is the health score of PAYAU?", ("get_health_score", {"application_code": "PAYAU"})),
    ("Who is on the team for CLMJP?", ("list_team_members", {"application_code": "CLMJP"})),
    ("What are the reliability metrics for the last 30 days?", ("get_reliability_metrics", {"lookback_hours": 720})),
    (f"Have we seen investigation {SAMPLE_ID} before?", ("find_similar_incidents", {"investigation_id": SAMPLE_ID})),
    ("インシデント一覧を見せて", ("list_incidents", {})),
    ("CLMJP の健全性スコアは？", ("get_health_score", {"application_code": "CLMJP"})),
    ("信頼性の指標を教えて", ("get_reliability_metrics", {})),
])
def test_each_global_tool_is_planned_from_a_plain_question(question: str, expected: tuple[str, dict[str, object]]) -> None:
    assert requested(plan(question_entry(question), tools=GLOBAL_TOOLS))[0] == expected


def test_a_history_question_plans_the_history_before_the_status() -> None:
    result = plan(question_entry(f"Show the history of SLO {SAMPLE_ID}"), tools=GLOBAL_TOOLS)
    assert [name for name, _ in requested(result)] == ["get_slo_history"]


def test_the_worked_example_of_the_spec_plans_the_slo_status_and_the_recent_changes_in_that_order() -> None:
    question = "Is claims-api burning its error budget, and did anything change before it started?"
    result = plan(question_entry(question), tools=GLOBAL_TOOLS)
    assert requested(result) == [("get_slo_status", {})]
    second = plan(question_entry(question), *turn(AgentToolRequest("k1", "get_slo_status", {}), spotlighted(json.dumps({"summary": "6 SLOs"}))), tools=GLOBAL_TOOLS)
    assert requested(second) == [("list_recent_changes", {})]


def test_a_global_tool_that_needs_an_identifier_is_not_planned_without_one() -> None:
    assert requested(plan(question_entry("Show me the investigation"), tools=GLOBAL_TOOLS)) == []

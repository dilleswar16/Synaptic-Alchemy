"""keigan/services/ask_keigan_conformance_checks.py: a run is judged against its scenario the same way in every mode (spec 23, 4.6.6)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from keigan.entities.status_values import ChatRunStepStatus
from keigan.services.ask_keigan_conformance_checks import ObservedCall, ObservedRun, ObservedTurn, evaluate
from keigan.services.ask_keigan_conformance_scenarios import Scenario


def call(tool: str = "get_slo_status", status: ChatRunStepStatus = ChatRunStepStatus.SUCCEEDED, citation: str | None = "T1", outcome_code: str | None = None, **arguments: Any) -> ObservedCall:
    return ObservedCall(tool, arguments, status, outcome_code, citation, "a result")


def observed(**overrides: Any) -> ObservedRun:
    values: dict[str, Any] = {
        "run_status": "completed", "stop_reason": "answered", "error_code": None, "calls": (call(),), "answer_text": "The SLOs are fine [T1].", "citation_codes": ("T1",), "is_refusal": False,
        "applications_read": ("CLMJP",), "answer_text_event_count": 3, "turns": (ObservedTurn(100, 20, False, 1, 0), ObservedTurn(150, 30, False, 0, 3)), "duration_milliseconds": 10,
        "tool_calling_mode": "native", "model_name": "m",
    }
    return ObservedRun(**{**values, **overrides})


def scenario(**expect: Any) -> Scenario:
    return Scenario.model_validate({"id": "C99", "title": "t", "scope": "global", "user": "u", "question": "q", "runs_in": ["mock"], "expect": expect})


def test_a_run_that_matches_a_scenario_with_no_expectations_beyond_the_defaults_passes() -> None:
    assert evaluate(scenario(), observed()) == []


def test_the_status_the_stop_reason_and_the_error_code_are_compared() -> None:
    failures = evaluate(scenario(), observed(run_status="failed", stop_reason="failed", error_code="ai_timeout"))
    assert len(failures) == 3 and "failed, expected completed" in failures[0]
    assert evaluate(scenario(run_status="failed", stop_reason="failed", error_code="ai_timeout"), observed(run_status="failed", stop_reason="failed", error_code="ai_timeout")) == []


def test_calls_in_order_must_match_tool_arguments_status_and_outcome() -> None:
    expected = scenario(calls=[{"tool": "get_slo_status", "arguments": {"application_codes": ["CLMJP"]}, "status": "succeeded"}])
    assert evaluate(expected, observed(calls=(call(application_codes=["CLMJP"], extra=1),))) == []  # extra arguments are fine: the expected ones must be there
    assert evaluate(expected, observed(calls=(call(application_codes=["PAYAU"]),)))
    assert evaluate(expected, observed(calls=(call(application_codes=["CLMJP"], status=ChatRunStepStatus.FAILED),)))
    assert evaluate(expected, observed(calls=(call(application_codes=["CLMJP"]), call("list_incidents"))))
    assert evaluate(scenario(calls=[{"tool": "x", "outcome_code": "invalid_arguments"}]), observed(calls=(call("x", ChatRunStepStatus.REFUSED),)))


def test_calls_in_any_order_need_each_expected_call_and_no_call_to_another_tool() -> None:
    expected = scenario(calls=[{"tool": "get_slo_status"}], call_order="any")
    assert evaluate(expected, observed(calls=(call(), call(citation="T2")), citation_codes=("T1", "T2"))) == []
    assert evaluate(expected, observed(calls=(call("list_incidents"),)))
    assert evaluate(expected, observed(calls=(call(), call("list_incidents", citation="T2"))))


def test_no_calls_expected_means_none_were_made() -> None:
    assert evaluate(scenario(calls=[], answer={"refusal": True}), observed(calls=(), is_refusal=True, citation_codes=())) == []
    assert evaluate(scenario(calls=[]), observed())


def test_a_forbidden_tool_and_a_missing_application_are_reported() -> None:
    assert evaluate(scenario(forbidden_tools=["get_slo_status"]), observed())
    assert evaluate(scenario(reads_applications=["CLMJP", "CHAD"]), observed()) == ["the answer did not read CHAD"]


def test_forbidden_text_is_looked_for_in_results_arguments_and_the_answer_ignoring_case() -> None:
    assert evaluate(scenario(forbidden_text=["hanako"]), observed(answer_text="Ask Hanako [T1]."))
    assert evaluate(scenario(forbidden_text=["secret"]), observed(calls=(replace(call(), result_text="the Secret value"),)))
    assert evaluate(scenario(forbidden_text=["CHAD"]), observed(calls=(call(application_codes=["CHAD"]),)))
    assert evaluate(scenario(forbidden_text=["CHAD"]), observed()) == []


def test_forbidden_arguments_look_only_at_the_arguments() -> None:
    assert evaluate(scenario(forbidden_in_arguments=["CHAD"]), observed(answer_text="CHAD is not readable [T1]")) == []
    assert evaluate(scenario(forbidden_in_arguments=["CHAD"]), observed(calls=(call(application_codes=["CHAD"]),)))


def test_citation_expectations() -> None:
    assert evaluate(scenario(answer={"cites": True}), observed(citation_codes=())) == ["the answer cites nothing"]
    assert evaluate(scenario(answer={"cites": False}), observed(answer_text="Nothing [T1]"))
    assert evaluate(scenario(answer={"cites_any_of": ["T9", "E2"]}), observed())
    assert evaluate(scenario(answer={"cites_any_of": ["T1"]}), observed()) == []
    failures = evaluate(scenario(answer={"cites_each_succeeded_call": True}), observed(calls=(call(), call(citation="T2")), citation_codes=("T1",)))
    assert failures == ["the answer does not cite T2 (get_slo_status)"]
    assert evaluate(scenario(answer={"cites_each_succeeded_call": True}), observed(calls=(call(status=ChatRunStepStatus.FAILED, citation="T1"),), citation_codes=())) == []


def test_refusal_and_text_patterns_and_streaming() -> None:
    assert evaluate(scenario(answer={"refusal": True}), observed())
    assert evaluate(scenario(answer={"matches": ["fine"]}), observed()) == []
    assert evaluate(scenario(answer={"matches": ["COULD NOT"]}), observed())
    assert evaluate(scenario(answer={"not_matches": ["fine"]}), observed())
    assert evaluate(scenario(answer={"streams_text": True}), observed(answer_text_event_count=0))


def test_a_run_whose_every_turn_has_no_token_counts_fails_but_estimates_count() -> None:
    assert evaluate(scenario(), observed(turns=(ObservedTurn(0, 0, True, 0, 0),))) == ["no token counts, reported or estimated"]
    assert evaluate(scenario(), observed(turns=(ObservedTurn(30, 5, True, 0, 0),))) == []
    assert evaluate(scenario(run_status="failed", stop_reason="failed", error_code="x"), observed(run_status="failed", stop_reason="failed", error_code="x", turns=())) == []

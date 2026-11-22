"""keigan/services/ask_keigan_conformance_report.py: the conformance report and its writer (spec 23, 4.6.6). Offline: the live script was never run against a real model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from keigan.entities.status_values import ChatRunStepStatus
from keigan.services.ask_keigan_conformance_checks import ObservedCall, ObservedRun, ObservedTurn
from keigan.services.ask_keigan_conformance_report import (
    ConformanceReport, observe_capabilities, report_as_json, scenario_report, unrunnable_scenario_report, write_report,
)


def run(turns: tuple[ObservedTurn, ...], calls: tuple[ObservedCall, ...] = ()) -> ObservedRun:
    return ObservedRun("completed", "answered", None, calls, "Answer [T1].", ("T1",), False, ("CLMJP",), 2, turns, 250, "native", "model-x")


def test_a_scenario_report_lists_the_tools_called_the_tokens_and_the_latency() -> None:
    call = ObservedCall("get_evidence", {"evidence_code": "E2"}, ChatRunStepStatus.REFUSED, "invalid_arguments", "T1", "text")
    report = scenario_report("C9", "Refused arguments", "native", ["a failure"], run((ObservedTurn(100, 20, False, 1, 0), ObservedTurn(50, 10, False, 0, 3)), (call,)))
    assert (report.passed, report.failures, report.input_token_count, report.output_token_count, report.duration_milliseconds) == (False, ["a failure"], 150, 30, 250)
    assert report.tools_called == [{"tool": "get_evidence", "arguments": {"evidence_code": "E2"}, "status": "refused", "outcomeCode": "invalid_arguments", "citation": "T1"}]
    assert scenario_report("C1", "t", "native", [], run(())).passed is True


def test_the_observations_say_what_the_runs_showed_of_the_model() -> None:
    nothing = observe_capabilities([run((ObservedTurn(10, 2, True, 1, 1),))])
    assert (nothing.parallel_tool_calls_seen, nothing.stream_usage_reported, nothing.streamed_text_seen, nothing.token_counts_estimated_seen) == (False, False, False, True)
    seen = observe_capabilities([run((ObservedTurn(10, 2, True, 1, 0),)), run((ObservedTurn(10, 2, False, 2, 3),))])
    assert (seen.parallel_tool_calls_seen, seen.stream_usage_reported, seen.streamed_text_seen, seen.token_counts_estimated_seen) == (True, True, True, True)


def test_a_scenario_that_could_not_be_run_is_a_failure_with_the_reason() -> None:
    report = unrunnable_scenario_report("C6", "t", "live", "LookupError: no CLMJP")
    assert report.passed is False and report.failures == ["the scenario could not be run: LookupError: no CLMJP"] and report.tools_called == []


def test_the_report_passes_only_when_it_has_scenarios_and_every_one_passed() -> None:
    report = ConformanceReport("p", "m", {})
    assert report.passed is False
    report.scenarios += [scenario_report("C1", "t", "native", [], run(())), scenario_report("C2", "t", "native", ["x"], run(()))]
    assert report.passed is False
    report.scenarios.pop()
    assert report.passed is True


def test_the_written_report_has_camel_case_keys_the_configured_capabilities_and_a_summary(tmp_path: Path) -> None:
    report = ConformanceReport(
        "openai_compatible", "gpt-x", {"tool_calling": "native", "parallel_tool_calls": False}, tool_calling_mode="native", generated_at=datetime(2026, 11, 22, 10, 0, tzinfo=UTC),
    )
    report.scenarios.append(scenario_report("C1", "One evidence item", "live", [], run((ObservedTurn(100, 20, False, 2, 3),), (ObservedCall("get_evidence", {"evidence_code": "E2"}, ChatRunStepStatus.SUCCEEDED, None, "T1", "t"),))))
    report.observations = observe_capabilities([run((ObservedTurn(100, 20, False, 2, 3),))])
    target = tmp_path / "reports" / "out.json"  # the folder does not exist yet
    write_report(report, target)
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == report_as_json(report)
    assert written["generatedAt"] == "2026-11-22T10:00:00+00:00" and written["passed"] is True and written["providerName"] == "openai_compatible" and written["modelName"] == "gpt-x"
    assert written["configuredCapabilities"] == {"tool_calling": "native", "parallel_tool_calls": False}
    assert written["observations"] == {"parallelToolCallsSeen": True, "streamUsageReported": True, "streamedTextSeen": True, "tokenCountsEstimatedSeen": False}
    assert written["summary"] == {"scenarioCount": 1, "passedCount": 1}
    scenario = written["scenarios"][0]
    assert scenario["scenarioId"] == "C1" and scenario["inputTokenCount"] == 100 and scenario["durationMilliseconds"] == 250 and scenario["toolsCalled"][0]["arguments"] == {"evidence_code": "E2"}

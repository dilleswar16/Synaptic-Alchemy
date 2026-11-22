"""The report of a conformance run: per scenario pass or fail, the tools called, tokens and latency, and what the run showed of the model's capabilities (spec 23, 4.6.6).

The capability observations are what an admin compares with the resolved capabilities and, where they differ, copies into ``LLM_MODEL_CAPABILITIES_JSON``. An observation of
"seen" is evidence that the model can; the absence of it proves nothing (the scenarios may simply not have asked for it).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from keigan.services.ask_keigan_conformance_checks import ObservedRun


@dataclass(frozen=True)
class ScenarioReport:
    scenario_id: str
    title: str
    mode: str
    passed: bool
    failures: list[str]
    tools_called: list[dict[str, Any]]
    input_token_count: int
    output_token_count: int
    duration_milliseconds: int
    answer_text: str | None


@dataclass(frozen=True)
class CapabilityObservations:
    parallel_tool_calls_seen: bool
    stream_usage_reported: bool
    streamed_text_seen: bool
    token_counts_estimated_seen: bool


@dataclass
class ConformanceReport:
    provider_name: str
    model_name: str
    configured_capabilities: dict[str, Any]
    tool_calling_mode: str | None = None  # what the runs recorded; None when no scenario ran
    scenarios: list[ScenarioReport] = field(default_factory=list)
    observations: CapabilityObservations = CapabilityObservations(False, False, False, False)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed(self) -> bool:
        return bool(self.scenarios) and all(scenario.passed for scenario in self.scenarios)


def scenario_report(scenario_id: str, title: str, mode: str, failures: list[str], run: ObservedRun) -> ScenarioReport:
    return ScenarioReport(
        scenario_id=scenario_id, title=title, mode=mode, passed=not failures, failures=failures,
        tools_called=[{"tool": call.tool_name, "arguments": call.arguments, "status": call.status.value, "outcomeCode": call.outcome_code, "citation": call.citation_code} for call in run.calls],
        input_token_count=run.input_token_count, output_token_count=run.output_token_count, duration_milliseconds=run.duration_milliseconds, answer_text=run.answer_text,
    )


def unrunnable_scenario_report(scenario_id: str, title: str, mode: str, problem: str) -> ScenarioReport:
    """A scenario that could not even be set up (an unknown user, a fixture that needs data the database lacks): reported as failed, so the rest still run."""
    return ScenarioReport(scenario_id, title, mode, False, [f"the scenario could not be run: {problem}"], [], 0, 0, 0, None)


def observe_capabilities(runs: list[ObservedRun]) -> CapabilityObservations:
    turns = [turn for run in runs for turn in run.turns]
    return CapabilityObservations(
        parallel_tool_calls_seen=any(turn.tool_request_count >= 2 for turn in turns),
        stream_usage_reported=any(not turn.token_counts_estimated for turn in turns),
        streamed_text_seen=any(turn.text_chunk_count >= 2 for turn in turns),
        token_counts_estimated_seen=any(turn.token_counts_estimated for turn in turns),
    )


def report_as_json(report: ConformanceReport) -> dict[str, Any]:
    """The report as written to the file: camelCase keys, tool arguments keep the tools' own names."""
    return {
        "generatedAt": report.generated_at.isoformat(), "passed": report.passed, "providerName": report.provider_name, "modelName": report.model_name,
        "toolCallingMode": report.tool_calling_mode, "configuredCapabilities": report.configured_capabilities,
        "observations": _camel(asdict(report.observations)),
        "summary": {"scenarioCount": len(report.scenarios), "passedCount": sum(scenario.passed for scenario in report.scenarios)},
        "scenarios": [_camel(asdict(scenario)) for scenario in report.scenarios],
    }


def write_report(report: ConformanceReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_as_json(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _camel(values: dict[str, Any]) -> dict[str, Any]:
    """The top-level keys in camelCase (the keys inside a tool's arguments are the tool's own and stay)."""
    return {_camel_case(name): value for name, value in values.items()}


def _camel_case(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)

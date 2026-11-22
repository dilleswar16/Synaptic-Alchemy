"""Judges what an Ask Keigan run did against what its conformance scenario expects (spec 23, 4.6.6). Pure: it reads an ``ObservedRun`` and returns the failures in words.

The same judgement is made of every kind of model (the offline planner, a scripted model in either tool mode, a real provider), so a scenario that passes for all of them
says the models behave the same through the gateway.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from keigan.entities.status_values import ChatRunStepStatus
from keigan.services.ask_keigan_conformance_scenarios import AnswerExpectation, ExpectedCall, Scenario


@dataclass(frozen=True)
class ObservedCall:
    tool_name: str
    arguments: dict[str, Any]  # the effective arguments: what the tool was run with
    status: ChatRunStepStatus
    outcome_code: str | None
    citation_code: str | None
    result_text: str  # everything the call produced that the model or the person could read: output, model view, outcome message


@dataclass(frozen=True)
class ObservedTurn:
    input_token_count: int
    output_token_count: int
    token_counts_estimated: bool
    tool_request_count: int
    text_chunk_count: int


@dataclass(frozen=True)
class ObservedRun:
    run_status: str
    stop_reason: str
    error_code: str | None
    calls: tuple[ObservedCall, ...]
    answer_text: str | None
    citation_codes: tuple[str, ...]
    is_refusal: bool
    applications_read: tuple[str, ...]  # application codes
    answer_text_event_count: int
    turns: tuple[ObservedTurn, ...]
    duration_milliseconds: int
    tool_calling_mode: str
    model_name: str

    @property
    def input_token_count(self) -> int:
        return sum(turn.input_token_count for turn in self.turns)

    @property
    def output_token_count(self) -> int:
        return sum(turn.output_token_count for turn in self.turns)


def evaluate(scenario: Scenario, run: ObservedRun) -> list[str]:
    """The ways ``run`` fails ``scenario`` (an empty list: it passes)."""
    expected = scenario.expect
    failures: list[str] = []
    if run.run_status != expected.run_status:
        failures.append(f"the run ended {run.run_status}, expected {expected.run_status}")
    if run.stop_reason != expected.stop_reason:
        failures.append(f"the stop reason was {run.stop_reason}, expected {expected.stop_reason}")
    if run.error_code != expected.error_code:
        failures.append(f"the error code was {run.error_code}, expected {expected.error_code}")
    failures += _call_failures(expected.calls, expected.call_order, run.calls) if expected.calls is not None else []
    failures += [f"{tool} was called but must not be" for tool in expected.forbidden_tools if any(call.tool_name == tool for call in run.calls)]
    failures += [f"the answer did not read {code}" for code in expected.reads_applications if code not in run.applications_read]
    failures += _forbidden_text_failures(expected.forbidden_text, run)
    failures += [f"a call was made with '{text}' in its arguments" for text in expected.forbidden_in_arguments if any(text.lower() in str(call.arguments).lower() for call in run.calls)]
    failures += _answer_failures(expected.answer, run)
    if run.turns and not any(turn.input_token_count or turn.output_token_count for turn in run.turns):
        failures.append("no token counts, reported or estimated")
    return failures


def _matches(expected: ExpectedCall, call: ObservedCall) -> bool:
    return (
        call.tool_name == expected.tool
        and all(call.arguments.get(name) == value for name, value in expected.arguments.items())
        and (expected.status is None or call.status == expected.status)
        and (expected.outcome_code is None or call.outcome_code == expected.outcome_code)
    )


def _describe(call: ObservedCall) -> str:
    return f"{call.tool_name}({call.status.value}{f'/{call.outcome_code}' if call.outcome_code else ''})"


def _call_failures(expected_calls: list[ExpectedCall], order: str, calls: tuple[ObservedCall, ...]) -> list[str]:
    observed = ", ".join(_describe(call) for call in calls) or "none"
    if order == "exact":
        if len(calls) == len(expected_calls) and all(_matches(expected, call) for expected, call in zip(expected_calls, calls, strict=True)):
            return []
        return [f"the calls were [{observed}], expected [{', '.join(expected.tool for expected in expected_calls)}] in this order with the stated arguments and outcomes"]
    failures = [f"no call matched {expected.tool} {expected.arguments}" for expected in expected_calls if not any(_matches(expected, call) for call in calls)]
    allowed_tools = {expected.tool for expected in expected_calls}
    return failures + [f"{call.tool_name} was called but is not among the expected tools" for call in calls if call.tool_name not in allowed_tools]


def _readable_text_of(run: ObservedRun) -> Iterable[str]:
    for call in run.calls:
        yield call.result_text
        yield str(call.arguments)
    yield run.answer_text or ""


def _forbidden_text_failures(forbidden_texts: list[str], run: ObservedRun) -> list[str]:
    readable = "\n".join(_readable_text_of(run)).lower()
    return [f"'{text}' appears in the run's results or answer" for text in forbidden_texts if text.lower() in readable]


def _answer_failures(expected: AnswerExpectation, run: ObservedRun) -> list[str]:
    failures: list[str] = []
    answer_text = run.answer_text or ""
    if expected.cites is True and not run.citation_codes:
        failures.append("the answer cites nothing")
    if expected.cites is False and (run.citation_codes or re.search(r"\[[A-Z]\d{1,3}\]", answer_text)):
        failures.append("the answer cites a source but must not")
    if expected.cites_any_of and not set(expected.cites_any_of) & set(run.citation_codes):
        failures.append(f"the answer cites {list(run.citation_codes)}, none of {expected.cites_any_of}")
    if expected.cites_each_succeeded_call:
        failures += [f"the answer does not cite {call.citation_code} ({call.tool_name})" for call in run.calls if call.status is ChatRunStepStatus.SUCCEEDED and call.citation_code not in run.citation_codes]
    if expected.refusal is not None and run.is_refusal != expected.refusal:
        failures.append(f"the answer {'is' if run.is_refusal else 'is not'} a refusal, expected the opposite")
    failures += [f"the answer does not match /{pattern}/" for pattern in expected.matches if not re.search(pattern, answer_text, re.IGNORECASE)]
    failures += [f"the answer matches /{pattern}/ but must not" for pattern in expected.not_matches if re.search(pattern, answer_text, re.IGNORECASE)]
    if expected.streams_text and run.answer_text_event_count == 0:
        failures.append("no answer.text event reached the stream")
    return failures

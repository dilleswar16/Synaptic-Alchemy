"""The Ask Keigan conformance scenarios: questions with what a model must do with the tools and what its answer must look like (spec 23, 4.6.6).

The file ``resources/evaluation/ask_keigan_conformance.yaml`` holds them in a shape the evaluation harness can reuse: a question, who asks, the named fixture that
seeds the data, settings to lower for the scenario, the expectations, and ``offline_script`` (what a model is recorded to do, replayed offline in native and prompted
mode; the offline mock model plans from the question itself and ignores it). A scenario says in which ``runs_in`` it makes sense: a scripted failure cannot be asked of
a real model. Text in ``offline_script`` and ``expect`` may use ``${name}`` placeholders, filled from the fixture's variables when the scenario is run.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from string import Template
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from keigan.config.settings import RESOURCES_DIRECTORY, Settings
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepStatus

SCENARIO_FILE = RESOURCES_DIRECTORY / "evaluation" / "ask_keigan_conformance.yaml"


class ScenarioMode(StrEnum):
    """How the model of a run is provided: the offline planner (``mock``), a scripted model through native tool calling or through the prompted-JSON protocol, or the configured real provider."""

    MOCK = "mock"
    NATIVE = "native"
    PROMPTED = "prompted"
    LIVE = "live"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScriptedRequest(_Strict):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScriptedTurn(_Strict):
    """One recorded model turn: tool requests, an answer, a reply outside the prompted format (``raw``), or the model endpoint failing with an HTTP status."""

    tool_requests: list[ScriptedRequest] | None = None
    answer: str | None = None
    follow_ups: list[str] = Field(default_factory=list)
    raw: str | None = None
    fails_with_status: int | None = None

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Self:
        kinds = [self.tool_requests, self.answer, self.raw, self.fails_with_status]
        if sum(kind is not None for kind in kinds) != 1:
            raise ValueError("a scripted turn has exactly one of tool_requests, answer, raw, fails_with_status")
        return self


class ExpectedCall(_Strict):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)  # every key must be among the effective arguments with this value
    status: ChatRunStepStatus | None = None
    outcome_code: str | None = None


class AnswerExpectation(_Strict):
    cites: bool | None = None  # True: at least one citation survives; False: none
    cites_any_of: list[str] = Field(default_factory=list)
    cites_each_succeeded_call: bool = False
    refusal: bool | None = None
    matches: list[str] = Field(default_factory=list)  # regular expressions, case-insensitive
    not_matches: list[str] = Field(default_factory=list)
    streams_text: bool = False  # at least one answer.text event reached the stream


class Expectations(_Strict):
    run_status: ChatAnswerRunStatus = ChatAnswerRunStatus.COMPLETED
    stop_reason: ChatAnswerStopReason = ChatAnswerStopReason.ANSWERED
    error_code: str | None = None
    calls: list[ExpectedCall] | None = None  # None: the calls are not checked
    call_order: Literal["exact", "any"] = "exact"  # any: each expected call is matched by some call, and no call is made to another tool
    forbidden_tools: list[str] = Field(default_factory=list)
    reads_applications: list[str] = Field(default_factory=list)  # codes the answer's tool calls must have read
    forbidden_text: list[str] = Field(default_factory=list)  # in no tool result, effective argument or answer (names of people, data of applications the person cannot read)
    forbidden_in_arguments: list[str] = Field(default_factory=list)  # in no effective argument of any call (a code the schema does not offer)
    answer: AnswerExpectation = AnswerExpectation()


class Scenario(_Strict):
    id: str = Field(pattern=r"^C\d+$")
    title: str
    scope: Literal["global", "investigation"]
    user: str
    question: str
    fixture: str | None = None
    limits: dict[str, int] = Field(default_factory=dict)  # Settings fields lowered for this scenario
    runs_in: list[ScenarioMode]
    offline_script: list[ScriptedTurn] = Field(default_factory=list)
    expect: Expectations

    @model_validator(mode="after")
    def _is_runnable_where_it_says(self) -> Self:
        scripted = {ScenarioMode.NATIVE, ScenarioMode.PROMPTED} & set(self.runs_in)
        if scripted and not self.offline_script:
            raise ValueError(f"{self.id} runs in {sorted(scripted)} and needs an offline_script")
        if unknown := sorted(set(self.limits) - set(Settings.model_fields)):
            raise ValueError(f"{self.id} lowers settings that do not exist: {unknown}")
        return self

    def resolved(self, variables: dict[str, str]) -> Scenario:
        """The scenario with ``${name}`` placeholders replaced by the fixture's values."""
        return Scenario.model_validate(_fill(self.model_dump(mode="json"), variables))


def _fill(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return Template(value).safe_substitute(variables)
    if isinstance(value, list):
        return [_fill(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _fill(item, variables) for key, item in value.items()}
    return value


@lru_cache
def load_scenarios() -> tuple[Scenario, ...]:
    document = yaml.safe_load(SCENARIO_FILE.read_text(encoding="utf-8"))
    scenarios = tuple(Scenario.model_validate(entry) for entry in document["scenarios"])
    if len({scenario.id for scenario in scenarios}) != len(scenarios):
        raise ValueError(f"{SCENARIO_FILE.name} has a duplicate scenario id")
    return scenarios


def scenarios_for(mode: ScenarioMode, only: str | None = None) -> list[Scenario]:
    return [scenario for scenario in load_scenarios() if mode in scenario.runs_in and (only is None or scenario.id == only)]

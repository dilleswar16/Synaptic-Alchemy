"""The Ask Keigan answer API (DTOs) and the TypeScript types of ``askKeiganApi.ts`` must name the same fields and the same values (spec 23, 7.2)."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel

from keigan.ai.tool_registry import AskKeiganScope, ToolPresentation, ToolProgressStage
from keigan.dtos.ask_keigan_dtos import (
    AnswerRequest, AnswerRunView, AnswerView, CitationView, ProblemSummaryView, RecordReferenceView, RunStepToolTargetView, RunStepToolView, RunStepView, StepOutputView,
)
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus, ToolCallingMode
from support.ask_keigan_typescript import inline_object_fields, interface_fields, typescript_block, typescript_union

FRONTEND_SOURCE = Path(__file__).resolve().parents[3] / "frontend" / "src"


def wire_fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_json_schema(by_alias=True)["properties"])


@pytest.mark.parametrize(("dto", "interface_name"), [
    (AnswerRunView, "AnswerRunView"), (RunStepView, "RunStepView"), (RunStepToolView, "RunStepToolView"), (CitationView, "Citation"), (AnswerView, "AnswerView"),
    (ProblemSummaryView, "ProblemSummary"), (StepOutputView, "StepOutputView"), (RecordReferenceView, "RecordReference"), (AnswerRequest, "AnswerRequest"),
])
def test_a_dto_and_its_typescript_interface_have_the_same_fields(dto: type[BaseModel], interface_name: str) -> None:
    assert wire_fields(dto) == interface_fields(interface_name)


def test_the_tool_target_has_the_same_fields_as_the_typescript_target() -> None:
    assert wire_fields(RunStepToolTargetView) == inline_object_fields("RunStepToolView", "target")


@pytest.mark.parametrize(("values", "union_name"), [
    (ChatAnswerRunStatus, "AnswerRunStatus"), (ChatAnswerStopReason, "AnswerStopReason"), (ChatRunStepKind, "RunStepKind"), (ChatRunStepStatus, "RunStepStatus"),
    (ToolCallingMode, "ToolCallingMode"), (ToolPresentation, "ToolPresentation"), (AskKeiganScope, "AskKeiganScope"),
])
def test_a_value_list_and_its_typescript_union_have_the_same_values(values: type[StrEnum], union_name: str) -> None:
    assert {value.value for value in values} == typescript_union(union_name)


def test_the_record_kinds_of_the_server_are_the_record_kinds_of_the_screen() -> None:
    block = typescript_block("export interface RecordReference ")
    screen_kinds = set(re.findall(r'"([^"]+)"', re.search(r"kind:(.*?);", block, re.DOTALL).group(1)))  # type: ignore[union-attr]
    assert set(RecordReferenceView.model_json_schema(by_alias=True)["properties"]["kind"]["enum"]) == screen_kinds


# ── Event payloads, null versus absent, and the stages (the screen reads each of these by name) ──────────────────────────────────
TRUST_FLAGS = {"isSimulated", "totalCount", "isTruncated"}
EVENT_TRUST_FIELDS = ("outputPreview", "outputCharacterCount", "outputIsTruncated", "itemCount", "summary", "maskedValueCount", "injectionFlagged", "outcomeCode", "outcomeMessage", "records")


def test_the_tool_finished_event_and_the_stored_step_carry_the_same_trust_flags_as_their_own_fields() -> None:
    assert TRUST_FLAGS <= interface_fields("ToolFinishedEvent") and TRUST_FLAGS <= interface_fields("RunStepToolView")
    assert TRUST_FLAGS <= wire_fields(RunStepToolView)


def test_a_step_with_no_tool_or_note_sends_null_and_the_screen_types_say_so() -> None:
    step = RunStepView(run_step_id="s", sequence_number=1, kind="model_turn", status="succeeded", started_at="2026-01-01T00:00:00Z", duration_milliseconds=None, note=None, tool=None)
    dumped = step.model_dump(by_alias=True, mode="json")
    assert dumped["note"] is None and dumped["tool"] is None and {"note", "tool"} <= set(dumped)  # present and null, not absent
    block = typescript_block("export interface RunStepView ")
    assert "note: string | null;" in block and "tool: RunStepToolView | null;" in block


def test_a_tool_without_the_trust_notions_sends_them_as_null_and_the_screen_types_say_so() -> None:
    dumped = RunStepToolView.model_json_schema(by_alias=True)["properties"]
    for flag in TRUST_FLAGS:
        assert {"type": "null"} in dumped[flag]["anyOf"], flag
    block = typescript_block("export interface RunStepToolView ")
    assert "isSimulated: boolean | null;" in block and "totalCount: number | null;" in block and "isTruncated: boolean | null;" in block


def test_a_citation_names_one_target_and_leaves_the_other_fields_absent_as_the_screen_types_say() -> None:
    dumped = CitationView(code="E1", evidence_code="E1", title="Error spike").model_dump(by_alias=True, mode="json")
    assert set(dumped) == {"code", "evidenceCode", "title"}
    block = typescript_block("export interface Citation ")
    assert "runStepId?:" in block and "evidenceCode?:" in block and "runbookId?:" in block


def test_every_progress_stage_the_server_sends_has_a_caption_in_the_screens_strings() -> None:
    captions = json.loads((FRONTEND_SOURCE / "i18n" / "locales" / "en" / "chat.json").read_text(encoding="utf-8"))["tool"]["progress"]
    assert {stage.value for stage in ToolProgressStage} <= set(captions)


def test_the_problem_summary_carries_the_parameters_the_message_was_written_from() -> None:
    assert "parameters" in interface_fields("ProblemSummary") and "parameters" in wire_fields(ProblemSummaryView)
    assert "parameters: Record<string, string | number>;" in typescript_block("export interface ProblemSummary ")


def test_the_tool_finished_fields_the_screen_declares_are_the_fields_the_server_names() -> None:
    declared = interface_fields("ToolFinishedEvent") - {"type", "runStepId", "sequenceNumber", "status", "durationMilliseconds"}
    assert declared == set(EVENT_TRUST_FIELDS) | TRUST_FLAGS

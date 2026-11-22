"""Ask Keigan DTOs: the question, the answer-run snapshot and the full output of one tool call (spec 23, section 7.1 and 7.2).

These classes are the TypeScript types of ``frontend/src/api/askKeiganApi.ts``; ``tests/unit/test_ask_keigan_frontend_contract.py`` keeps the two in step.
Keys inside tool arguments and tool outputs keep the tool's own ``snake_case`` names (they are data, not API fields); everything else is camelCase.
The events of the stream (7.3) are built by ``TraceRecorder`` in the same names and shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, JsonValue, model_serializer

from keigan.ai.tool_registry import AskKeiganScope, RecordKind, ToolPresentation
from keigan.dtos.chat_dtos import MESSAGE_TEXT_MAXIMUM_CHARACTERS
from keigan.dtos.common_dtos import ApiModel
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason, ChatRunStepKind, ChatRunStepStatus, ToolCallingMode


class AnswerRequest(ApiModel):
    message_text: str = Field(min_length=1, max_length=MESSAGE_TEXT_MAXIMUM_CHARACTERS)
    client_request_id: UUID  # a fresh id per question: the server answers a repeat with 409 duplicate_request instead of asking twice


class RecordReferenceView(ApiModel):
    kind: RecordKind
    id: str
    label: str
    application_id: str


class RunStepToolTargetView(ApiModel):
    application_id: str | None
    application_name: str | None
    records: list[RecordReferenceView]


class RunStepToolView(ApiModel):
    name: str
    bound_argument_names: list[str]  # the arguments the scope fixed; the model never chose them
    label: str
    label_key: str
    source: str
    presentation: ToolPresentation
    citation_code: str | None
    arguments: dict[str, JsonValue]
    target: RunStepToolTargetView
    summary: str | None
    output_preview: JsonValue  # the masked output, or its first characters as text when it is long; the whole output is read with the step-output endpoint
    output_character_count: int
    output_is_truncated: bool
    item_count: int | None
    # The trust flags of the output, from the whole output (never from the preview, which may be only its first characters). None when the tool has no such notion.
    is_simulated: bool | None
    total_count: int | None
    is_truncated: bool | None
    masked_value_count: int
    injection_flagged: bool
    outcome_code: str | None
    outcome_message: str | None
    is_redacted: bool  # the reader can no longer read the step's application: arguments, output and target are withheld


class RunStepView(ApiModel):
    run_step_id: str
    sequence_number: int
    kind: ChatRunStepKind
    status: ChatRunStepStatus
    started_at: datetime
    duration_milliseconds: int | None
    note: str | None  # the text of a model turn that asked for tools: shown in the trace, never as the answer
    tool: RunStepToolView | None


class CitationView(ApiModel):
    code: str
    run_step_id: str | None = None
    evidence_code: str | None = None
    runbook_id: str | None = None
    title: str

    @model_serializer(mode="wrap")
    def leave_out_what_the_citation_does_not_point_to(self, serialize: Any) -> dict[str, Any]:
        """A citation names one kind of target; the other fields are absent (as in the ``answer.completed`` event), not null."""
        return {field_name: value for field_name, value in serialize(self).items() if value is not None}


class AnswerView(ApiModel):
    message_id: str
    markdown: str
    citations: list[CitationView]
    follow_ups: list[str]
    is_unverified: bool
    is_refusal: bool


class ProblemSummaryView(ApiModel):
    error_code: str
    title: str
    detail: str
    correlation_id: str | None
    is_retryable: bool  # from the error catalogue (spec 4.10): "Try again" is offered only when true
    parameters: dict[str, str | int]  # the low-sensitivity values the message was written from (the failed step, a limit, a delay); title and detail are already in the person's language


class AnswerRunView(ApiModel):
    answer_run_id: str
    conversation_id: str
    status: ChatAnswerRunStatus
    stop_reason: ChatAnswerStopReason | None
    scope: AskKeiganScope
    started_at: datetime
    completed_at: datetime | None
    duration_milliseconds: int | None
    tool_call_count: int
    maximum_tool_calls: int
    input_token_count: int
    output_token_count: int
    token_counts_estimated: bool
    model_name: str
    tool_calling_mode: ToolCallingMode
    steps: list[RunStepView]
    answer: AnswerView | None
    error: ProblemSummaryView | None
    last_sequence: int  # the last event this process published for a run it is still running; 0 for any other run


class StepOutputView(ApiModel):
    run_step_id: str
    output: JsonValue
    output_character_count: int
    output_is_truncated: bool
    model_view_text: str
    model_view_sha256: str


class CancelAnswerResponse(ApiModel):
    answer_run_id: str
    cancel_requested: bool

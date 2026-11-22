"""The decision trace of an investigation as the API returns it (spec 28, 4.5). Ids, codes, numbers, hashes and catalogue names: never prompt text, never a raw answer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel
from keigan.dtos.investigation_dtos import InvestigationOutcomeDto


class TraceAttemptDto(ApiModel):
    """One model request (a validation retry is a second attempt of the same call)."""

    outcome_status: str
    latency_milliseconds: int
    input_token_count: int
    output_token_count: int


class TraceInputSectionDto(ApiModel):
    """One prompt section that went into a call, by reference: size, whether it was cut, the SHA-256 of its content and the citation codes inside."""

    title: str
    source_label: str
    is_untrusted: bool
    is_flagged: bool
    character_count: int
    sent_character_count: int
    is_truncated: bool
    sha256: str
    citation_codes: list[str] = Field(default_factory=list)


class TraceAdjustmentDto(ApiModel):
    """One thing Keigan's code changed in the model's answer (the screen words the code)."""

    code: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class TraceAiCallDto(ApiModel):
    feature_name: str | None
    prompt_key: str | None
    prompt_version: str | None
    prompt_template_sha256: str | None
    system_prompt_sha256: str | None
    provider_name: str | None
    model_name: str | None
    model_tier: str | None
    input_token_count: int
    output_token_count: int
    token_counts_estimated: bool
    attempts: list[TraceAttemptDto] = Field(default_factory=list)
    input_sections: list[TraceInputSectionDto] = Field(default_factory=list)
    adjustments: list[TraceAdjustmentDto] = Field(default_factory=list)
    has_raw_output: bool
    raw_output_character_count: int | None = None
    raw_output_is_truncated: bool | None = None
    failure_code: str | None = None
    hypothesis_id: str | None = None


class TraceStepDto(ApiModel):
    trace_step_id: str
    sequence_number: int
    stage_name: str
    step_kind: str
    step_status: str
    decision_kind: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_milliseconds: int | None = None
    ai_call: TraceAiCallDto | None = None
    details: dict[str, Any] | None = None


class TraceTotalsDto(ApiModel):
    input_token_count: int
    output_token_count: int
    token_counts_estimated: bool
    ai_call_count: int
    attempt_count: int
    failed_attempt_count: int
    duration_milliseconds: int | None = None


class TraceModelDto(ApiModel):
    provider_name: str | None
    model_name: str | None
    model_tier: str | None
    call_count: int


class TracePromptDto(ApiModel):
    prompt_key: str
    prompt_version: str | None
    prompt_template_sha256: str | None


class TraceCallWithoutStepDto(ApiModel):
    """An AI call of this investigation that no trace step describes (an investigation from before traces, a later draft or postmortem, or a stage that failed and was rolled back)."""

    feature_name: str
    model_name: str
    created_at: datetime
    input_token_count: int
    output_token_count: int
    outcome_status: str


class InvestigationTraceView(ApiModel):
    investigation_id: str
    is_recorded: bool  # false for an investigation that ran before decision traces existed
    is_complete: bool  # false while it runs, or when recording stopped early
    pipeline_version: str | None = None
    status: str
    outcome: InvestigationOutcomeDto | None = None
    totals: TraceTotalsDto
    models: list[TraceModelDto] = Field(default_factory=list)
    prompts: list[TracePromptDto] = Field(default_factory=list)
    steps: list[TraceStepDto] = Field(default_factory=list)
    calls_without_step: list[TraceCallWithoutStepDto] = Field(default_factory=list)


class RawOutputView(ApiModel):
    """The model's answer before Keigan's checks, masked and size-limited; for application admins only."""

    raw_output: dict[str, Any]
    character_count: int
    is_truncated: bool
    sha256: str

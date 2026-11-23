"""Request and response beans for investigations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from keigan.ai.fix_parameter_kinds import bare_safe_pattern, kind_catalogue
from keigan.dtos.common_dtos import ApiModel
from keigan.dtos.incident_dtos import ApplicationReference, IncidentSummaryDto


class FixStepDto(ApiModel):
    """A step of a fix written before spec 33 phase 2 (schema version 1): free text with an optional command."""

    description: str = ""
    command_text: str | None = None
    command_language: str | None = None
    command_risk_level: str | None = None
    command_withheld_reason: str | None = None  # why Keigan did not show the command (spec 33): the description stays
    command_warnings: list[str] = Field(default_factory=list)


class CodeChangeDto(ApiModel):
    repository_name: str | None = None
    file_path: str = "file not identified"
    change_description: str = ""
    before_snippet: str | None = None
    after_snippet: str | None = None


class FixParameterDto(ApiModel):
    """One value of a suggested command or setting, with its status and the rules the browser checks a typed value with (the same patterns the server uses)."""

    name: str
    value_kind: str
    value: str | None = None  # never a refused or masked value: those are cleared on the server
    value_source: str = "unknown"
    source_code: str | None = None
    status: str  # verified, assumed, missing, masked or refused
    status_reason: str | None = None
    value_pattern: str | None = None
    bare_pattern: str | None = None
    maximum_length: int | None = None
    label_key: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _with_the_rules_of_its_kind(cls, data: Any) -> Any:
        if isinstance(data, dict) and "value_pattern" not in data:
            rules = kind_catalogue().get(data.get("value_kind", ""))
            if rules:
                return {**data, "value_pattern": rules["pattern"], "bare_pattern": bare_safe_pattern(), "maximum_length": rules["maximum_length"], "label_key": rules["label_key"]}
        return data


class FixSegmentDto(ApiModel):
    kind: str  # literal, value, assumed_value or missing_value
    text: str = ""
    parameter_name: str | None = None


class FixRenderingDto(ApiModel):
    dialect: str
    text: str | None = None  # null while a value is missing
    risk_level: str
    segments: list[FixSegmentDto] = Field(default_factory=list)


class FixCommandDto(ApiModel):
    tool: str
    dialect: str
    template: str
    parameters: list[FixParameterDto] = Field(default_factory=list)
    withheld_reason: str | None = None
    renderings: list[FixRenderingDto] = Field(default_factory=list)
    risk_level: str
    warnings: list[str] = Field(default_factory=list)


class FixConfigurationChangeDto(ApiModel):
    target_kind: str
    service_name: str
    service_in_catalogue: bool
    setting_name: FixParameterDto
    before_value: FixParameterDto | None = None
    after_value: FixParameterDto
    file_path: str | None = None
    withheld_reason: str | None = None
    risk_level: str
    warnings: list[str] = Field(default_factory=list)


class FixActionDto(ApiModel):
    action_kind: str
    description: str
    expected_result: str = ""
    risk_level: str
    command: FixCommandDto | None = None
    configuration_change: FixConfigurationChangeDto | None = None
    evidence_code: str | None = None
    withheld_reason: str | None = None


class FixStepV2Dto(ApiModel):
    """A checked step (schema version 2): what to do, how to see it worked, how to undo it, each with its own risk (spec 33)."""

    step_id: str
    title: str
    purpose: str
    risk_level: str
    risk_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    has_assumed_values: bool = False
    missing_value_count: int = 0
    action: FixActionDto
    check: FixActionDto | None = None
    revert: FixActionDto | None = None
    perspective: str | None = None  # set on the steps of the fix plan: which analyst wrote it


class ProposedFixDto(ApiModel):
    """Typed so the stored snake_case JSON is returned in camelCase like the rest of the API. Version 1 rows keep their free-text ``steps``; version 2 rows carry ``fix_steps``."""

    schema_version: int = 1
    summary: str = ""
    steps: list[FixStepDto] = Field(default_factory=list)
    fix_steps: list[FixStepV2Dto] = Field(default_factory=list)
    code_changes: list[CodeChangeDto] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _version_two_steps_are_checked_steps(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("schema_version") == 2:
            return {**data, "steps": [], "fix_steps": data.get("steps", [])}
        return data


class FixPlanDto(ApiModel):
    """The steps the synthesis recommends, resolved from the analysts' checked steps."""

    overview_markdown: str = ""
    steps: list[FixStepV2Dto] = Field(default_factory=list)


class StartInvestigationRequest(ApiModel):
    application_id: str
    service_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=5, max_length=8000)
    window_start: datetime | None = None
    window_end: datetime | None = None


class InvestigationFeedbackRequest(ApiModel):
    verdict: str = Field(pattern="^(correct|partially_correct|incorrect)$")
    comment: str | None = Field(default=None, max_length=4000)


NOT_RECORDED_OUTCOME = "not_recorded"  # an investigation that finished before Keigan recorded outcomes


class InvestigationSummaryDto(ApiModel):
    investigation_id: str
    application: ApplicationReference
    incident_id: str | None = None
    incident_number: str | None = None
    incident_title: str | None = None
    investigation_trigger: str
    investigation_status: str
    current_stage_name: str
    progress_percent: int
    keigan_priority: str | None = None
    overall_confidence_score: float | None = None
    investigation_outcome: str | None = None  # cause_identified, inconclusive, cause_not_visible, or not_recorded; null while running, failed or evidence only
    executive_summary: str | None = None
    investigated_service_names: list[str] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    requested_by_user_principal_name: str | None = None


class InvestigationProgressDto(ApiModel):
    investigation_id: str
    status: str
    current_stage_name: str
    progress_percent: int
    stage_messages: list[dict[str, Any]] = Field(default_factory=list)
    failure_reason: str | None = None


class EvidenceDto(ApiModel):
    evidence_id: str
    evidence_code: str
    service_id: str | None = None
    service_name: str | None = None
    evidence_source_kind: str
    evidence_category: str
    evidence_title: str
    evidence_summary: str | None = None
    query_language: str
    query_text: str | None = None
    query_time_range_start: datetime | None = None
    query_time_range_end: datetime | None = None
    matched_record_count: int
    baseline_record_count: int | None = None
    condensed_patterns: list[dict[str, Any]] = Field(default_factory=list)
    metric_series: list[dict[str, Any]] = Field(default_factory=list)
    signal_strength: str
    check_outcome: str | None = None  # signal, no_signal or (rows stored before spec 27 only) not_checked
    baseline_comparison: str | None = None  # compared or no_baseline_for_source
    masked_value_count: int
    possible_prompt_injection: bool
    deep_link_url: str | None = None
    collected_at: datetime


class RunbookReference(ApiModel):
    runbook_id: str
    runbook_title: str


class HypothesisDto(ApiModel):
    hypothesis_id: str
    analysis_perspective: str
    hypothesis_title: str
    hypothesis_statement_markdown: str | None = None
    reasoning_markdown: str | None = None
    confidence_score: float
    state: str | None = None  # supported, ruled_out or inconclusive; null on rows stored before spec 27
    proposed_state: str | None = None  # what the model said before Keigan's rules
    state_guard_code: str | None = None
    state_reason_markdown: str | None = None
    supporting_evidence_codes: list[str] = Field(default_factory=list)
    contradicting_evidence_codes: list[str] = Field(default_factory=list)
    proposed_fix: ProposedFixDto | None = None
    fix_risk_level: str
    matched_runbook: RunbookReference | None = None
    is_leading_hypothesis: bool
    display_order: int


class InvestigationOutcomeDto(ApiModel):
    code: str
    proposed_code: str | None = None
    guard_code: str | None = None
    reason_markdown: str | None = None


class CoverageGapDto(ApiModel):
    """One thing the investigation meant to check and could not (spec 27). Codes and catalogue names only."""

    coverage_gap_id: str
    gap_kind: str
    reason_code: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    source_kind: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    legacy_evidence_code: str | None = None  # set for an unread source an older investigation stored as an evidence item


class TimelineEventDto(ApiModel):
    timeline_event_id: str
    event_occurred_at: datetime
    event_type: str
    event_title: str
    event_details_markdown: str | None = None
    event_source: str
    source_reference: str | None = None
    actor_display_name: str | None = None


class ServiceReference(ApiModel):
    service_id: str
    service_name: str
    service_type: str


class InvestigationDetailDto(InvestigationSummaryDto):
    incident: IncidentSummaryDto | None = None
    investigation_window_start: datetime | None = None
    investigation_window_end: datetime | None = None
    baseline_window_start: datetime | None = None
    baseline_window_end: datetime | None = None
    services: list[ServiceReference] = Field(default_factory=list)
    triage: dict[str, Any] | None = None
    what_went_wrong_markdown: str | None = None
    why_it_happened_markdown: str | None = None
    how_to_fix_markdown: str | None = None
    fix_plan: FixPlanDto | None = None  # null for investigations written before spec 33 phase 2
    open_questions: list[str] = Field(default_factory=list)
    leading_hypothesis_id: str | None = None
    outcome: InvestigationOutcomeDto | None = None
    leading_perspective_reason_markdown: str | None = None
    coverage_gaps: list[CoverageGapDto] = Field(default_factory=list)
    hypotheses: list[HypothesisDto] = Field(default_factory=list)
    evidence: list[EvidenceDto] = Field(default_factory=list)
    blast_radius: dict[str, Any] | None = None
    matched_runbooks: list[RunbookReference] = Field(default_factory=list)
    knowledge_references: list[dict[str, Any]] = Field(default_factory=list)
    alert_group: dict[str, Any] | None = None
    stage_messages: list[dict[str, Any]] = Field(default_factory=list)
    is_evidence_only: bool = False
    failure_reason: str | None = None
    user_feedback_verdict: str | None = None
    user_feedback_comment: str | None = None
    total_input_token_count: int = 0
    total_output_token_count: int = 0
    model_names: list[str] = Field(default_factory=list)
    detected_at: datetime | None = None
    first_update_sent_at: datetime | None = None

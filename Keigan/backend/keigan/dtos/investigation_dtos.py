"""Request and response beans for investigations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel
from keigan.dtos.incident_dtos import ApplicationReference, IncidentSummaryDto


class FixStepDto(ApiModel):
    description: str = ""
    command_text: str | None = None
    command_language: str | None = None
    command_risk_level: str | None = None


class CodeChangeDto(ApiModel):
    repository_name: str | None = None
    file_path: str = "file not identified"
    change_description: str = ""
    before_snippet: str | None = None
    after_snippet: str | None = None


class ProposedFixDto(ApiModel):
    """Typed so the stored snake_case JSON is returned in camelCase like the rest of the API."""

    summary: str = ""
    steps: list[FixStepDto] = Field(default_factory=list)
    code_changes: list[CodeChangeDto] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)


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

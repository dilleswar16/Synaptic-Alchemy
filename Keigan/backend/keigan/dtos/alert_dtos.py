"""Request and response beans for alert sources, the noise policy, alert groups and the noise report."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel
from keigan.entities.status_values import AlertGroupingReason


# ── Alert sources ──────────────────────────────────────────────────────────────
class AlertSourceResponse(ApiModel):
    alert_source_id: str
    application_id: str
    source_tool: str
    source_name: str
    source_status: str
    webhook_url: str
    field_mapping: dict[str, Any] | None = None
    severity_mapping: dict[str, Any] | None = None
    service_mapping: dict[str, Any] | None = None
    last_received_at: datetime | None = None
    received_alert_count: int = 0
    authentication_failure_count: int = 0
    previous_secret_valid_until: datetime | None = None
    seven_day_alert_count: int = 0
    seven_day_group_count: int = 0
    seven_day_investigated_count: int = 0
    created_at: datetime | None = None


class AlertSourceCreateRequest(ApiModel):
    source_tool: Literal["azure_monitor", "elastic", "generic"]
    source_name: str = Field(min_length=2, max_length=200)
    field_mapping: dict[str, Any] | None = None
    severity_mapping: dict[str, Any] | None = None
    service_mapping: dict[str, Any] | None = None


class AlertSourceUpdateRequest(ApiModel):
    source_name: str | None = Field(default=None, min_length=2, max_length=200)
    field_mapping: dict[str, Any] | None = None
    severity_mapping: dict[str, Any] | None = None
    service_mapping: dict[str, Any] | None = None
    is_paused: bool | None = None


class SetupCodeBlock(ApiModel):
    title: str
    language: str
    content: str


class SetupTab(ApiModel):
    tab_key: str
    tab_title: str
    steps: list[str]
    code_blocks: list[SetupCodeBlock] = Field(default_factory=list)


class SetupInstructionsResponse(ApiModel):
    source_tool: str
    webhook_url: str
    webhook_secret_is_placeholder: bool
    header_name: str = "X-Keigan-Token"
    tabs: list[SetupTab]
    canonical_example: dict[str, Any]


class AlertSourceCreatedResponse(ApiModel):
    alert_source: AlertSourceResponse
    webhook_url: str
    webhook_secret: str
    setup_instructions: SetupInstructionsResponse


class SecretRotationResponse(ApiModel):
    alert_source: AlertSourceResponse
    webhook_url: str
    webhook_secret: str
    previous_secret_valid_until: datetime


class MappingPreviewRequest(ApiModel):
    source_tool: Literal["azure_monitor", "elastic", "generic"] = "generic"
    sample_payload: dict[str, Any] | None = None
    field_mapping: dict[str, Any] | None = None
    severity_mapping: dict[str, Any] | None = None
    service_mapping: dict[str, Any] | None = None


class MappingPreviewResponse(ApiModel):
    is_parsed: bool
    error_message: str | None = None
    parsed_alert: dict[str, Any] | None = None
    matched_service_id: str | None = None
    matched_service_name: str | None = None
    suggested_field_mapping: dict[str, str] = Field(default_factory=dict)
    available_paths: list[str] = Field(default_factory=list)
    distinct_service_values: list[str] = Field(default_factory=list)


class RecentAlertEventResponse(ApiModel):
    alert_event_id: str
    received_at: datetime
    processing_status: str
    processing_error_message: str | None = None
    payload_size_bytes: int
    raw_payload: dict[str, Any] | None = None
    parsed_alert: dict[str, Any] | None = None
    matched_service_name: str | None = None
    parse_error: str | None = None


class TestAlertResponse(ApiModel):
    alert_event_id: str
    job_id: str
    message: str


class AzureAlertRuleResponse(ApiModel):
    rule_name: str
    rule_kind: str
    severity: int | None = None
    target_resource: str | None = None
    is_enabled: bool = True
    sends_to_keigan: bool = False
    action_group_names: list[str] = Field(default_factory=list)


class UnreadableResourceGroupResponse(ApiModel):
    resource_group_name: str
    subscription_id: str
    # Why Keigan could not read the rules; the UI turns it into a message. "failed" covers any other error.
    reason_code: Literal["forbidden", "not_found", "throttled", "failed"]


class AzureAlertRulesResponse(ApiModel):
    is_simulated: bool
    total_rule_count: int
    sending_to_keigan_count: int
    rules: list[AzureAlertRuleResponse] = Field(default_factory=list)
    # Resource groups whose rules Azure would not return, so the list above is incomplete for them.
    unreadable_resource_groups: list[UnreadableResourceGroupResponse] = Field(default_factory=list)


# ── Noise policy ───────────────────────────────────────────────────────────────
class NoisePolicySettings(ApiModel):
    min_severity: int = Field(ge=0, le=4)
    investigate_environments: list[str]
    settle_delay_minutes: int = Field(ge=0, le=240)
    no_delay_severities: list[int]
    reopen_window_minutes: int = Field(ge=0, le=1440)
    group_window_minutes: int = Field(ge=1, le=1440)
    flap_count: int = Field(ge=2, le=50)
    flap_window_minutes: int = Field(ge=1, le=1440)
    max_investigations_per_hour: int = Field(ge=1, le=500)
    investigate_score_threshold: float = Field(ge=0, le=200)


class NoisePolicyResponse(ApiModel):
    application_id: str
    policy_mode: Literal["observe", "active"]
    policy_settings: NoisePolicySettings
    policy_sentences: list[str]
    observe_mode_started_at: datetime | None = None
    observe_mode_days_remaining: int | None = None
    observed_effect: FunnelResponse | None = None
    dependency_hint: str | None = None
    updated_at: datetime | None = None


class NoisePolicyUpdateRequest(ApiModel):
    policy_mode: Literal["observe", "active"] | None = None
    policy_settings: NoisePolicySettings | None = None
    reset_to_defaults: bool = False


class NoisePreviewRequest(ApiModel):
    policy_settings: NoisePolicySettings | None = None
    days: int = Field(default=7, ge=1, le=30)


class FunnelStep(ApiModel):
    step_key: str
    step_label: str
    count: int
    detail: str | None = None


class FunnelResponse(ApiModel):
    period_start: datetime
    period_end: datetime
    steps: list[FunnelStep]
    reason_counts: dict[str, int] = Field(default_factory=dict)
    summary_sentence: str = ""
    is_illustration: bool = False


NoisePolicyResponse.model_rebuild()


class MaintenanceWindowRequest(ApiModel):
    window_name: str = Field(min_length=2, max_length=200)
    applies_to_service_ids: list[str] | None = None
    applies_to_environments: list[str] | None = None
    starts_at: datetime
    ends_at: datetime
    repeats_weekly: bool = False


class MaintenanceWindowUpdateRequest(ApiModel):
    window_name: str | None = Field(default=None, min_length=2, max_length=200)
    applies_to_service_ids: list[str] | None = None
    applies_to_environments: list[str] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    repeats_weekly: bool | None = None


class MaintenanceWindowResponse(ApiModel):
    maintenance_window_id: str
    application_id: str
    window_name: str
    applies_to_service_ids: list[str] = Field(default_factory=list)
    applies_to_service_names: list[str] = Field(default_factory=list)
    applies_to_environments: list[str] = Field(default_factory=list)
    starts_at: datetime
    ends_at: datetime
    repeats_weekly: bool
    is_active_now: bool = False
    created_by_user_principal_name: str | None = None


class MuteRuleMatcher(ApiModel):
    rule_name_contains: str | None = None
    service_id: str | None = None
    alert_source_id: str | None = None
    severity: int | None = Field(default=None, ge=0, le=4)
    label_key: str | None = None
    label_value: str | None = None


class MuteRuleRequest(ApiModel):
    rule_name: str = Field(min_length=2, max_length=200)
    matcher: MuteRuleMatcher
    mute_reason: str = Field(min_length=3)
    expires_at: datetime


class MuteRuleUpdateRequest(ApiModel):
    rule_name: str | None = Field(default=None, min_length=2, max_length=200)
    matcher: MuteRuleMatcher | None = None
    mute_reason: str | None = Field(default=None, min_length=3)
    expires_at: datetime | None = None


class MuteRuleResponse(ApiModel):
    mute_rule_id: str
    application_id: str
    rule_name: str
    matcher: dict[str, Any]
    mute_reason: str
    expires_at: datetime
    is_expired: bool
    created_by_user_principal_name: str | None = None


# ── Alert groups ───────────────────────────────────────────────────────────────
class ServiceReference(ApiModel):
    service_id: str
    service_name: str


class GroupingReasonResponse(ApiModel):
    """Why the alerts of a group belong together: a stable code and the names and numbers its sentence needs (see ``services/alert_grouping_reason.py``). The screen writes the sentence."""

    code: AlertGroupingReason
    parameters: dict[str, str | int] = Field(default_factory=dict)


class AlertGroupSummaryResponse(ApiModel):
    alert_group_id: str
    application_id: str
    application_name: str | None = None
    group_title: str
    group_summary: str | None = None
    group_status: str
    priority_score: float
    grouping_reason: GroupingReasonResponse
    member_alert_count: int
    total_occurrence_count: int = 0
    services: list[ServiceReference] = Field(default_factory=list)
    highest_severity_level: int
    started_at: datetime
    last_activity_at: datetime
    resolved_at: datetime | None = None
    investigation_id: str | None = None
    incident_id: str | None = None
    servicenow_incident_suggested: bool = False
    user_feedback_verdict: str | None = None
    decision_reason: str | None = None
    decision_outcome: str | None = None


class AlertMemberResponse(ApiModel):
    alert_id: str
    rule_name: str
    alert_status: str
    severity_level: int
    service_id: str | None = None
    service_name: str | None = None
    alert_summary: str
    alert_link_url: str | None = None
    occurrence_count: int
    is_flapping: bool
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    final_disposition: str | None = None


class AlertDecisionResponse(ApiModel):
    alert_decision_id: str
    alert_id: str
    rule_name: str | None = None
    pipeline_stage: str
    decision_outcome: str
    decision_reason: str
    would_have_outcome_in_active_mode: str | None = None
    decided_at: datetime


class AlertGroupDetailResponse(AlertGroupSummaryResponse):
    members: list[AlertMemberResponse]
    decisions: list[AlertDecisionResponse]
    user_feedback_reason: str | None = None
    policy_mode: str = "observe"
    incident_creation_policy: dict[str, Any] | None = None


class AlertGroupFeedbackRequest(ApiModel):
    verdict: Literal["useful", "noise"]
    reason: str | None = Field(default=None, max_length=2000)


class CreateIncidentResponse(ApiModel):
    incident_id: str
    alert_group_id: str


# ── Weekly noise report ────────────────────────────────────────────────────────
class NoiseReportRow(ApiModel):
    rule_name: str
    service_name: str | None = None
    alert_count: int
    occurrence_count: int
    resolved_within_settle_delay_percentage: int
    flapping_count: int
    led_to_action: bool
    suggestion: str


class NoiseReportResponse(ApiModel):
    application_id: str
    generated_at: datetime | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    total_alert_count: int = 0
    total_occurrence_count: int = 0
    group_count: int = 0
    rows: list[NoiseReportRow] = Field(default_factory=list)
    headline: str = ""

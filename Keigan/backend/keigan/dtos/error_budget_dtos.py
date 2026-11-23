"""Error budget policy as the API sends and receives it (spec 30, 4.7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from keigan.dtos.common_dtos import ApiModel


class BudgetImpactDto(ApiModel):
    """What one incident cost one SLO's error budget, with the inputs (the screen shows how the figure was worked out)."""

    slo_id: str | None = None
    sli_name: str
    target_percentage: float
    budget_window_days: int
    impact_window_start: datetime
    impact_window_end: datetime
    budget_window_start: datetime
    budget_window_end: datetime
    bad_event_count: int
    impact_total_event_count: int
    window_total_event_count: int
    budget_event_count: float | None = None
    budget_share_percent: float | None = None
    data_coverage_percent: float
    is_service_matched: bool
    impact_state: str
    evaluated_at: datetime


class BudgetPolicySummaryDto(ApiModel):
    is_enabled: bool
    single_incident_threshold_percent: float
    minimum_data_coverage_percent: float


class ErrorBudgetBreachDto(ApiModel):
    breach_id: str
    application_id: str
    application_name: str
    breach_kind: str
    incident_id: str | None = None
    incident_reference: str | None = None
    slo_id: str | None = None
    sli_name: str | None = None
    recurrence_category: str | None = None
    recurrence_service_name: str | None = None
    measured_share_percent: float | None = None
    threshold_percent: float | None = None
    window_days: int
    detected_at: datetime
    requirement_status: str
    is_provisional: bool
    qualifying_action_item_id: str | None = None
    waived_by: str | None = None
    waiver_reason_text: str | None = None
    guidance_text: str | None = None  # budget_exhausted only: the team's own agreed response
    can_waive: bool = False
    can_add_action_item: bool = False


class PolicyDefaultsDto(ApiModel):
    single_incident_threshold_percent: float
    outage_class_threshold_percent: float
    outage_class_window_days: int


class PolicyUsesDefaultDto(ApiModel):
    single_incident_threshold: bool
    outage_class_threshold: bool
    outage_class_window: bool


class ErrorBudgetPolicyResponse(ApiModel):
    application_id: str
    is_enabled: bool
    single_incident_threshold_percent: float
    outage_class_threshold_percent: float
    outage_class_window_days: int
    uses_default: PolicyUsesDefaultDto
    defaults: PolicyDefaultsDto
    maximum_outage_class_window_days: int
    exhausted_budget_guidance_text: str | None = None
    guidance_maximum_characters: int
    can_edit: bool
    updated_at: datetime | None = None
    updated_by: str | None = None


class _StrictRequest(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ErrorBudgetPolicyRequest(_StrictRequest):
    """A null threshold or window means the default; the numbers are range-checked by the service so the answer can say which field and why."""

    is_enabled: bool
    single_incident_threshold_percent: float | None = None
    outage_class_threshold_percent: float | None = None
    outage_class_window_days: int | None = None
    exhausted_budget_guidance_text: str | None = None


class WaiveBreachRequest(_StrictRequest):
    reason_text: str


class IncidentBudgetImpactResponse(ApiModel):
    incident_id: str
    policy: BudgetPolicySummaryDto
    impacts: list[BudgetImpactDto]
    breach: ErrorBudgetBreachDto | None = None

"""Error budget policy as the API sends and receives it (spec 30, 4.7)."""

from __future__ import annotations

from datetime import datetime

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


class IncidentBudgetImpactResponse(ApiModel):
    incident_id: str
    policy: BudgetPolicySummaryDto
    impacts: list[BudgetImpactDto]

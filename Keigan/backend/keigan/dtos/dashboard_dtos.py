"""Home dashboard DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel


class HomeKpiResponse(ApiModel):
    open_incidents_total: int = 0
    open_incidents_by_priority: dict[str, int] = Field(default_factory=dict)
    active_alert_group_count: int = 0
    alerts_last_24_hours: int = 0
    noise_reduction_percentage: float | None = None
    slo_total_count: int = 0
    slos_at_risk_count: int = 0
    investigations_last_24_hours: int = 0
    mean_minutes_to_first_update: float | None = None


class ApplicationHealthCard(ApiModel):
    application_id: str
    application_name: str
    application_code: str
    criticality_tier: str
    health_percentage: int
    health_status: str  # healthy | watch | degraded | critical
    worst_budget_remaining_percentage: float | None = None
    worst_budget_slo_name: str | None = None
    availability_sparkline: list[float] = Field(default_factory=list)
    open_incident_count: int = 0
    latest_signal_title: str | None = None
    latest_signal_severity: str | None = None
    component_types: list[str] = Field(default_factory=list)


class LiveIncidentItem(ApiModel):
    incident_id: str
    investigation_id: str | None = None
    application_id: str
    application_name: str
    incident_title: str
    external_incident_number: str | None = None
    priority: str | None = None
    incident_status: str
    investigation_status: str | None = None
    current_stage_name: str | None = None
    progress_percent: int | None = None
    opened_at: datetime


class IntelligenceFeedItem(ApiModel):
    signal_id: str
    application_id: str
    application_name: str
    signal_title: str
    signal_severity: str
    forecast_breach_at: datetime | None = None
    detected_at: datetime


class MaintenanceWindowItem(ApiModel):
    maintenance_window_id: str
    application_id: str
    application_name: str
    window_name: str
    starts_at: datetime
    ends_at: datetime


class RecentPostmortemItem(ApiModel):
    postmortem_id: str
    incident_id: str
    application_name: str
    report_title: str
    report_status: str
    created_at: datetime


class HomeDashboardResponse(ApiModel):
    greeting_name: str
    status_sentence: str
    kpis: HomeKpiResponse
    application_cards: list[ApplicationHealthCard]
    live_incidents: list[LiveIncidentItem]
    intelligence_feed: list[IntelligenceFeedItem]
    maintenance_windows: list[MaintenanceWindowItem]
    recent_postmortems: list[RecentPostmortemItem]
    generated_at: datetime

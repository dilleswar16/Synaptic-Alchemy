"""Request and response beans for SLI proposals, SLIs, SLOs, the SLO dashboard, series and the ecosystem heatmap."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel
from keigan.entities.status_values import SloHealthStatus


class SupportingSignalResponse(ApiModel):
    signal_key: str
    signal_name: str
    description: str | None = None


class SliProposalResponse(ApiModel):
    proposal_key: str
    catalog_entry_key: str
    service_id: str
    service_name: str
    sli_name: str
    sli_kind: str
    explanation: str
    source_chip: str
    good_total_definition: str | None = None
    is_enabled_by_default: bool = True
    is_available: bool = True
    disabled_reason: str | None = None
    measured_percentage: float | None = None
    event_count: int = 0
    sparkline: list[float] = Field(default_factory=list)
    proposed_target_percentage: float | None = None
    proposed_latency_threshold_milliseconds: int | None = None
    rolling_window_days: int = 30
    error_budget_minutes: float | None = None
    error_budget_text: str | None = None
    is_approximate: bool = False
    is_headline: bool = False
    warning: str | None = None
    already_accepted: bool = False


class ServiceProposalGroup(ApiModel):
    service_id: str
    service_name: str
    service_type: str
    proposals: list[SliProposalResponse]
    supporting_signals: list[SupportingSignalResponse] = Field(default_factory=list)


class SloProposalsResponse(ApiModel):
    application_id: str
    measurement_status: Literal["not_started", "measuring", "ready", "failed"]
    progress_stage: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    suggested_slo_count: int = 0
    service_count: int = 0
    headline_proposal: SliProposalResponse | None = None
    groups: list[ServiceProposalGroup] = Field(default_factory=list)
    explanation: str = "Targets are set slightly below what you achieved in the last 30 days, so they are realistic on day one. An SRE can tighten them."


class AcceptedProposal(ApiModel):
    catalog_entry_key: str
    service_id: str
    target_percentage: float = Field(gt=0, lt=100)
    rolling_window_days: Literal[7, 28, 30] = 30
    latency_threshold_milliseconds: int | None = Field(default=None, ge=1)


class AcceptProposalsRequest(ApiModel):
    accepted_proposals: list[AcceptedProposal] = Field(min_length=1)


class AcceptProposalsResponse(ApiModel):
    accepted_count: int
    created_sli_count: int
    created_slo_count: int
    backfill_job_ids: list[str]


class SloResponse(ApiModel):
    slo_id: str
    sli_id: str
    application_id: str
    target_percentage: float
    rolling_window_days: int
    error_budget_minutes: float
    burn_rate_policy: dict[str, Any] | None = None


class SliResponse(ApiModel):
    sli_id: str
    application_id: str
    service_id: str | None = None
    service_name: str | None = None
    catalog_entry_key: str
    sli_name: str
    sli_kind: str
    data_source_kind: str
    query_definition: dict[str, Any] | None = None
    latency_threshold_milliseconds: int | None = None
    is_approximate: bool
    is_enabled: bool
    is_headline: bool
    measured_baseline: dict[str, Any] | None = None
    last_collected_window_start: datetime | None = None
    slo: SloResponse | None = None


class SliCreateRequest(ApiModel):
    service_id: str | None = None
    sli_name: str = Field(min_length=2, max_length=200)
    sli_kind: Literal["availability", "latency", "run_success", "freshness", "dependency_success"] = "availability"
    data_source_kind: Literal["log_query", "metrics"] = "log_query"
    query_definition: dict[str, Any] = Field(description="log_query: {'kql': '... | summarize good=..., total=... by window_start=bin(TimeGenerated, 5m)'}; metrics: {'goodMetric': ..., 'totalMetric': ...}")
    latency_threshold_milliseconds: int | None = Field(default=None, ge=1)
    target_percentage: float | None = Field(default=None, gt=0, lt=100)
    rolling_window_days: Literal[7, 28, 30] = 30


class SliUpdateRequest(ApiModel):
    sli_name: str | None = Field(default=None, min_length=2, max_length=200)
    is_enabled: bool | None = None
    is_headline: bool | None = None
    latency_threshold_milliseconds: int | None = Field(default=None, ge=1)
    query_definition: dict[str, Any] | None = None


class SloCreateRequest(ApiModel):
    sli_id: str
    target_percentage: float = Field(gt=0, lt=100)
    rolling_window_days: Literal[7, 28, 30] = 30


class SloUpdateRequest(ApiModel):
    target_percentage: float | None = Field(default=None, gt=0, lt=100)
    rolling_window_days: Literal[7, 28, 30] | None = None


class SloSummaryResponse(ApiModel):
    slo_id: str
    sli_id: str
    application_id: str
    application_name: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    sli_name: str
    sli_kind: str | None = None
    is_headline: bool = False
    is_approximate: bool = False
    target_percentage: float
    rolling_window_days: int = 30
    compliance_percentage: float | None = None
    error_budget_remaining_percentage: float | None = None
    error_budget_remaining_minutes: float | None = None
    error_budget_total_minutes: float | None = None
    burn_rate_one_hour: float | None = None
    burn_rate_six_hours: float | None = None
    status: SloHealthStatus
    sparkline: list[float] = Field(default_factory=list)


class SeriesPoint(ApiModel):
    timestamp: datetime
    sli_percentage: float | None = None
    good_event_count: int = 0
    total_event_count: int = 0
    budget_remaining_percentage: float | None = None


class SloSeriesResponse(ApiModel):
    slo_id: str
    sli_name: str
    target_percentage: float
    rolling_window_days: int
    resolution_minutes: int
    points: list[SeriesPoint]
    compliance_percentage: float | None = None


class HeatmapCell(ApiModel):
    date: str
    compliance_percentage: float | None = None


class HeatmapRow(ApiModel):
    application_id: str
    application_name: str
    slo_id: str
    row_label: str
    service_name: str | None = None
    target_percentage: float
    overall_compliance_percentage: float | None = None
    status: SloHealthStatus
    cells: list[HeatmapCell]


class EcosystemHeatmapResponse(ApiModel):
    days: int
    dates: list[str]
    rows: list[HeatmapRow]

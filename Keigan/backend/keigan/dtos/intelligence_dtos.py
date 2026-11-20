"""Request and response beans for predictive signals, intelligence reports and the health-score trend."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel

SignalStatus = Literal["open", "acknowledged", "dismissed"]


class PredictiveSignalResponse(ApiModel):
    predictive_signal_id: str
    application_id: str
    application_name: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    sli_id: str | None = None
    detector_name: str
    signal_severity: str
    signal_title: str
    explanation_markdown: str | None = None
    metric_name: str | None = None
    observed_value: float | None = None
    expected_value: float | None = None
    deviation_score: float | None = None
    forecast_breach_at: datetime | None = None
    confidence_score: float
    evidence_series: list[Any] = Field(default_factory=list)
    signal_status: str
    detected_at: datetime
    status_changed_by_user_principal_name: str | None = None
    intelligence_report_id: str | None = None
    investigation_id: str | None = None


class PredictiveSignalStatusRequest(ApiModel):
    signal_status: SignalStatus


class SignalInvestigationResponse(ApiModel):
    investigation_id: str
    predictive_signal_id: str


class IntelligenceReportSummary(ApiModel):
    intelligence_report_id: str
    application_id: str
    application_name: str | None = None
    report_type: str
    report_title: str
    report_period_start: datetime
    report_period_end: datetime
    overall_health_score: int | None = None
    sent_at: datetime | None = None
    recipient_count: int = 0
    created_at: datetime


class IntelligenceReportResponse(IntelligenceReportSummary):
    report_markdown: str | None = None
    report_sections: dict[str, Any] = Field(default_factory=dict)
    recipient_addresses: list[str] = Field(default_factory=list)


class GenerateReportRequest(ApiModel):
    report_type: Literal["weekly_digest", "proactive_alert"] = "weekly_digest"
    send_to_stakeholders: bool = False


class HealthScorePoint(ApiModel):
    day: str
    health_score: int
    slo_component: float
    signal_component: float
    incident_component: float


class HealthScoreTrendResponse(ApiModel):
    application_id: str
    current_health_score: int | None = None
    points: list[HealthScorePoint]

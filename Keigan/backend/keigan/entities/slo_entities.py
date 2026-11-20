"""SLO monitoring and predictive intelligence entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now


class ServiceLevelIndicator(AuditColumnsMixin, EntityBase):
    __tablename__ = "service_level_indicator"

    sli_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str | None] = mapped_column(String(36), index=True)
    catalog_entry_key: Mapped[str] = mapped_column(String(120), default="custom")
    sli_name: Mapped[str] = mapped_column(String(200))
    sli_kind: Mapped[str] = mapped_column(String(30))
    data_source_kind: Mapped[str] = mapped_column(String(30))
    query_definition_json: Mapped[dict[str, Any] | None] = mapped_column()
    latency_threshold_milliseconds: Mapped[int | None] = mapped_column(Integer)
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_headline: Mapped[bool] = mapped_column(Boolean, default=False)
    measured_baseline_json: Mapped[dict[str, Any] | None] = mapped_column()
    last_collected_window_start: Mapped[datetime | None] = mapped_column()


class ServiceLevelObjective(AuditColumnsMixin, EntityBase):
    __tablename__ = "service_level_objective"

    slo_id: Mapped[str] = identifier_column()
    sli_id: Mapped[str] = mapped_column(ForeignKey("service_level_indicator.sli_id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    target_percentage: Mapped[float] = mapped_column(Float)
    rolling_window_days: Mapped[int] = mapped_column(Integer, default=30)
    burn_rate_policy_json: Mapped[dict[str, Any] | None] = mapped_column()


class SliMeasurement(EntityBase):
    __tablename__ = "sli_measurement"
    __table_args__ = (UniqueConstraint("sli_id", "measurement_window_start", name="uq_sli_measurement_window"),)

    sli_measurement_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    sli_id: Mapped[str] = mapped_column(String(36), index=True)
    measurement_window_start: Mapped[datetime] = mapped_column()
    good_event_count: Mapped[int | None] = mapped_column(BigInteger)
    total_event_count: Mapped[int | None] = mapped_column(BigInteger)
    measured_value: Mapped[float | None] = mapped_column(Float)
    collected_at: Mapped[datetime] = mapped_column(default=utc_now)


class SloBurnAlert(EntityBase):
    __tablename__ = "slo_burn_alert"

    slo_burn_alert_id: Mapped[str] = identifier_column()
    slo_id: Mapped[str] = mapped_column(ForeignKey("service_level_objective.slo_id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    burn_alert_severity: Mapped[str] = mapped_column(String(10))
    long_window_burn_rate: Mapped[float] = mapped_column(Float)
    short_window_burn_rate: Mapped[float] = mapped_column(Float)
    fired_at: Mapped[datetime] = mapped_column(default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column()
    alert_group_id: Mapped[str | None] = mapped_column(String(36))


class PredictiveSignal(EntityBase):
    __tablename__ = "predictive_signal"
    __table_args__ = (Index("ix_predictive_signal_application_detected", "application_id", "detected_at"),)

    predictive_signal_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(String(36))
    service_id: Mapped[str | None] = mapped_column(String(36))
    sli_id: Mapped[str | None] = mapped_column(String(36))
    detector_name: Mapped[str] = mapped_column(String(40))
    signal_severity: Mapped[str] = mapped_column(String(10), default="warning")
    signal_title: Mapped[str] = mapped_column(String(400))
    explanation_markdown: Mapped[str | None] = mapped_column(Text)
    metric_name: Mapped[str | None] = mapped_column(String(200))
    observed_value: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    deviation_score: Mapped[float | None] = mapped_column(Float)
    forecast_breach_at: Mapped[datetime | None] = mapped_column()
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_series_json: Mapped[list[Any] | None] = mapped_column()
    signal_status: Mapped[str] = mapped_column(String(30), default="open")
    detected_at: Mapped[datetime] = mapped_column(default=utc_now)
    status_changed_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    intelligence_report_id: Mapped[str | None] = mapped_column(String(36))


class IntelligenceReport(EntityBase):
    __tablename__ = "intelligence_report"

    intelligence_report_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    report_type: Mapped[str] = mapped_column(String(20))
    report_title: Mapped[str] = mapped_column(String(400))
    report_period_start: Mapped[datetime] = mapped_column()
    report_period_end: Mapped[datetime] = mapped_column()
    overall_health_score: Mapped[int | None] = mapped_column(Integer)
    report_markdown: Mapped[str | None] = mapped_column(Text)
    report_sections_json: Mapped[dict[str, Any] | None] = mapped_column()
    sent_at: Mapped[datetime | None] = mapped_column()
    recipient_addresses_json: Mapped[list[str] | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


__all__ = [
    "IntelligenceReport",
    "PredictiveSignal",
    "ServiceLevelIndicator",
    "ServiceLevelObjective",
    "SliMeasurement",
    "SloBurnAlert",
]

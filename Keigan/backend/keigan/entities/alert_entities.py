"""Alert intake and noise-reduction entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now


class AlertSource(AuditColumnsMixin, EntityBase):
    __tablename__ = "alert_source"

    alert_source_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    source_tool: Mapped[str] = mapped_column(String(30))
    source_name: Mapped[str] = mapped_column(String(200))
    webhook_secret_hash: Mapped[str] = mapped_column(String(128))
    previous_webhook_secret_hash: Mapped[str | None] = mapped_column(String(128))
    previous_secret_valid_until: Mapped[datetime | None] = mapped_column()
    field_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    severity_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    service_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    source_status: Mapped[str] = mapped_column(String(30), default="waiting_for_first_alert")
    last_received_at: Mapped[datetime | None] = mapped_column()
    received_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    authentication_failure_count: Mapped[int] = mapped_column(Integer, default=0)


class AlertEvent(EntityBase):
    __tablename__ = "alert_event"

    alert_event_id: Mapped[str] = identifier_column()
    alert_source_id: Mapped[str] = mapped_column(ForeignKey("alert_source.alert_source_id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    received_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column()
    payload_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    processing_status: Mapped[str] = mapped_column(String(20), default="received")
    processing_error_message: Mapped[str | None] = mapped_column(Text)


class Alert(EntityBase):
    __tablename__ = "alert"
    __table_args__ = (Index("ix_alert_application_fingerprint_status", "application_id", "alert_fingerprint", "alert_status"),)

    alert_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(String(36))
    alert_source_id: Mapped[str | None] = mapped_column(String(36))
    external_alert_identifier: Mapped[str | None] = mapped_column(String(400))
    alert_fingerprint: Mapped[str] = mapped_column(String(64))
    rule_identifier: Mapped[str | None] = mapped_column(String(600))
    rule_name: Mapped[str] = mapped_column(String(400))
    service_id: Mapped[str | None] = mapped_column(String(36))
    resource_reference: Mapped[str | None] = mapped_column(String(600))
    environment_name: Mapped[str | None] = mapped_column(String(20))
    severity_level: Mapped[int] = mapped_column(Integer, default=3)
    alert_status: Mapped[str] = mapped_column(String(20), default="firing")
    alert_summary: Mapped[str] = mapped_column(String(1000), default="")
    alert_description: Mapped[str | None] = mapped_column(Text)
    alert_link_url: Mapped[str | None] = mapped_column(String(1000))
    alert_labels_json: Mapped[dict[str, Any] | None] = mapped_column()
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    state_change_count: Mapped[int] = mapped_column(Integer, default=1)
    is_flapping: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column()
    alert_group_id: Mapped[str | None] = mapped_column(String(36), index=True)
    final_disposition: Mapped[str | None] = mapped_column(String(30))
    latest_alert_event_id: Mapped[str | None] = mapped_column(String(36))


class AlertDecision(EntityBase):
    __tablename__ = "alert_decision"

    alert_decision_id: Mapped[str] = identifier_column()
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.alert_id", ondelete="CASCADE"), index=True)
    alert_group_id: Mapped[str | None] = mapped_column(String(36))
    pipeline_stage: Mapped[str] = mapped_column(String(20))
    decision_outcome: Mapped[str] = mapped_column(String(40))
    decision_reason: Mapped[str] = mapped_column(String(600))
    would_have_outcome_in_active_mode: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime] = mapped_column(default=utc_now)


class AlertGroup(EntityBase):
    __tablename__ = "alert_group"
    __table_args__ = (Index("ix_alert_group_application_status_activity", "application_id", "group_status", "last_activity_at"),)

    alert_group_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(String(36))
    group_title: Mapped[str] = mapped_column(String(400))
    group_summary: Mapped[str | None] = mapped_column(Text)
    group_status: Mapped[str] = mapped_column(String(20), default="open")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    grouping_reason: Mapped[str | None] = mapped_column(String(400))
    member_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    primary_service_id: Mapped[str | None] = mapped_column(String(36))
    affected_service_ids_json: Mapped[list[str] | None] = mapped_column()
    highest_severity_level: Mapped[int] = mapped_column(Integer, default=4)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column()
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    incident_id: Mapped[str | None] = mapped_column(String(36))
    servicenow_incident_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    user_feedback_verdict: Mapped[str | None] = mapped_column(String(20))
    user_feedback_reason: Mapped[str | None] = mapped_column(Text)
    user_feedback_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))


class NoiseReductionPolicy(AuditColumnsMixin, EntityBase):
    __tablename__ = "noise_reduction_policy"

    application_id: Mapped[str] = mapped_column(
        ForeignKey("application.application_id", ondelete="CASCADE"), primary_key=True
    )
    policy_settings_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    policy_mode: Mapped[str] = mapped_column(String(10), default="observe")
    observe_mode_started_at: Mapped[datetime | None] = mapped_column()


class MaintenanceWindow(AuditColumnsMixin, EntityBase):
    __tablename__ = "maintenance_window"

    maintenance_window_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    window_name: Mapped[str] = mapped_column(String(200))
    applies_to_service_ids_json: Mapped[list[str] | None] = mapped_column()
    applies_to_environments_json: Mapped[list[str] | None] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    repeats_weekly: Mapped[bool] = mapped_column(Boolean, default=False)


class AlertMuteRule(AuditColumnsMixin, EntityBase):
    __tablename__ = "alert_mute_rule"

    mute_rule_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    rule_name: Mapped[str] = mapped_column(String(200))
    matcher_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    mute_reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column()


__all__ = [
    "Alert",
    "AlertDecision",
    "AlertEvent",
    "AlertGroup",
    "AlertMuteRule",
    "AlertSource",
    "MaintenanceWindow",
    "NoiseReductionPolicy",
]

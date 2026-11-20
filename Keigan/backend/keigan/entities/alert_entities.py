"""Alert intake and noise-reduction entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now
from keigan.entities.linked_ids import LinkedIdsMixin, OrderedLinkColumns, linked_ids_property, ordered_links_relationship
from keigan.entities.status_values import AlertEventProcessingStatus, AlertFinalDisposition, AlertGroupFeedbackVerdict, AlertGroupStatus, AlertPipelineStage, AlertSourceStatus, AlertSourceTool, AlertStatus, NoisePolicyMode, values_check


class AlertSource(AuditColumnsMixin, EntityBase):
    __tablename__ = "alert_source"
    __table_args__ = (
        values_check("source_tool", AlertSourceTool),
        values_check("source_status", AlertSourceStatus),
    )

    alert_source_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    source_tool: Mapped[str] = mapped_column(String(30))
    source_name: Mapped[str] = mapped_column(String(200))
    webhook_secret_hash: Mapped[str] = mapped_column(String(128))
    previous_webhook_secret_hash: Mapped[str | None] = mapped_column(String(128))
    previous_secret_valid_until: Mapped[datetime | None] = mapped_column()
    # Names of the plaintext webhook secrets in the secret store (the HMAC signing keys). Null on sources created before signing keys were stored.
    webhook_secret_name: Mapped[str | None] = mapped_column(String(200))
    previous_webhook_secret_name: Mapped[str | None] = mapped_column(String(200))
    field_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    severity_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    service_mapping_json: Mapped[dict[str, Any] | None] = mapped_column()
    source_status: Mapped[str] = mapped_column(String(30), default="waiting_for_first_alert")
    last_received_at: Mapped[datetime | None] = mapped_column()
    received_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    authentication_failure_count: Mapped[int] = mapped_column(Integer, default=0)


class AlertEvent(EntityBase):
    __tablename__ = "alert_event"
    __table_args__ = (
        values_check("processing_status", AlertEventProcessingStatus),
    )

    alert_event_id: Mapped[str] = identifier_column()
    alert_source_id: Mapped[str] = mapped_column(ForeignKey("alert_source.alert_source_id", ondelete="CASCADE"), index=True)
    # NO ACTION: alert events already cascade from their alert source, and SQL Server allows one cascade path.
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id"), index=True)
    received_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column()
    payload_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    processing_status: Mapped[str] = mapped_column(String(20), default="received")
    processing_error_message: Mapped[str | None] = mapped_column(Text)


# An alert is "open" while it is firing (a flapping alert stays firing). The database allows one open alert per fingerprint.
OPEN_ALERT_STATUS = AlertStatus.FIRING.value
_OPEN_ALERT_FILTER = text(f"alert_status = '{OPEN_ALERT_STATUS}'")


class Alert(EntityBase):
    __tablename__ = "alert"
    __table_args__ = (
        Index("ix_alert_application_fingerprint_status", "application_id", "alert_fingerprint", "alert_status"),
        # Filtered unique index (portable like uq_incident_external_number): resolved alerts keep their fingerprint for history.
        Index(
            "uq_alert_open_fingerprint", "application_id", "alert_fingerprint", unique=True,
            mssql_where=_OPEN_ALERT_FILTER, postgresql_where=_OPEN_ALERT_FILTER, sqlite_where=_OPEN_ALERT_FILTER,
        ),
        values_check("alert_status", AlertStatus),
        values_check("final_disposition", AlertFinalDisposition),
    )

    alert_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    alert_source_id: Mapped[str | None] = mapped_column(String(36))
    external_alert_identifier: Mapped[str | None] = mapped_column(String(400))
    alert_fingerprint: Mapped[str] = mapped_column(String(64))
    rule_identifier: Mapped[str | None] = mapped_column(String(600))
    rule_name: Mapped[str] = mapped_column(String(400))
    # NO ACTION: the service already cascades from the application; deleting a service clears this reference (reference_release).
    service_id: Mapped[str | None] = mapped_column(ForeignKey("monitored_service.service_id"))
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
    __table_args__ = (
        values_check("pipeline_stage", AlertPipelineStage),
    )

    alert_decision_id: Mapped[str] = identifier_column()
    alert_id: Mapped[str] = mapped_column(ForeignKey("alert.alert_id", ondelete="CASCADE"), index=True)
    alert_group_id: Mapped[str | None] = mapped_column(String(36))
    pipeline_stage: Mapped[str] = mapped_column(String(20))
    decision_outcome: Mapped[str] = mapped_column(String(40))
    decision_reason: Mapped[str] = mapped_column(String(600))
    would_have_outcome_in_active_mode: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime] = mapped_column(default=utc_now)


class AlertGroup(LinkedIdsMixin, EntityBase):
    link_relationship_names = ("affected_service_links",)

    __tablename__ = "alert_group"
    __table_args__ = (
        Index("ix_alert_group_application_status_activity", "application_id", "group_status", "last_activity_at"),
        values_check("group_status", AlertGroupStatus),
        values_check("user_feedback_verdict", AlertGroupFeedbackVerdict),
    )

    alert_group_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    group_title: Mapped[str] = mapped_column(String(400))
    group_summary: Mapped[str | None] = mapped_column(Text)
    group_status: Mapped[str] = mapped_column(String(20), default="open")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    grouping_reason: Mapped[str | None] = mapped_column(String(400))
    member_alert_count: Mapped[int] = mapped_column(Integer, default=0)
    primary_service_id: Mapped[str | None] = mapped_column(ForeignKey("monitored_service.service_id"))
    affected_service_links: Mapped[list[AlertGroupAffectedService]] = ordered_links_relationship("AlertGroupAffectedService")
    affected_service_ids = linked_ids_property("affected_service_links")
    highest_severity_level: Mapped[int] = mapped_column(Integer, default=4)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column()
    # The group says which investigation covers it and which incident it belongs to (see AlertGroupLinkService). NO ACTION: both parents
    # cascade from the application; deleting an investigation or incident clears these (retention) and the application delete removes the groups first.
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"))
    servicenow_incident_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    user_feedback_verdict: Mapped[str | None] = mapped_column(String(20))
    user_feedback_reason: Mapped[str | None] = mapped_column(Text)
    user_feedback_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))


class AlertGroupAffectedService(OrderedLinkColumns, EntityBase):
    """A service an alert group touches; the first one is the group's first service."""

    __tablename__ = "alert_group_affected_service"
    linked_id_attribute = "service_id"

    alert_group_id: Mapped[str] = mapped_column(ForeignKey("alert_group.alert_group_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the group already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


class NoiseReductionPolicy(AuditColumnsMixin, EntityBase):
    __tablename__ = "noise_reduction_policy"
    __table_args__ = (
        values_check("policy_mode", NoisePolicyMode),
    )

    application_id: Mapped[str] = mapped_column(
        ForeignKey("application.application_id", ondelete="CASCADE"), primary_key=True
    )
    policy_settings_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    policy_mode: Mapped[str] = mapped_column(String(10), default="observe")
    observe_mode_started_at: Mapped[datetime | None] = mapped_column()


class MaintenanceWindow(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("service_links",)

    __tablename__ = "maintenance_window"

    maintenance_window_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    window_name: Mapped[str] = mapped_column(String(200))
    service_links: Mapped[list[MaintenanceWindowAppliesToService]] = ordered_links_relationship("MaintenanceWindowAppliesToService")
    applies_to_service_ids = linked_ids_property("service_links")
    applies_to_environments_json: Mapped[list[str] | None] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    repeats_weekly: Mapped[bool] = mapped_column(Boolean, default=False)


class MaintenanceWindowAppliesToService(OrderedLinkColumns, EntityBase):
    """A service a maintenance window applies to (an empty list means every service of the application)."""

    __tablename__ = "maintenance_window_applies_to_service"
    linked_id_attribute = "service_id"

    maintenance_window_id: Mapped[str] = mapped_column(ForeignKey("maintenance_window.maintenance_window_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the window already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


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
    "AlertGroupAffectedService",
    "AlertMuteRule",
    "AlertSource",
    "MaintenanceWindow",
    "MaintenanceWindowAppliesToService",
    "NoiseReductionPolicy",
]

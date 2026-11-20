"""Platform-wide entities: users, settings, secrets, audit, LLM usage and the background job queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, UtcDateTime, identifier_column, utc_now


class PlatformUser(AuditColumnsMixin, EntityBase):
    __tablename__ = "platform_user"

    platform_user_id: Mapped[str] = identifier_column()
    user_principal_name: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    email_address: Mapped[str | None] = mapped_column(String(320))
    entra_object_id: Mapped[str | None] = mapped_column(String(36))
    preferred_locale: Mapped[str | None] = mapped_column(String(10))
    preferred_theme: Mapped[str | None] = mapped_column(String(10))
    last_known_group_names_json: Mapped[list[str] | None] = mapped_column()
    last_sign_in_at: Mapped[datetime | None] = mapped_column()


class PlatformSetting(EntityBase):
    __tablename__ = "platform_setting"

    setting_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    setting_value_json: Mapped[dict[str, Any] | None] = mapped_column()
    setting_description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    updated_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))


class StoredSecret(AuditColumnsMixin, EntityBase):
    __tablename__ = "stored_secret"

    secret_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    encrypted_secret_value: Mapped[str | None] = mapped_column(Text)
    secret_description: Mapped[str | None] = mapped_column(String(400))
    last_rotated_at: Mapped[datetime | None] = mapped_column()


class AuditEvent(EntityBase):
    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_occurred_at", "occurred_at"),)

    audit_event_id: Mapped[str] = identifier_column()
    actor_user_principal_name: Mapped[str] = mapped_column(String(320))
    action_name: Mapped[str] = mapped_column(String(120))
    target_entity_type: Mapped[str | None] = mapped_column(String(80))
    target_entity_id: Mapped[str | None] = mapped_column(String(36))
    application_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action_details_json: Mapped[dict[str, Any] | None] = mapped_column()
    client_ip_address: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(default=utc_now)


class LlmUsageRecord(EntityBase):
    __tablename__ = "llm_usage_record"
    __table_args__ = (Index("ix_llm_usage_record_created_application", "created_at", "application_id"),)

    llm_usage_record_id: Mapped[str] = identifier_column()
    application_id: Mapped[str | None] = mapped_column(String(36))
    investigation_id: Mapped[str | None] = mapped_column(String(36))
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    feature_name: Mapped[str] = mapped_column(String(80))
    provider_name: Mapped[str] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(120))
    model_tier: Mapped[str] = mapped_column(String(20))
    input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    output_token_count: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_token_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_milliseconds: Mapped[int] = mapped_column(Integer, default=0)
    outcome_status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class BackgroundJob(EntityBase):
    __tablename__ = "background_job"
    __table_args__ = (Index("ix_background_job_status_available", "job_status", "available_at", "priority_number"),)

    background_job_id: Mapped[str] = identifier_column()
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    job_payload_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    job_status: Mapped[str] = mapped_column(String(20), default="queued")
    priority_number: Mapped[int] = mapped_column(Integer, default=100)
    deduplication_key: Mapped[str | None] = mapped_column(String(200), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    maximum_attempt_count: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(default=utc_now)
    leased_by_worker_name: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column()
    last_error_message: Mapped[str | None] = mapped_column(Text)
    result_summary_json: Mapped[dict[str, Any] | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


__all__ = ["AuditEvent", "BackgroundJob", "LlmUsageRecord", "PlatformSetting", "PlatformUser", "StoredSecret", "UtcDateTime"]

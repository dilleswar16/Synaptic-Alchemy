"""Application onboarding entities: applications, components, discovered resources, services, log sources, integrations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now
from keigan.entities.status_values import AccessVerificationStatus, ApplicationLifecycleStatus, ComponentType, CriticalityTier, IntegrationStatus, LogToolConnectionStatus, ReadTestStatus, values_check


class Application(AuditColumnsMixin, EntityBase):
    __tablename__ = "application"
    __table_args__ = (
        values_check("lifecycle_status", ApplicationLifecycleStatus),
        values_check("criticality_tier", CriticalityTier),
    )

    application_id: Mapped[str] = identifier_column()
    application_name: Mapped[str] = mapped_column(String(200), nullable=False)
    application_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    application_description: Mapped[str | None] = mapped_column(Text)
    business_unit_name: Mapped[str | None] = mapped_column(String(200))
    region_code: Mapped[str | None] = mapped_column(String(10))
    primary_locale: Mapped[str] = mapped_column(String(10), default="en")
    time_zone_name: Mapped[str] = mapped_column(String(60), default="UTC")
    criticality_tier: Mapped[str] = mapped_column(String(10), default="tier_2")
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="draft")
    admin_group_name: Mapped[str] = mapped_column(String(200))
    admin_group_object_id: Mapped[str | None] = mapped_column(String(36))
    reader_group_name: Mapped[str] = mapped_column(String(200))
    reader_group_object_id: Mapped[str | None] = mapped_column(String(36))
    incident_creation_policy_json: Mapped[dict[str, Any] | None] = mapped_column()
    onboarding_progress_json: Mapped[dict[str, Any] | None] = mapped_column()
    went_live_at: Mapped[datetime | None] = mapped_column()
    went_live_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))


class ApplicationComponent(AuditColumnsMixin, EntityBase):
    __tablename__ = "application_component"
    __table_args__ = (
        values_check("component_type", ComponentType),
        values_check("access_verification_status", AccessVerificationStatus),
    )

    component_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    component_type: Mapped[str] = mapped_column(String(40))
    component_name: Mapped[str] = mapped_column(String(200))
    environment_name: Mapped[str] = mapped_column(String(20), default="prod")
    azure_tenant_id: Mapped[str | None] = mapped_column(String(36))
    azure_subscription_id: Mapped[str | None] = mapped_column(String(36))
    azure_subscription_name: Mapped[str | None] = mapped_column(String(200))
    azure_resource_group_name: Mapped[str | None] = mapped_column(String(200))
    component_configuration_json: Mapped[dict[str, Any] | None] = mapped_column()
    access_verification_status: Mapped[str] = mapped_column(String(20), default="not_checked")
    access_verification_details_json: Mapped[list[Any] | None] = mapped_column()
    last_verified_at: Mapped[datetime | None] = mapped_column()
    last_discovered_at: Mapped[datetime | None] = mapped_column()
    discovery_summary_json: Mapped[dict[str, Any] | None] = mapped_column()


class DiscoveredResource(EntityBase):
    __tablename__ = "discovered_resource"
    __table_args__ = (UniqueConstraint("component_id", "azure_resource_id", name="uq_discovered_resource_component_resource"),)

    discovered_resource_id: Mapped[str] = identifier_column()
    component_id: Mapped[str] = mapped_column(ForeignKey("application_component.component_id", ondelete="CASCADE"), index=True)
    # NO ACTION: discovered resources already cascade from their component.
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id"), index=True)
    azure_resource_id: Mapped[str] = mapped_column(String(600))
    resource_name: Mapped[str] = mapped_column(String(260))
    resource_type: Mapped[str] = mapped_column(String(200))
    resource_kind: Mapped[str | None] = mapped_column(String(120))
    location_name: Mapped[str | None] = mapped_column(String(60))
    monitoring_classification: Mapped[str] = mapped_column(String(30), default="not_monitored_type")
    has_diagnostic_setting: Mapped[bool] = mapped_column(Boolean, default=False)
    diagnostic_settings_json: Mapped[list[Any] | None] = mapped_column()
    log_analytics_workspace_resource_ids_json: Mapped[list[str] | None] = mapped_column()
    resource_tags_json: Mapped[dict[str, Any] | None] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    no_longer_found_at: Mapped[datetime | None] = mapped_column()


class MonitoredService(AuditColumnsMixin, EntityBase):
    __tablename__ = "monitored_service"
    __table_args__ = (
        values_check("criticality_tier", CriticalityTier),
    )

    service_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    # NO ACTION (not SET NULL): SQL Server forbids a second cascade path from application; component removal deletes its services explicitly.
    component_id: Mapped[str | None] = mapped_column(ForeignKey("application_component.component_id"))
    discovered_resource_id: Mapped[str | None] = mapped_column(String(36))
    service_name: Mapped[str] = mapped_column(String(200))
    service_type: Mapped[str] = mapped_column(String(40))
    external_resource_identifier: Mapped[str | None] = mapped_column(String(600))
    environment_name: Mapped[str] = mapped_column(String(20), default="prod")
    criticality_tier: Mapped[str] = mapped_column(String(10), default="tier_2")
    is_monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    aks_namespace_filter: Mapped[str | None] = mapped_column(String(200))
    application_insights_resource_id: Mapped[str | None] = mapped_column(String(600))
    application_insights_role_name: Mapped[str | None] = mapped_column(String(200))
    available_metrics_json: Mapped[list[Any] | None] = mapped_column()
    repository_provider: Mapped[str | None] = mapped_column(String(40))
    repository_url: Mapped[str | None] = mapped_column(String(600))
    repository_default_branch: Mapped[str | None] = mapped_column(String(200))
    repository_path: Mapped[str | None] = mapped_column(String(400))
    repository_credential_secret_name: Mapped[str | None] = mapped_column(String(200))
    service_description: Mapped[str | None] = mapped_column(Text)


class ServiceDependency(EntityBase):
    __tablename__ = "service_dependency"
    __table_args__ = (UniqueConstraint("upstream_service_id", "downstream_service_id", name="uq_service_dependency_pair"),)

    service_dependency_id: Mapped[str] = identifier_column()
    # NO ACTION: dependencies already cascade from their upstream service.
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id"), index=True)
    upstream_service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id", ondelete="CASCADE"))
    # NO ACTION: SQL Server allows one cascade path; service removal deletes dependencies in both directions explicitly.
    downstream_service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"))
    dependency_kind: Mapped[str] = mapped_column(String(30), default="calls")
    dependency_source: Mapped[str] = mapped_column(String(30), default="user_declared")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class LogToolConnection(AuditColumnsMixin, EntityBase):
    __tablename__ = "log_tool_connection"
    __table_args__ = (
        values_check("connection_status", LogToolConnectionStatus),
    )

    log_tool_connection_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    tool_type: Mapped[str] = mapped_column(String(40))
    connection_name: Mapped[str] = mapped_column(String(200))
    endpoint_url: Mapped[str | None] = mapped_column(String(600))
    authentication_method: Mapped[str] = mapped_column(String(40), default="api_key")
    credential_secret_name: Mapped[str | None] = mapped_column(String(200))
    connection_configuration_json: Mapped[dict[str, Any] | None] = mapped_column()
    connection_status: Mapped[str] = mapped_column(String(30), default="not_tested")
    last_tested_at: Mapped[datetime | None] = mapped_column()
    last_test_message: Mapped[str | None] = mapped_column(Text)
    newest_log_timestamp_seen_at: Mapped[datetime | None] = mapped_column()


class ServiceLogSource(EntityBase):
    __tablename__ = "service_log_source"
    __table_args__ = (
        values_check("last_read_test_status", ReadTestStatus),
    )

    service_log_source_id: Mapped[str] = identifier_column()
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(40))
    # NO ACTION: a connection still used by a service cannot be deleted (the service checks and explains this).
    log_tool_connection_id: Mapped[str | None] = mapped_column(ForeignKey("log_tool_connection.log_tool_connection_id"))
    log_analytics_workspace_resource_id: Mapped[str | None] = mapped_column(String(600))
    log_analytics_workspace_customer_id: Mapped[str | None] = mapped_column(String(36))
    query_scope_json: Mapped[dict[str, Any] | None] = mapped_column()
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False)
    was_auto_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_read_test_status: Mapped[str] = mapped_column(String(20), default="not_tested")
    last_read_test_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class ExternalIntegration(AuditColumnsMixin, EntityBase):
    __tablename__ = "external_integration"
    __table_args__ = (
        UniqueConstraint("application_id", "integration_kind", name="uq_external_integration_kind"),
        values_check("integration_status", IntegrationStatus),
    )

    external_integration_id: Mapped[str] = identifier_column()
    application_id: Mapped[str | None] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    integration_kind: Mapped[str] = mapped_column(String(40))
    integration_configuration_json: Mapped[dict[str, Any] | None] = mapped_column()
    credential_secret_name: Mapped[str | None] = mapped_column(String(200))
    integration_status: Mapped[str] = mapped_column(String(30), default="not_set_up")
    integration_notes: Mapped[str | None] = mapped_column(Text)


class ApplicationRecordLink(EntityBase):
    __tablename__ = "application_record_link"

    application_record_link_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    record_system: Mapped[str] = mapped_column(String(30))
    record_identifier: Mapped[str] = mapped_column(String(100))
    link_status: Mapped[str] = mapped_column(String(30), default="saved_reader_in_development")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


__all__ = [
    "Application",
    "ApplicationComponent",
    "ApplicationRecordLink",
    "DiscoveredResource",
    "ExternalIntegration",
    "LogToolConnection",
    "MonitoredService",
    "ServiceDependency",
    "ServiceLogSource",
]

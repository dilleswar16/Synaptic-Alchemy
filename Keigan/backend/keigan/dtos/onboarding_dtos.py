"""Onboarding: components, discovery, services, log sources, dependencies, log tools, integrations, record links, ServiceNow groups."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel

ComponentType = Literal["azure_resource_group", "hardware", "mainframe", "saas_platform"]
EnvironmentName = Literal["dev", "test", "uat", "prod"]
CriticalityTier = Literal["tier_1", "tier_2", "tier_3"]


# ── Components ─────────────────────────────────────────────────────────────────
class ComponentCreateRequest(ApiModel):
    component_type: ComponentType
    component_name: str = Field(min_length=1, max_length=200)
    environment_name: EnvironmentName = "prod"
    azure_tenant_id: str | None = None
    azure_subscription_id: str | None = None
    azure_subscription_name: str | None = None
    azure_resource_group_name: str | None = None
    component_configuration: dict[str, Any] | None = None


class ComponentUpdateRequest(ApiModel):
    component_name: str | None = Field(default=None, min_length=1, max_length=200)
    environment_name: EnvironmentName | None = None
    azure_tenant_id: str | None = None
    azure_subscription_name: str | None = None
    component_configuration: dict[str, Any] | None = None


class AccessCheckResponse(ApiModel):
    check_name: str
    passed: bool
    message: str
    missing_role_name: str | None = None


class ComponentResponse(ApiModel):
    component_id: str
    application_id: str
    component_type: str
    component_name: str
    environment_name: str
    azure_tenant_id: str | None = None
    azure_subscription_id: str | None = None
    azure_subscription_name: str | None = None
    azure_resource_group_name: str | None = None
    component_configuration: dict[str, Any] | None = None
    access_verification_status: str
    access_verification_details: list[dict[str, Any]] | None = None
    last_verified_at: datetime | None = None
    last_discovered_at: datetime | None = None
    discovery_summary: dict[str, Any] | None = None
    service_count: int = 0
    is_simulated: bool = False
    updated_at: datetime | None = None


class RoleCommandsResponse(ApiModel):
    cli: str
    powershell: str
    terraform: str
    portal_steps: list[str]
    required_roles: list[dict[str, str]]
    tenant_note: str | None = None


class DiscoveredResourceResponse(ApiModel):
    discovered_resource_id: str
    component_id: str
    azure_resource_id: str
    resource_name: str
    resource_type: str
    resource_type_display_name: str
    resource_kind: str | None = None
    location_name: str | None = None
    monitoring_classification: str
    has_diagnostic_setting: bool
    diagnostic_settings: list[dict[str, Any]] | None = None
    last_seen_at: datetime
    no_longer_found_at: datetime | None = None
    service_id: str | None = None


# ── Services ───────────────────────────────────────────────────────────────────
class LogSourceInput(ApiModel):
    source_kind: Literal["log_analytics", "application_insights", "azure_monitor_metrics", "log_tool", "synthetic_probe", "vendor_status_page"]
    log_tool_connection_id: str | None = None
    log_analytics_workspace_resource_id: str | None = None
    log_analytics_workspace_customer_id: str | None = None
    query_scope: dict[str, Any] | None = None
    is_primary_source: bool = False


class LogSourceResponse(ApiModel):
    service_log_source_id: str
    service_id: str
    source_kind: str
    log_tool_connection_id: str | None = None
    log_tool_connection_name: str | None = None
    log_analytics_workspace_resource_id: str | None = None
    log_analytics_workspace_customer_id: str | None = None
    query_scope: dict[str, Any] | None = None
    is_primary_source: bool
    was_auto_detected: bool
    last_read_test_status: str
    last_read_test_at: datetime | None = None


class ServiceCreateRequest(ApiModel):
    service_name: str = Field(min_length=1, max_length=200)
    service_type: str
    component_id: str | None = None
    external_resource_identifier: str | None = None
    environment_name: EnvironmentName = "prod"
    criticality_tier: CriticalityTier = "tier_2"
    aks_namespace_filter: str | None = None
    service_description: str | None = None


class ServiceUpdateRequest(ApiModel):
    service_name: str | None = Field(default=None, min_length=1, max_length=200)
    environment_name: EnvironmentName | None = None
    criticality_tier: CriticalityTier | None = None
    is_monitoring_enabled: bool | None = None
    aks_namespace_filter: str | None = None
    application_insights_resource_id: str | None = None
    application_insights_role_name: str | None = None
    repository_provider: str | None = None
    repository_url: str | None = None
    repository_default_branch: str | None = None
    repository_path: str | None = None
    service_description: str | None = None


class ServiceBulkChanges(ApiModel):
    environment_name: EnvironmentName | None = None
    criticality_tier: CriticalityTier | None = None
    is_monitoring_enabled: bool | None = None
    add_log_source: LogSourceInput | None = None


class ServiceBulkUpdateRequest(ApiModel):
    service_ids: list[str] = Field(min_length=1)
    changes: ServiceBulkChanges


class ServiceResponse(ApiModel):
    service_id: str
    application_id: str
    component_id: str | None = None
    component_name: str | None = None
    component_type: str | None = None
    discovered_resource_id: str | None = None
    service_name: str
    service_type: str
    external_resource_identifier: str | None = None
    environment_name: str
    criticality_tier: str
    is_monitoring_enabled: bool
    aks_namespace_filter: str | None = None
    application_insights_resource_id: str | None = None
    application_insights_role_name: str | None = None
    available_metric_count: int = 0
    available_metrics: list[dict[str, Any]] | None = None
    repository_provider: str | None = None
    repository_url: str | None = None
    repository_default_branch: str | None = None
    repository_path: str | None = None
    repository_credential_configured: bool = False
    service_description: str | None = None
    log_sources: list[LogSourceResponse] = []
    has_diagnostic_setting: bool | None = None
    no_longer_found_at: datetime | None = None
    depends_on_service_ids: list[str] = []
    updated_at: datetime | None = None


class ServiceDependencyInput(ApiModel):
    upstream_service_id: str
    downstream_service_id: str
    dependency_kind: str = "calls"


class ServiceDependencyResponse(ServiceDependencyInput):
    service_dependency_id: str
    dependency_source: str


class ServiceDependenciesUpdateRequest(ApiModel):
    dependencies: list[ServiceDependencyInput]


class DiagnosticSettingCommandResponse(ApiModel):
    has_diagnostic_setting: bool
    cli_command: str
    powershell_command: str
    explanation: str


class LogSourceTestResponse(ApiModel):
    service_log_source_id: str
    succeeded: bool
    message: str
    newest_log_timestamp: datetime | None = None


# ── Log tool connections ───────────────────────────────────────────────────────
LogToolType = Literal["elastic", "splunk", "datadog", "solarwinds", "ibm_z_log_analytics", "vendor_api", "other"]


class LogToolConnectionCreateRequest(ApiModel):
    tool_type: LogToolType
    connection_name: str = Field(min_length=1, max_length=200)
    endpoint_url: str | None = None
    authentication_method: str = "api_key"
    connection_configuration: dict[str, Any] | None = None
    credential_value: str | None = Field(default=None, repr=False, description="Write-only secret; never returned.")


class LogToolConnectionUpdateRequest(ApiModel):
    connection_name: str | None = None
    endpoint_url: str | None = None
    authentication_method: str | None = None
    connection_configuration: dict[str, Any] | None = None
    credential_value: str | None = Field(default=None, repr=False)


class LogToolConnectionResponse(ApiModel):
    log_tool_connection_id: str
    application_id: str
    tool_type: str
    connection_name: str
    endpoint_url: str | None = None
    authentication_method: str
    connection_configuration: dict[str, Any] | None = None
    has_credential: bool
    credential_set_at: datetime | None = None
    connection_status: str
    last_tested_at: datetime | None = None
    last_test_message: str | None = None
    newest_log_timestamp_seen_at: datetime | None = None
    reader_available: bool
    used_by_service_names: list[str] = []


class ConnectionTestResponse(ApiModel):
    succeeded: bool
    message: str
    newest_log_timestamp: datetime | None = None
    reader_not_available: bool = False


# ── Integrations and record links ──────────────────────────────────────────────
class IntegrationResponse(ApiModel):
    integration_kind: str
    display_name: str
    purpose: str
    reader_available: bool
    fields: list[dict[str, Any]]
    integration_configuration: dict[str, Any] = {}
    credential_secret_name: str | None = None
    integration_status: str
    integration_notes: str | None = None
    updated_at: datetime | None = None


class IntegrationUpdateRequest(ApiModel):
    integration_configuration: dict[str, Any] | None = None
    credential_value: str | None = Field(default=None, repr=False, description="Write-only secret; Keigan stores it under a name it generates.")
    integration_notes: str | None = None


class RecordLinkCreateRequest(ApiModel):
    record_system: Literal["eai", "cmdb"]
    record_identifier: str = Field(min_length=1, max_length=100)


class RecordLinkResponse(ApiModel):
    application_record_link_id: str
    record_system: str
    record_identifier: str
    link_status: str
    created_at: datetime


# ── ServiceNow assignment groups ───────────────────────────────────────────────
class ServiceNowGroupsUpdateRequest(ApiModel):
    group_names: list[str]


class ServiceNowGroupResponse(ApiModel):
    assignment_group_id: str
    group_name: str
    verification_status: str
    servicenow_sys_id: str | None = None


class ServiceNowGroupSearchResult(ApiModel):
    group_name: str
    servicenow_sys_id: str | None = None
    is_verified: bool

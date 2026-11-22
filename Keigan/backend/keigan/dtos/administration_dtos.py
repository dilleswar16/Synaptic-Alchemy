"""Administration DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel


class SettingsGroupResponse(ApiModel):
    group_key: str
    group_title: str
    settings: dict[str, Any]


class IntegrationStatusResponse(ApiModel):
    integration_key: str
    mode: str
    is_simulated: bool
    is_configured: bool
    summary: str


class KeiganIdentityResponse(ApiModel):
    managed_identity_object_id: str
    managed_identity_client_id: str
    managed_identity_display_name: str
    multi_tenant_app_client_id: str | None = None


class ModelCapabilitiesResponse(ApiModel):
    """What one configured AI model can do, as Keigan resolved it (the catalogue and the overrides in the settings)."""

    model_tier: str
    model_name: str
    tool_calling: str
    parallel_tool_calls: bool
    streams_text: bool
    streams_tool_requests: bool
    supports_tool_choice_none: bool
    supports_temperature: bool
    reports_stream_usage: bool
    max_context_tokens: int


class ConformanceReportSummaryResponse(ApiModel):
    """The last run of the Ask Keigan conformance script against a real model (``scripts/run_ask_keigan_conformance.py``)."""

    generated_at: datetime
    passed: bool
    provider_name: str
    model_name: str
    tool_calling_mode: str
    scenario_count: int
    passed_count: int


class AdministrationSettingsResponse(ApiModel):
    environment: str
    product_version: str
    groups: list[SettingsGroupResponse]
    integrations: list[IntegrationStatusResponse]
    keigan_identity: KeiganIdentityResponse
    simulation_controls_available: bool
    model_capabilities: list[ModelCapabilitiesResponse]
    last_conformance_report: ConformanceReportSummaryResponse | None = None


class ConnectionTestOutcome(ApiModel):
    integration: str
    succeeded: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    tested_at: datetime


class UsageBucketResponse(ApiModel):
    bucket_key: str
    bucket_label: str
    call_count: int
    input_token_count: int
    output_token_count: int
    estimated_cost: float


class UsageResponse(ApiModel):
    period_start: datetime
    period_end: datetime
    group_by: str
    buckets: list[UsageBucketResponse]
    total_call_count: int
    total_input_token_count: int
    total_output_token_count: int
    total_estimated_cost: float
    average_tokens_per_investigation: float | None = None
    failed_call_count: int = 0


class AuditEventResponse(ApiModel):
    audit_event_id: str
    actor_user_principal_name: str
    action_name: str
    target_entity_type: str | None = None
    target_entity_id: str | None = None
    application_id: str | None = None
    action_details: dict[str, Any] | None = None
    occurred_at: datetime


class JobResponse(ApiModel):
    job_id: str
    job_type: str
    job_status: str
    attempt_count: int
    maximum_attempt_count: int
    last_error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class JobStatsResponse(ApiModel):
    counts_by_status: dict[str, int]
    counts_by_type: dict[str, int]
    dead_letters: list[JobResponse]
    recent_jobs: list[JobResponse]


class SimulationScenarioResponse(ApiModel):
    scenario_key: str
    title: str
    category: str
    service_types: str


class TriggerScenarioRequest(ApiModel):
    application_id: str

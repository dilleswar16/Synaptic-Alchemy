"""Applications: list, detail, create / request, readiness, access and platform identity."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from keigan.dtos.common_dtos import ApiModel

CriticalityTier = Literal["tier_1", "tier_2", "tier_3"]
APPLICATION_CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,10}$")


class IncidentCreationPolicy(ApiModel):
    mode: Literal["suggest", "automatic"] = "suggest"
    minimum_score: int = Field(default=70, ge=0, le=100)
    assignment_group_name: str | None = None


class ApplicationCreateRequest(ApiModel):
    application_name: str = Field(min_length=2, max_length=200)
    application_code: str
    application_description: str | None = None
    business_unit_name: str | None = None
    region_code: str | None = Field(default=None, max_length=10)
    primary_locale: str | None = None
    time_zone_name: str | None = None
    criticality_tier: CriticalityTier = "tier_2"
    lifecycle_status: Literal["draft", "requested"] | None = None

    @field_validator("application_code")
    @classmethod
    def validate_application_code(cls, application_code: str) -> str:
        normalized_code = application_code.strip().upper()
        if not APPLICATION_CODE_PATTERN.match(normalized_code):
            raise ValueError("Use 2 to 10 upper-case letters or digits.")
        return normalized_code


class ApplicationUpdateRequest(ApiModel):
    application_name: str | None = Field(default=None, min_length=2, max_length=200)
    application_description: str | None = None
    business_unit_name: str | None = None
    region_code: str | None = None
    primary_locale: str | None = None
    time_zone_name: str | None = None
    criticality_tier: CriticalityTier | None = None
    lifecycle_status: Literal["draft", "onboarding", "requested"] | None = None
    incident_creation_policy: IncidentCreationPolicy | None = None
    onboarding_progress: dict[str, Any] | None = None


class ApplicationResponse(ApiModel):
    application_id: str
    application_name: str
    application_code: str
    application_description: str | None = None
    business_unit_name: str | None = None
    region_code: str | None = None
    primary_locale: str
    time_zone_name: str
    criticality_tier: str
    lifecycle_status: str
    admin_group_name: str
    reader_group_name: str
    incident_creation_policy: dict[str, Any] | None = None
    onboarding_progress: dict[str, Any] | None = None
    went_live_at: datetime | None = None
    went_live_by_user_principal_name: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


class ApplicationSummaryResponse(ApplicationResponse):
    component_types: list[str] = []
    component_count: int = 0
    service_count: int = 0
    open_incident_count: int = 0
    slo_compliance_percentage: float | None = None
    required_done_count: int | None = None
    required_total_count: int | None = None


class RequirementResponse(ApiModel):
    requirement_key: str
    step_key: str
    is_done: bool
    detail: str | None = None
    count: int | None = None


class StepStatusResponse(ApiModel):
    step_key: str
    status: Literal["not_started", "in_progress", "waiting", "blocked", "done"]
    summary: str | None = None


class ReadinessResponse(ApiModel):
    required: list[RequirementResponse]
    good_to_know: list[RequirementResponse]
    can_go_live: bool
    steps: list[StepStatusResponse]
    next_step_key: str | None = None


class AccessResponse(ApiModel):
    admin_group_name: str
    admin_group_object_id: str | None = None
    reader_group_name: str
    reader_group_object_id: str | None = None
    members_available: bool = False
    admin_members: list[str] = []
    reader_members: list[str] = []
    sailpoint_instructions: str
    can_edit_group_names: bool = False


class AccessUpdateRequest(ApiModel):
    admin_group_name: str | None = None
    admin_group_object_id: str | None = None
    reader_group_name: str | None = None
    reader_group_object_id: str | None = None


class GroupVerificationResult(ApiModel):
    role: Literal["admin", "reader"]
    group_name: str
    exists: bool | None  # None = could not check (for example Graph permission missing)
    object_id: str | None = None
    member_count: int | None = None
    sample_member_names: list[str] = []
    object_id_saved: bool = False
    message: str


class AccessVerificationResponse(ApiModel):
    results: list[GroupVerificationResult]
    checked_at: datetime
    directory: Literal["entra", "local_demo_users"]


class PlatformIdentityResponse(ApiModel):
    tenant_id: str | None = None
    client_id: str | None = None
    object_id: str | None = None
    display_name: str | None = None
    multi_tenant_client_id: str | None = None
    is_simulated: bool
    is_complete: bool = True
    missing_values: list[str] = []
    identity_source: str = "settings"  # settings | discovered | not_configured

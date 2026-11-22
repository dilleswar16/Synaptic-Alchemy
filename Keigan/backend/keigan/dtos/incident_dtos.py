"""Request and response beans for incidents, communications and postmortems."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel


class ApplicationReference(ApiModel):
    application_id: str
    application_code: str
    application_name: str


class InvestigationBrief(ApiModel):
    investigation_id: str
    investigation_status: str
    current_stage_name: str
    progress_percent: int
    overall_confidence_score: float | None = None
    investigation_outcome: str | None = None
    executive_summary: str | None = None
    investigation_trigger: str
    started_at: datetime | None = None
    completed_at: datetime | None = None


class IncidentSummaryDto(ApiModel):
    incident_id: str
    application: ApplicationReference
    incident_source: str
    external_incident_number: str | None = None
    incident_title: str
    servicenow_priority: str | None = None
    keigan_priority: str | None = None
    incident_category: str | None = None
    incident_status: str
    external_state: str | None = None
    affected_service_names: list[str] = Field(default_factory=list)
    assignment_group_name: str | None = None
    opened_at: datetime
    detected_by_keigan_at: datetime
    resolved_at: datetime | None = None
    duration_minutes: int
    keigan_confidence: float | None = None
    latest_investigation_id: str | None = None
    latest_investigation_status: str | None = None
    servicenow_url: str | None = None


class IncidentDetailDto(IncidentSummaryDto):
    incident_description: str | None = None
    priority_rationale: str | None = None
    servicenow_impact: str | None = None
    servicenow_urgency: str | None = None
    first_update_sent_at: datetime | None = None
    closed_at: datetime | None = None
    latest_investigation: InvestigationBrief | None = None
    postmortem_id: str | None = None
    postmortem_status: str | None = None


class ResolveIncidentRequest(ApiModel):
    resolution_note: str | None = Field(default=None, max_length=4000)
    generate_postmortem: bool = True


class CommunicationDto(ApiModel):
    communication_id: str
    incident_id: str | None = None
    investigation_id: str | None = None
    communication_type: str
    audience_type: str
    language_code: str
    subject_line: str
    body_markdown: str
    communication_status: str
    approved_by_user_principal_name: str | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CommunicationUpdateRequest(ApiModel):
    subject_line: str | None = Field(default=None, max_length=400)
    body_markdown: str | None = Field(default=None, max_length=20000)


class GenerateCommunicationsRequest(ApiModel):
    communication_type: str = "progress_update"
    language_codes: list[str] = Field(default_factory=lambda: ["en", "ja"])


class CommunicationSendResult(ApiModel):
    communication: CommunicationDto
    deliveries_queued: int
    message: str


class PostmortemDto(ApiModel):
    postmortem_id: str
    incident_id: str
    investigation_id: str | None = None
    report_title: str
    report_markdown: str | None = None
    report_sections: dict[str, Any] | None = None
    language_code: str
    report_status: str
    generation_trigger: str
    finalized_by_user_principal_name: str | None = None
    finalized_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PostmortemUpdateRequest(ApiModel):
    report_title: str | None = Field(default=None, max_length=400)
    report_markdown: str | None = Field(default=None, max_length=100000)

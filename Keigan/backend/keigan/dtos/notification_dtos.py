"""Request and response beans for stakeholders, the outbox, the directory search and the Teams incident chat."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from keigan.dtos.common_dtos import ApiModel
from keigan.utils.email_address import normalize_email_address

RecipientType = Literal["person", "teams_channel", "distribution_list"]
StakeholderRole = Literal["sre", "developer", "manager", "executive", "business_owner", "vendor_contact", "lead", "infra", "devops", "tester"]
PriorityCode = Literal["P1", "P2", "P3", "P4"]
NOTIFICATION_TYPE_VALUES = ("incident_detected", "preliminary_report", "progress_update", "postmortem", "intelligence_report", "slo_burn_alert", "alert_group", "error_budget_policy")
NOTIFICATION_CHANNEL_VALUES = ("email", "teams_incident_chat", "teams_channel")


def _normalized_address_or_none(typed_address: str | None) -> str | None:
    """Empty means "no address" (a Teams channel has none); anything else must be a real address, stored trimmed and in lower case."""
    return normalize_email_address(typed_address) if typed_address and typed_address.strip() else None


class StakeholderRequestBase(ApiModel):
    recipient_type: RecipientType = "person"
    display_name: str = Field(min_length=1, max_length=200)
    email_address: str | None = Field(default=None, max_length=320)
    user_principal_name: str | None = Field(default=None, max_length=320)
    entra_object_id: str | None = Field(default=None, max_length=36)
    teams_team_id: str | None = Field(default=None, max_length=100)
    teams_channel_id: str | None = Field(default=None, max_length=200)
    stakeholder_role: StakeholderRole = "sre"
    subscribed_service_ids: list[str] = Field(default_factory=list, description="Empty means every service of the application.")
    notification_channels: list[str] = Field(default_factory=lambda: ["email"])
    minimum_priority: PriorityCode = "P2"
    subscribed_notification_types: list[str] = Field(default_factory=lambda: list(NOTIFICATION_TYPE_VALUES[:4]))
    preferred_language_code: str = Field(default="en", max_length=10)
    is_active: bool = True

    @field_validator("email_address")
    @classmethod
    def validate_email_address(cls, typed_address: str | None) -> str | None:
        return _normalized_address_or_none(typed_address)


class StakeholderCreateRequest(StakeholderRequestBase):
    send_invitation: bool = Field(default=False, description="Email the person an invitation (people only).")


class StakeholderUpdateRequest(ApiModel):
    recipient_type: RecipientType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email_address: str | None = None
    user_principal_name: str | None = None
    entra_object_id: str | None = None
    teams_team_id: str | None = None
    teams_channel_id: str | None = None
    stakeholder_role: StakeholderRole | None = None
    subscribed_service_ids: list[str] | None = None
    notification_channels: list[str] | None = None
    minimum_priority: PriorityCode | None = None
    subscribed_notification_types: list[str] | None = None
    preferred_language_code: str | None = None
    is_active: bool | None = None

    @field_validator("email_address")
    @classmethod
    def validate_email_address(cls, typed_address: str | None) -> str | None:
        return _normalized_address_or_none(typed_address)


class TeamMemberRequest(ApiModel):
    """One person entered while an application is created: the rest (channels, priority, language) takes the stakeholder defaults."""

    display_name: str = Field(min_length=1, max_length=200)
    email_address: str = Field(max_length=320)
    stakeholder_role: StakeholderRole = "developer"

    @field_validator("email_address")
    @classmethod
    def validate_email_address(cls, typed_address: str) -> str:
        return normalize_email_address(typed_address)


class StakeholderResponse(ApiModel):
    stakeholder_id: str
    application_id: str
    recipient_type: str
    display_name: str
    email_address: str | None = None
    user_principal_name: str | None = None
    entra_object_id: str | None = None
    teams_team_id: str | None = None
    teams_channel_id: str | None = None
    stakeholder_role: str
    subscribed_service_ids: list[str]
    notification_channels: list[str]
    minimum_priority: str
    subscribed_notification_types: list[str]
    preferred_language_code: str
    is_active: bool
    updated_at: datetime | None = None
    team_member_status: Literal["listed", "invited", "active", "inactive"] = "listed"
    invited_at: datetime | None = None
    invited_by_user_principal_name: str | None = None
    last_invitation_sent_at: datetime | None = None
    joined_at: datetime | None = None
    invitation_is_stale: bool = False
    can_send_invitation: bool = False
    next_invitation_allowed_at: datetime | None = None


class StakeholderInvitationResponse(ApiModel):
    team_member: StakeholderResponse
    delivery_id: str | None = None
    message: str


class StakeholderTestResponse(ApiModel):
    deliveries_queued: int
    delivery_ids: list[str]
    message: str


class DirectoryUserResponse(ApiModel):
    display_name: str
    email_address: str | None = None
    user_principal_name: str | None = None
    entra_object_id: str | None = None
    job_title: str | None = None
    source: str = "local"


class NotificationDeliverySummary(ApiModel):
    notification_delivery_id: str
    application_id: str | None = None
    application_name: str | None = None
    incident_id: str | None = None
    notification_type: str
    delivery_channel: str
    recipient_address: str
    subject_line: str | None = None
    delivery_status: str
    attempt_count: int
    last_error_message: str | None = None
    created_at: datetime
    sent_at: datetime | None = None


class NotificationDeliveryDetail(NotificationDeliverySummary):
    body_html: str | None = None
    body_text: str | None = None
    provider_message_identifier: str | None = None
    investigation_id: str | None = None


class TeamsChatParticipant(ApiModel):
    display_name: str
    user_principal_name: str | None = None
    role: str = "member"


class TeamsChatMessageResponse(ApiModel):
    message_id: str
    author_role: str
    author_display_name: str | None = None
    author_user_principal_name: str | None = None
    message_text: str
    adaptive_card: dict[str, Any] | None = None
    created_at: datetime


class TeamsChatFactResponse(ApiModel):
    timeline_event_id: str
    event_title: str
    event_details_markdown: str | None = None
    event_occurred_at: datetime
    actor_display_name: str | None = None


class TeamsChatResponse(ApiModel):
    incident_id: str
    chat_exists: bool
    is_simulated: bool = True
    chat_topic: str | None = None
    chat_web_url: str | None = None
    chat_status: str | None = None
    participants: list[TeamsChatParticipant] = Field(default_factory=list)
    messages: list[TeamsChatMessageResponse] = Field(default_factory=list)
    facts: list[TeamsChatFactResponse] = Field(default_factory=list)
    can_post: bool = False


class TeamsChatPostRequest(ApiModel):
    message_text: str = Field(min_length=1, max_length=4000)

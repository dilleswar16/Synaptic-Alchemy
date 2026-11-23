"""Action items as the API sends and receives them (spec 29, 4.5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from keigan.dtos.common_dtos import ApiModel
from keigan.entities.status_values import ActionItemPriority, ActionItemStatus, ActionItemType


class ActionItemOwnerDto(ApiModel):
    """The team member an item is assigned to (set by a person, never by the AI)."""

    stakeholder_id: str
    display_name: str
    stakeholder_role: str


class ActionItemDto(ApiModel):
    action_item_id: str
    application_id: str
    application_name: str
    incident_id: str | None = None
    incident_reference: str | None = None
    postmortem_id: str | None = None
    source_kind: str
    item_title: str
    item_details_markdown: str | None = None
    action_type: str
    action_priority: str
    item_status: str
    suggested_owner_role_text: str | None = None
    owner: ActionItemOwnerDto | None = None
    due_on: date | None = None
    original_due_on: date | None = None
    due_on_change_count: int
    is_overdue: bool
    days_overdue: int
    status_reason_text: str | None = None
    completion_note_text: str | None = None
    completed_at: datetime | None = None
    completed_by: str | None = None
    accepted_at: datetime | None = None
    external_reference_text: str | None = None
    can_edit: bool  # the caller may change the item's fields
    can_change_status: bool
    allowed_statuses: list[str] = Field(default_factory=list)  # what the caller may move it to, so the screen never offers a refused action
    created_at: datetime
    updated_at: datetime


class _StrictRequest(ApiModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ActionItemCreateRequest(_StrictRequest):
    item_title: str = Field(min_length=2, max_length=300)
    item_details_markdown: str | None = None
    action_type: ActionItemType
    action_priority: ActionItemPriority = ActionItemPriority.NORMAL
    owner_stakeholder_id: str | None = None
    due_on: date
    incident_id: str | None = None
    postmortem_id: str | None = None
    external_reference_text: str | None = None


class ActionItemUpdateRequest(_StrictRequest):
    """Every field is optional; ``ownerStakeholderId: null`` unassigns (the fields the caller sent are in ``model_fields_set``)."""

    item_title: str | None = Field(default=None, min_length=2, max_length=300)
    item_details_markdown: str | None = None
    action_type: ActionItemType | None = None
    action_priority: ActionItemPriority | None = None
    owner_stakeholder_id: str | None = None
    due_on: date | None = None
    external_reference_text: str | None = None


class ActionItemStatusRequest(_StrictRequest):
    status: ActionItemStatus
    reason_text: str | None = None
    completion_note_text: str | None = None


# ── Overview (spec 29, 4.4 and 4.5): counts per application, never a ranking of people ──────────────────────────────────────────────────


class CompletionFiguresDto(ApiModel):
    accepted_count: int
    done_count: int
    wont_do_count: int
    open_count: int
    overdue_count: int
    completion_rate: float | None = None  # percent; absent while there is nothing to divide
    completion_rate_sample_count: int
    median_days_to_complete: float | None = None
    median_sample_count: int
    on_time_share: float | None = None
    on_time_sample_count: int


class ApplicationCompletionDto(CompletionFiguresDto):
    application_id: str
    application_name: str


class AttentionEntryDto(ApiModel):
    kind: str
    application_id: str
    application_name: str
    record_kind: str
    record_id: str
    title: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class EarlierPreventItemDto(ApiModel):
    action_item_id: str
    item_title: str
    status_at_repeat: str  # done, not_done or wont_do, as it stood when the later incident opened


class RepeatIncidentDto(ApiModel):
    incident_id: str
    incident_reference: str
    opened_at: datetime
    outcome: str | None = None  # absent for the first incident of the group; the others say what happened to the earlier follow-ups
    earlier_prevent_items: list[EarlierPreventItemDto] = Field(default_factory=list)


class RepeatGroupDto(ApiModel):
    application_id: str
    application_name: str
    recurrence_category: str
    service_id: str
    service_name: str
    incidents: list[RepeatIncidentDto]


class ActionItemOverviewResponse(ApiModel):
    period_start: datetime
    period_end: datetime
    period_days: int
    completion: CompletionFiguresDto
    by_application: list[ApplicationCompletionDto]
    needs_attention: list[AttentionEntryDto]
    repeats: list[RepeatGroupDto]


class SkippedActionItemDto(ApiModel):
    action_item_id: str
    item_title: str
    reason: str  # an AcceptAllSkipReason


class AcceptAllActionItemsResponse(ApiModel):
    """What "accept all" did to the suggestions of one postmortem: the items now tracked, and the suggestions that need a person (with the reason)."""

    accepted: list[ActionItemDto]
    skipped: list[SkippedActionItemDto]

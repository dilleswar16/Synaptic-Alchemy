"""Action items as the API sends and receives them (spec 29, 4.5)."""

from __future__ import annotations

from datetime import date, datetime

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

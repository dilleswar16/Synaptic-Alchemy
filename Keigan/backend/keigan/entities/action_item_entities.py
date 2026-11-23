"""Action items: follow-up tasks after an incident, tracked to done (spec 29)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column
from keigan.entities.status_values import ActionItemPriority, ActionItemSource, ActionItemStatus, ActionItemType, ExternalSyncStatus, values_check


class ActionItem(AuditColumnsMixin, EntityBase):
    """One follow-up. The rows are the truth (the postmortem's table is rendered from them). The AI writes only a title and a suggested owner role in words; only a person sets the owner."""

    __tablename__ = "action_item"
    __table_args__ = (
        Index("ix_action_item_application_id_item_status_due_on", "application_id", "item_status", "due_on"),
        values_check("item_source_kind", ActionItemSource),
        values_check("action_type", ActionItemType),
        values_check("action_priority", ActionItemPriority),
        values_check("item_status", ActionItemStatus),
        values_check("external_sync_status", ExternalSyncStatus),
    )

    action_item_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    # NO ACTION on the next three: the application is the one cascade path; incident retention and stakeholder deletion release them first.
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    postmortem_id: Mapped[str | None] = mapped_column(ForeignKey("postmortem_report.postmortem_id"), index=True)
    incident_reference_text: Mapped[str | None] = mapped_column(String(60))  # the incident number when it was linked: shown after the incident has expired
    item_source_kind: Mapped[str] = mapped_column(String(30))
    source_record_id: Mapped[str | None] = mapped_column(String(36))  # the record a later spec's item came from; a recorded fact, not a link
    item_title: Mapped[str] = mapped_column(String(300))
    item_details_markdown: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(10))
    action_priority: Mapped[str] = mapped_column(String(10), default=ActionItemPriority.NORMAL)
    item_status: Mapped[str] = mapped_column(String(20))
    suggested_owner_role_text: Mapped[str | None] = mapped_column(String(200))
    owner_stakeholder_id: Mapped[str | None] = mapped_column(ForeignKey("stakeholder.stakeholder_id"), index=True)
    due_on: Mapped[date | None] = mapped_column(Date)  # a calendar date in the application's time zone
    original_due_on: Mapped[date | None] = mapped_column(Date)  # when the item was accepted or created; never changed afterwards
    due_on_change_count: Mapped[int] = mapped_column(Integer, default=0)
    status_reason_text: Mapped[str | None] = mapped_column(String(1000))
    completion_note_text: Mapped[str | None] = mapped_column(String(2000))
    completed_at: Mapped[datetime | None] = mapped_column()
    completed_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    accepted_at: Mapped[datetime | None] = mapped_column()
    accepted_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    external_reference_text: Mapped[str | None] = mapped_column(String(60))  # a task number typed by a person (spec 29, 4.7); writing to ServiceNow is a later step
    external_system: Mapped[str | None] = mapped_column(String(30))  # the system that tracks this item as a task (an open column, like record_system); null until it is sent
    external_record_identifier: Mapped[str | None] = mapped_column(String(100))  # that system's own id of the task (the ServiceNow sys_id)
    external_status_text: Mapped[str | None] = mapped_column(String(100))  # the task's state as that system last said it
    external_synced_at: Mapped[datetime | None] = mapped_column()
    external_sync_status: Mapped[str | None] = mapped_column(String(20))  # an ExternalSyncStatus; null = never sent. Once linked, that system owns the item's status
    last_reminded_at: Mapped[datetime | None] = mapped_column()
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

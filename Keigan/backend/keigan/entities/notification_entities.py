"""Notification entities: stakeholders, the delivery outbox and Teams incident chats."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now
from keigan.entities.linked_ids import LinkedIdsMixin, OrderedLinkColumns, linked_ids_property, ordered_links_relationship
from keigan.entities.status_values import DeliveryChannel, DeliveryStatus, Priority, StakeholderRecipientType, StakeholderRole, TeamsChatStatus, values_check


class Stakeholder(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("subscribed_service_links",)

    __tablename__ = "stakeholder"
    __table_args__ = (
        values_check("recipient_type", StakeholderRecipientType),
        values_check("stakeholder_role", StakeholderRole),
        values_check("minimum_priority", Priority),
    )

    stakeholder_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    recipient_type: Mapped[str] = mapped_column(String(20), default="person")
    display_name: Mapped[str] = mapped_column(String(200))
    email_address: Mapped[str | None] = mapped_column(String(320))
    user_principal_name: Mapped[str | None] = mapped_column(String(320))
    entra_object_id: Mapped[str | None] = mapped_column(String(36))
    teams_team_id: Mapped[str | None] = mapped_column(String(100))
    teams_channel_id: Mapped[str | None] = mapped_column(String(200))
    stakeholder_role: Mapped[str] = mapped_column(String(30), default="sre")
    subscribed_service_links: Mapped[list[StakeholderSubscribedService]] = ordered_links_relationship("StakeholderSubscribedService")
    subscribed_service_ids = linked_ids_property("subscribed_service_links")
    notification_channels_json: Mapped[list[str] | None] = mapped_column()
    minimum_priority: Mapped[str] = mapped_column(String(4), default="P2")
    subscribed_notification_types_json: Mapped[list[str] | None] = mapped_column()
    preferred_language_code: Mapped[str] = mapped_column(String(10), default="en")
    quiet_hours_json: Mapped[dict[str, Any] | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StakeholderSubscribedService(OrderedLinkColumns, EntityBase):
    """A service a stakeholder wants notifications about (an empty list means every service)."""

    __tablename__ = "stakeholder_subscribed_service"
    linked_id_attribute = "service_id"

    stakeholder_id: Mapped[str] = mapped_column(ForeignKey("stakeholder.stakeholder_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the stakeholder already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


class NotificationDelivery(EntityBase):
    __tablename__ = "notification_delivery"
    __table_args__ = (
        values_check("delivery_channel", DeliveryChannel),
        values_check("delivery_status", DeliveryStatus),
    )

    notification_delivery_id: Mapped[str] = identifier_column()
    # NO ACTION on the incident and investigation: the delivery cascades from its application and SQL Server allows one cascade path.
    application_id: Mapped[str | None] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigation.investigation_id"))
    notification_type: Mapped[str] = mapped_column(String(40))
    delivery_channel: Mapped[str] = mapped_column(String(30))
    recipient_address: Mapped[str] = mapped_column(String(600))
    subject_line: Mapped[str | None] = mapped_column(String(400))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    provider_message_identifier: Mapped[str | None] = mapped_column(String(400))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column()


class TeamsIncidentChat(EntityBase):
    __tablename__ = "teams_incident_chat"
    __table_args__ = (
        values_check("chat_status", TeamsChatStatus),
    )

    teams_incident_chat_id: Mapped[str] = identifier_column()
    # NO ACTION on the incident: the chat cascades from its application and SQL Server allows one cascade path.
    incident_id: Mapped[str] = mapped_column(ForeignKey("incident.incident_id"), unique=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    teams_chat_identifier: Mapped[str] = mapped_column(String(300))
    bot_conversation_reference_json: Mapped[dict[str, Any] | None] = mapped_column()
    chat_topic: Mapped[str] = mapped_column(String(300))
    chat_web_url: Mapped[str | None] = mapped_column(String(1000))
    member_user_principal_names_json: Mapped[list[str] | None] = mapped_column()
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    last_polled_at: Mapped[datetime | None] = mapped_column()
    last_processed_message_identifier: Mapped[str | None] = mapped_column(String(200))
    last_unprompted_comment_at: Mapped[datetime | None] = mapped_column()
    chat_status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


__all__ = ["NotificationDelivery", "Stakeholder", "StakeholderSubscribedService", "TeamsIncidentChat"]

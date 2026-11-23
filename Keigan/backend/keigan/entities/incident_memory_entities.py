"""Similar incident memory: what was learnt from past investigations, kept so a new one can be shown the ones that look alike (spec 34)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, UtcDateTime, identifier_column, utc_now
from keigan.entities.status_values import (
    IncidentMemoryCauseSource, IncidentMemoryEntryStatus, IncidentMemoryFixSource, IncidentMemoryKeyKind, IncidentMemoryRelevanceVerdict, values_check,
)


class IncidentMemoryEntry(AuditColumnsMixin, EntityBase):
    """One remembered incident: a masked, shortened account of its title, cause and fix, kept for as long as the incident is. One live entry per investigation."""

    __tablename__ = "incident_memory_entry"
    __table_args__ = (
        Index("ix_incident_memory_entry_application_id_entry_status_occurred_at", "application_id", "entry_status", "occurred_at"),
        values_check("entry_status", IncidentMemoryEntryStatus),
        values_check("cause_source", IncidentMemoryCauseSource),
        values_check("fix_source", IncidentMemoryFixSource),
    )

    incident_memory_entry_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"))
    # NO ACTION on the next two: the application is the one cascade path; incident retention deletes the entries before the investigations and incidents they point at.
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id"), unique=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incident.incident_id"), index=True)
    entry_status: Mapped[str] = mapped_column(String(20), default=IncidentMemoryEntryStatus.ACTIVE)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime)  # when the incident opened, else the start of the investigated window
    incident_title_text: Mapped[str] = mapped_column(String(500))  # masked
    cause_text: Mapped[str | None] = mapped_column(Text)  # masked and cut to INCIDENT_MEMORY_TEXT_MAXIMUM_CHARACTERS
    fix_text: Mapped[str | None] = mapped_column(Text)  # masked and cut to INCIDENT_MEMORY_TEXT_MAXIMUM_CHARACTERS
    cause_source: Mapped[str] = mapped_column(String(20), default=IncidentMemoryCauseSource.NONE)
    fix_source: Mapped[str] = mapped_column(String(20), default=IncidentMemoryFixSource.NONE)
    search_terms_json: Mapped[dict[str, Any]] = mapped_column(default=dict)  # term -> how many times, over the title, description, symptoms, cause and fix
    service_ids_json: Mapped[list[str]] = mapped_column(default=list)  # the services the entry was about, for the "service removed" check
    hidden_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    hidden_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    hide_reason_text: Mapped[str | None] = mapped_column(String(500))  # masked
    built_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)


class IncidentMemoryKey(EntityBase):
    """One fact of a remembered incident that another incident can share: a kind and a hash of the normalised value, plus a short readable form for "matched on ..."."""

    __tablename__ = "incident_memory_key"
    __table_args__ = (
        Index("ix_incident_memory_key_key_kind_key_value_hash", "key_kind", "key_value_hash"),
        values_check("key_kind", IncidentMemoryKeyKind),
    )

    incident_memory_entry_id: Mapped[str] = mapped_column(ForeignKey("incident_memory_entry.incident_memory_entry_id", ondelete="CASCADE"), primary_key=True)
    key_kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    key_value_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256 hex of the normalised value
    key_display_text: Mapped[str] = mapped_column(String(200))  # masked and shortened


class IncidentMemoryRelevanceFeedback(EntityBase):
    """One person's answer to "was this past incident relevant here?", for one suggestion on one investigation."""

    __tablename__ = "incident_memory_relevance_feedback"
    __table_args__ = (
        UniqueConstraint("investigation_id", "incident_memory_entry_id", "user_principal_name", name="uq_incident_memory_relevance_feedback_person"),
        values_check("relevance_verdict", IncidentMemoryRelevanceVerdict),
    )

    relevance_feedback_id: Mapped[str] = identifier_column()
    # NO ACTION on the investigation: deleting an investigation removes this row first (retention). CASCADE on the entry: a deleted entry takes its feedback with it.
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigation.investigation_id"), index=True)
    incident_memory_entry_id: Mapped[str] = mapped_column(ForeignKey("incident_memory_entry.incident_memory_entry_id", ondelete="CASCADE"), index=True)
    user_principal_name: Mapped[str] = mapped_column(String(320))
    relevance_verdict: Mapped[str] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)

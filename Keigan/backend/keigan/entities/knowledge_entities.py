"""Knowledge base entities: documents, chunks, AI-built topology, topology reviews and runbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now
from keigan.entities.linked_ids import LinkedIdsMixin, OrderedLinkColumns, linked_ids_property, ordered_links_relationship
from keigan.entities.status_values import DocumentDigestStatus, TopologyGenerationStatus, TopologyReviewStatus, TopologyReviewVerdict, values_check


class KnowledgeDocument(EntityBase):
    __tablename__ = "knowledge_document"
    __table_args__ = (
        values_check("ai_digest_status", DocumentDigestStatus),
    )

    knowledge_document_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("monitored_service.service_id"))
    document_title: Mapped[str] = mapped_column(String(300))
    document_category: Mapped[str] = mapped_column(String(40))
    original_file_name: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(120))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_path: Mapped[str] = mapped_column(String(600))
    file_sha256_hash: Mapped[str] = mapped_column(String(64))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_headings_json: Mapped[list[str] | None] = mapped_column()
    ai_digest_markdown: Mapped[str | None] = mapped_column(Text)
    ai_digest_status: Mapped[str] = mapped_column(String(20), default="pending")
    ai_digest_error_message: Mapped[str | None] = mapped_column(Text)
    possible_prompt_injection: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_token_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_user_principal_name: Mapped[str | None] = mapped_column(String(320))
    uploaded_at: Mapped[datetime] = mapped_column(default=utc_now)
    stale_after_at: Mapped[datetime | None] = mapped_column()


class KnowledgeChunk(EntityBase):
    __tablename__ = "knowledge_chunk"

    knowledge_chunk_id: Mapped[str] = identifier_column()
    knowledge_document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_document.knowledge_document_id", ondelete="CASCADE"), index=True
    )
    # NO ACTION: chunks already cascade from their document.
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("monitored_service.service_id"))
    chunk_sequence_number: Mapped[int] = mapped_column(Integer)
    section_heading: Mapped[str | None] = mapped_column(String(400))
    chunk_text: Mapped[str] = mapped_column(Text)
    estimated_token_count: Mapped[int] = mapped_column(Integer, default=0)
    search_terms_json: Mapped[dict[str, Any] | None] = mapped_column()


class ApplicationTopology(LinkedIdsMixin, EntityBase):
    link_relationship_names = ("source_document_links",)

    __tablename__ = "application_topology"
    __table_args__ = (
        values_check("generation_status", TopologyGenerationStatus),
        values_check("review_status", TopologyReviewStatus),
    )

    topology_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    topology_version_number: Mapped[int] = mapped_column(Integer, default=1)
    topology_graph_json: Mapped[dict[str, Any] | None] = mapped_column()
    understanding_summary_markdown: Mapped[str | None] = mapped_column(Text)
    source_document_links: Mapped[list[TopologySourceDocument]] = ordered_links_relationship("TopologySourceDocument")
    generated_from_document_ids = linked_ids_property("source_document_links")
    generation_status: Mapped[str] = mapped_column(String(20), default="building")
    generated_by_model_name: Mapped[str | None] = mapped_column(String(120))
    review_status: Mapped[str] = mapped_column(String(30), default="awaiting_review")
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class TopologySourceDocument(OrderedLinkColumns, EntityBase):
    """A document the topology was generated from."""

    __tablename__ = "topology_source_document"
    linked_id_attribute = "knowledge_document_id"

    topology_id: Mapped[str] = mapped_column(ForeignKey("application_topology.topology_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the topology already cascades from its application, and SQL Server allows one cascade path; deleting a document releases its rows.
    knowledge_document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.knowledge_document_id"), primary_key=True, index=True)


class TopologyReviewComment(EntityBase):
    __tablename__ = "topology_review_comment"
    __table_args__ = (
        values_check("review_verdict", TopologyReviewVerdict),
    )

    topology_review_comment_id: Mapped[str] = identifier_column()
    topology_id: Mapped[str] = mapped_column(ForeignKey("application_topology.topology_id", ondelete="CASCADE"), index=True)
    target_element_key: Mapped[str | None] = mapped_column(String(200))
    review_verdict: Mapped[str] = mapped_column(String(30))
    review_comment_text: Mapped[str | None] = mapped_column(Text)
    reviewer_user_principal_name: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Runbook(LinkedIdsMixin, AuditColumnsMixin, EntityBase):
    link_relationship_names = ("service_links",)

    __tablename__ = "runbook"

    runbook_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    runbook_title: Mapped[str] = mapped_column(String(300))
    trigger_symptoms_text: Mapped[str | None] = mapped_column(Text)
    runbook_steps_markdown: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(600))
    service_links: Mapped[list[RunbookAppliesToService]] = ordered_links_relationship("RunbookAppliesToService")
    applies_to_service_ids = linked_ids_property("service_links")
    knowledge_document_id: Mapped[str | None] = mapped_column(String(36))
    search_terms_json: Mapped[dict[str, Any] | None] = mapped_column()
    times_referenced_count: Mapped[int] = mapped_column(Integer, default=0)
    last_referenced_at: Mapped[datetime | None] = mapped_column()


class RunbookAppliesToService(OrderedLinkColumns, EntityBase):
    """A service a runbook applies to (an empty list means every service of the application)."""

    __tablename__ = "runbook_applies_to_service"
    linked_id_attribute = "service_id"

    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbook.runbook_id", ondelete="CASCADE"), primary_key=True)
    # NO ACTION: the runbook already cascades from its application, and SQL Server allows one cascade path; deleting a service releases its rows.
    service_id: Mapped[str] = mapped_column(ForeignKey("monitored_service.service_id"), primary_key=True, index=True)


__all__ = ["ApplicationTopology", "KnowledgeChunk", "KnowledgeDocument", "Runbook", "RunbookAppliesToService", "TopologyReviewComment", "TopologySourceDocument"]

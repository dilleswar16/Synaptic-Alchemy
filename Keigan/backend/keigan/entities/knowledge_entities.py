"""Knowledge base entities: documents, chunks, AI-built topology, topology reviews and runbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from keigan.entities.base_entity import AuditColumnsMixin, EntityBase, identifier_column, utc_now


class KnowledgeDocument(EntityBase):
    __tablename__ = "knowledge_document"

    knowledge_document_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str | None] = mapped_column(String(36))
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
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    service_id: Mapped[str | None] = mapped_column(String(36))
    chunk_sequence_number: Mapped[int] = mapped_column(Integer)
    section_heading: Mapped[str | None] = mapped_column(String(400))
    chunk_text: Mapped[str] = mapped_column(Text)
    estimated_token_count: Mapped[int] = mapped_column(Integer, default=0)
    search_terms_json: Mapped[dict[str, Any] | None] = mapped_column()


class ApplicationTopology(EntityBase):
    __tablename__ = "application_topology"

    topology_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    topology_version_number: Mapped[int] = mapped_column(Integer, default=1)
    topology_graph_json: Mapped[dict[str, Any] | None] = mapped_column()
    understanding_summary_markdown: Mapped[str | None] = mapped_column(Text)
    generated_from_document_ids_json: Mapped[list[str] | None] = mapped_column()
    generation_status: Mapped[str] = mapped_column(String(20), default="building")
    generated_by_model_name: Mapped[str | None] = mapped_column(String(120))
    review_status: Mapped[str] = mapped_column(String(30), default="awaiting_review")
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class TopologyReviewComment(EntityBase):
    __tablename__ = "topology_review_comment"

    topology_review_comment_id: Mapped[str] = identifier_column()
    topology_id: Mapped[str] = mapped_column(ForeignKey("application_topology.topology_id", ondelete="CASCADE"), index=True)
    target_element_key: Mapped[str | None] = mapped_column(String(200))
    review_verdict: Mapped[str] = mapped_column(String(30))
    review_comment_text: Mapped[str | None] = mapped_column(Text)
    reviewer_user_principal_name: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Runbook(AuditColumnsMixin, EntityBase):
    __tablename__ = "runbook"

    runbook_id: Mapped[str] = identifier_column()
    application_id: Mapped[str] = mapped_column(ForeignKey("application.application_id", ondelete="CASCADE"), index=True)
    runbook_title: Mapped[str] = mapped_column(String(300))
    trigger_symptoms_text: Mapped[str | None] = mapped_column(Text)
    runbook_steps_markdown: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(600))
    applies_to_service_ids_json: Mapped[list[str] | None] = mapped_column()
    knowledge_document_id: Mapped[str | None] = mapped_column(String(36))
    search_terms_json: Mapped[dict[str, Any] | None] = mapped_column()
    times_referenced_count: Mapped[int] = mapped_column(Integer, default=0)
    last_referenced_at: Mapped[datetime | None] = mapped_column()


__all__ = ["ApplicationTopology", "KnowledgeChunk", "KnowledgeDocument", "Runbook", "TopologyReviewComment"]

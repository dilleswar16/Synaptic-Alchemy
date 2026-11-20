"""Knowledge base: capture prompt, documents, topology and runbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel

DocumentCategory = Literal["code_context", "architecture", "operations_guide", "runbook_source", "incident_history", "other"]
DOCUMENT_CATEGORIES = ("code_context", "architecture", "operations_guide", "runbook_source", "incident_history", "other")


class CapturePromptResponse(ApiModel):
    prompt_markdown: str
    line_count: int
    version: str
    suggested_file_name: str


class KnowledgeDocumentResponse(ApiModel):
    knowledge_document_id: str
    application_id: str
    service_id: str | None = None
    service_name: str | None = None
    document_title: str
    document_category: str
    original_file_name: str
    content_type: str
    file_size_bytes: int
    headings: list[str] = []
    ai_digest_status: str
    ai_digest_error_message: str | None = None
    possible_prompt_injection: bool = False
    estimated_token_count: int = 0
    uploaded_by_user_principal_name: str | None = None
    uploaded_at: datetime
    stale_after_at: datetime | None = None
    is_stale: bool = False


class KnowledgeDocumentDetailResponse(KnowledgeDocumentResponse):
    ai_digest_markdown: str | None = None
    extracted_text_excerpt: str | None = None
    chunk_count: int = 0


class DocumentUploadResponse(ApiModel):
    document: KnowledgeDocumentResponse
    job_id: str
    status: str = "queued"


# ── Topology ───────────────────────────────────────────────────────────────────
class TopologyNodeResponse(ApiModel):
    node_key: str
    label: str
    node_type: str
    service_id: str | None = None
    technology: str | None = None
    description: str | None = None
    criticality: str | None = None
    review_verdict: str | None = None
    review_comment_text: str | None = None


class TopologyEdgeResponse(ApiModel):
    edge_key: str
    source_node_key: str
    target_node_key: str
    relationship: str
    protocol: str | None = None
    description: str | None = None
    review_verdict: str | None = None
    review_comment_text: str | None = None


class TopologyVersionResponse(ApiModel):
    topology_id: str
    topology_version_number: int
    generation_status: str
    review_status: str
    is_current_version: bool
    generated_by_model_name: str | None = None
    created_at: datetime


class TopologyDetailResponse(TopologyVersionResponse):
    nodes: list[TopologyNodeResponse] = []
    edges: list[TopologyEdgeResponse] = []
    understanding_summary_markdown: str | None = None
    uncertainties: list[str] = []
    generated_from_document_ids: list[str] = []


class TopologyResponse(ApiModel):
    current: TopologyDetailResponse | None = None
    versions: list[TopologyVersionResponse] = []
    build_in_progress: bool = False


class TopologyReviewRequest(ApiModel):
    target_element_key: str | None = Field(default=None, max_length=200, description="Node key, edge key (source->target) or empty for the whole graph.")
    review_verdict: Literal["looks_right", "needs_correction", "comment"]
    review_comment_text: str | None = Field(default=None, max_length=2000)


class TopologyReviewResponse(ApiModel):
    topology_review_comment_id: str
    topology_id: str
    target_element_key: str | None = None
    review_verdict: str
    review_comment_text: str | None = None
    reviewer_user_principal_name: str
    created_at: datetime
    topology_review_status: str


# ── Runbooks ───────────────────────────────────────────────────────────────────
class RunbookCreateRequest(ApiModel):
    runbook_title: str = Field(min_length=2, max_length=300)
    trigger_symptoms_text: str | None = None
    runbook_steps_markdown: str | None = None
    source_url: str | None = Field(default=None, max_length=600)
    applies_to_service_ids: list[str] = []
    knowledge_document_id: str | None = None


class RunbookUpdateRequest(ApiModel):
    runbook_title: str | None = Field(default=None, min_length=2, max_length=300)
    trigger_symptoms_text: str | None = None
    runbook_steps_markdown: str | None = None
    source_url: str | None = None
    applies_to_service_ids: list[str] | None = None
    knowledge_document_id: str | None = None


class RunbookResponse(ApiModel):
    runbook_id: str
    application_id: str
    runbook_title: str
    trigger_symptoms_text: str | None = None
    runbook_steps_markdown: str | None = None
    source_url: str | None = None
    applies_to_service_ids: list[str] = []
    applies_to_service_names: list[str] = []
    knowledge_document_id: str | None = None
    times_referenced_count: int = 0
    last_referenced_at: datetime | None = None
    updated_at: datetime
    created_by_user_principal_name: str | None = None


GraphDictionary = dict[str, Any]

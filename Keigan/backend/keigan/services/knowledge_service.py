"""Knowledge base: documents, digests, chunks, lexical retrieval and grounding context.

The public contract methods (``build_grounding_context``, ``find_matching_runbooks``, ``get_current_topology_graph``,
``record_runbook_references``) are used by investigations, chat and jobs: keep their names, arguments and return types.
Topology building lives in ``TopologyService`` and runbook CRUD in ``RunbookService``.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ai_safety_settings import FlaggedDocumentPolicy, get_ai_safety_settings
from keigan.ai.knowledge_ai_schemas import DocumentDigestResult
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection, estimate_token_count
from keigan.ai.prompt_safety import assess_prompt_injection
from keigan.ai.user_facing_errors import describe_failure_for_user
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.dtos.knowledge_dtos import (
    DOCUMENT_CATEGORIES,
    CapturePromptResponse,
    DocumentUploadResponse,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentResponse,
)
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.knowledge_entities import ApplicationTopology, KnowledgeChunk, KnowledgeDocument, Runbook
from keigan.exceptions.keigan_exceptions import (
    BusinessValidationException,
    ConflictException,
    KeiganException,
    NotFoundException,
)
from keigan.integrations.file_storage import build_storage_path
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.reference_release import release_references
from keigan.utils.pii_masker import MaskingContext, PiiMasker
from keigan.utils.text_utils import chunk_markdown, extract_markdown_headings, rank_with_bm25, term_frequencies, truncate_text
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue
from keigan.entities.status_values import DocumentDigestStatus, TopologyGenerationStatus

logger = logging.getLogger(__name__)
STALE_AFTER_DAYS = 90
MAXIMUM_EXTRACTED_CHARACTERS = 400_000
DIGEST_INPUT_CHARACTERS = 24_000
CONTENT_TYPE_BY_EXTENSION = {
    ".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
FILE_NAME_UNSAFE_PATTERN = re.compile(r"[^\w.\- ]+")


@dataclass
class KnowledgeReference:
    reference_code: str  # K1, K2 … (cited as [K1] by the AI)
    title: str
    source_kind: str  # topology | document_digest | document_chunk | cmdb_record
    knowledge_document_id: str | None = None
    section_heading: str | None = None


@dataclass
class GroundingContext:
    """Knowledge text to put in an AI prompt, already within the requested token budget."""

    topology_summary_markdown: str = ""
    knowledge_markdown: str = ""  # sections labelled [K1], [K2] …
    references: list[KnowledgeReference] = field(default_factory=list)
    estimated_token_count: int = 0
    # True when a document in this text was flagged as a possible prompt injection (policy "warn"); the prompt block then carries a warning.
    contains_flagged_content: bool = False


@dataclass
class RunbookMatch:
    reference_code: str  # R1, R2 …
    runbook_id: str
    runbook_title: str
    trigger_symptoms_text: str
    runbook_steps_markdown: str
    match_score: float


def _has_valid_magic_bytes(file_extension: str, file_bytes: bytes) -> bool:
    if file_extension == ".pdf":
        return file_bytes.startswith(b"%PDF-")
    if file_extension == ".png":
        return file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if file_extension in (".jpg", ".jpeg"):
        return file_bytes.startswith(b"\xff\xd8\xff")
    if file_extension == ".webp":
        return file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"
    if file_extension in TEXT_EXTENSIONS:
        if b"\x00" in file_bytes[:8192]:
            return False
        try:
            file_bytes[:65536].decode("utf-8", errors="strict")
        except UnicodeDecodeError as decode_error:
            return decode_error.start >= 65530  # a multi-byte character cut by the slice is fine
        return True
    return False


def format_digest_markdown(digest: DocumentDigestResult) -> str:
    sections = [("Purpose", [digest.purpose_summary]), ("Key facts", digest.key_facts), ("Outbound dependencies", digest.outbound_dependencies),
                ("Known failure modes", digest.known_failure_modes), ("Operational commands", digest.operational_commands),
                ("Logging and telemetry", digest.log_and_telemetry_hints)]
    lines: list[str] = []
    for heading, items in sections:
        if items:
            lines.append(f"### {heading}")
            lines.extend(item if heading == "Purpose" else f"- {item}" for item in items)
            lines.append("")
    return "\n".join(lines).strip()


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.document_repository = BaseRepository(session, KnowledgeDocument)
        self.audit_service = AuditService(session)

    # ── Capture prompt ─────────────────────────────────────────────────────────
    async def get_capture_prompt(self, application_id: str, service_id: str | None) -> CapturePromptResponse:
        application = await BaseRepository(self.session, Application).get_required(application_id, "application")
        library = application_context.prompt_library()
        if service_id:
            service = await self._get_service(application_id, service_id)
            scope_description = f'the service "{service.service_name}" ({service.service_type}) of the application "{application.application_name}" ({application.application_code})'
            file_slug = re.sub(r"[^a-z0-9]+", "-", service.service_name.lower()).strip("-")
        else:
            scope_description = f'the application "{application.application_name}" ({application.application_code}), covering every deployable service in this repository'
            file_slug = application.application_code.lower()
        prompt_markdown = library.render("knowledge_capture_prompt", scope_description=scope_description, file_slug=file_slug)
        return CapturePromptResponse(
            prompt_markdown=prompt_markdown,
            line_count=prompt_markdown.count("\n") + 1,
            version=library.version_of("knowledge_capture_prompt"),
            suggested_file_name=f"keigan-knowledge-{file_slug}.md",
        )

    # ── Documents ──────────────────────────────────────────────────────────────
    async def list_documents(self, application_id: str) -> list[KnowledgeDocumentResponse]:
        documents = await self.document_repository.find_all(KnowledgeDocument.application_id == application_id, order_by=KnowledgeDocument.uploaded_at.desc())
        service_names = await self._service_names(application_id)
        return [self._to_response(document, service_names) for document in documents]

    async def get_document(self, application_id: str, knowledge_document_id: str) -> KnowledgeDocumentDetailResponse:
        document = await self._get_document(application_id, knowledge_document_id)
        service_names = await self._service_names(application_id)
        chunk_count = len((await self.session.scalars(select(KnowledgeChunk.knowledge_chunk_id).where(KnowledgeChunk.knowledge_document_id == knowledge_document_id))).all())
        return KnowledgeDocumentDetailResponse(
            **self._to_response(document, service_names).model_dump(),
            ai_digest_markdown=document.ai_digest_markdown,
            extracted_text_excerpt=truncate_text(document.extracted_text, 6000),
            chunk_count=chunk_count,
        )

    async def upload_document(
        self, current_user: CurrentUser, application_id: str, upload_file: UploadFile, service_id: str | None, document_category: str, document_title: str | None
    ) -> DocumentUploadResponse:
        if document_category not in DOCUMENT_CATEGORIES:
            raise BusinessValidationException("The document category is not known.", field_errors=[{"field": "documentCategory", "message": f"Use one of {', '.join(DOCUMENT_CATEGORIES)}."}])
        if service_id:
            await self._get_service(application_id, service_id)
        safe_file_name = FILE_NAME_UNSAFE_PATTERN.sub("_", Path(upload_file.filename or "upload").name).strip(" .")[:200] or "upload"
        file_extension = Path(safe_file_name).suffix.lower()
        if file_extension not in CONTENT_TYPE_BY_EXTENSION:
            raise BusinessValidationException(
                "This file type is not supported.", field_errors=[{"field": "file", "message": "Upload .md, .markdown, .txt, .pdf, .png, .jpg, .jpeg or .webp files."}]
            )
        file_bytes = await upload_file.read(self.settings.max_upload_bytes + 1)
        if len(file_bytes) > self.settings.max_upload_bytes:
            raise BusinessValidationException(f"The file is larger than {self.settings.max_upload_bytes // (1024 * 1024)} MB.", field_errors=[{"field": "file", "message": "File too large."}])
        if not file_bytes or not _has_valid_magic_bytes(file_extension, file_bytes):
            raise BusinessValidationException("The file content does not match its type.", field_errors=[{"field": "file", "message": "The file looks damaged or is not a real " + file_extension + " file."}])
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        duplicate = await self.document_repository.find_one(KnowledgeDocument.application_id == application_id, KnowledgeDocument.file_sha256_hash == file_hash)
        if duplicate is not None:
            raise ConflictException(f'This file was already uploaded as "{duplicate.document_title}".')
        storage_path = build_storage_path(application_id, safe_file_name)
        content_type = CONTENT_TYPE_BY_EXTENSION[file_extension]
        await application_context.file_storage().save_file(storage_path, file_bytes, content_type)
        now = utc_now()
        document = await self.document_repository.add(
            KnowledgeDocument(
                application_id=application_id,
                service_id=service_id,
                document_title=(document_title or Path(safe_file_name).stem)[:300],
                document_category=document_category,
                original_file_name=safe_file_name,
                content_type=content_type,
                file_size_bytes=len(file_bytes),
                storage_path=storage_path,
                file_sha256_hash=file_hash,
                ai_digest_status=DocumentDigestStatus.PENDING,
                uploaded_by_user_principal_name=current_user.user_principal_name,
                uploaded_at=now,
                stale_after_at=now + timedelta(days=STALE_AFTER_DAYS),
            )
        )
        job_id = await JobQueue(self.session).enqueue("digest_knowledge_document", {"knowledge_document_id": document.knowledge_document_id}, deduplication_key=f"digest:{document.knowledge_document_id}")
        await self.audit_service.record(
            current_user, "knowledge.upload", target_entity_type="knowledge_document", target_entity_id=document.knowledge_document_id, application_id=application_id,
            action_details={"fileName": safe_file_name, "category": document_category, "sizeBytes": len(file_bytes)},
        )
        return DocumentUploadResponse(document=self._to_response(document, await self._service_names(application_id)), job_id=job_id)

    async def delete_document(self, current_user: CurrentUser, application_id: str, knowledge_document_id: str) -> None:
        document = await self._get_document(application_id, knowledge_document_id)
        try:
            await application_context.file_storage().delete_file(document.storage_path)
        except KeiganException:
            pass  # the database row is what matters; an already-missing file must not block deletion
        await self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == knowledge_document_id))
        await self.session.execute(update(Runbook).where(Runbook.knowledge_document_id == knowledge_document_id).values(knowledge_document_id=None))
        await self.audit_service.record(
            current_user, "knowledge.delete", target_entity_type="knowledge_document", target_entity_id=knowledge_document_id, application_id=application_id,
            action_details={"fileName": document.original_file_name},
        )
        await release_references(self.session, KnowledgeDocument.knowledge_document_id, [knowledge_document_id])
        await self.document_repository.delete(document)

    async def read_document_content(self, application_id: str, knowledge_document_id: str) -> tuple[bytes, str, str]:
        document = await self._get_document(application_id, knowledge_document_id)
        return await application_context.file_storage().read_file(document.storage_path), document.content_type, document.original_file_name

    # ── Digest job ─────────────────────────────────────────────────────────────
    async def digest_document(self, knowledge_document_id: str) -> dict[str, Any] | None:
        document = await self.document_repository.get_by_id(knowledge_document_id)
        if document is None:
            return None
        document.ai_digest_status = DocumentDigestStatus.RUNNING
        document.ai_digest_error_message = None
        await self.session.flush()
        usage_context = LlmUsageContext(application_id=document.application_id, requested_by_user_principal_name=document.uploaded_by_user_principal_name)
        try:
            file_bytes = await application_context.file_storage().read_file(document.storage_path)
            raw_text = await self._extract_text(document, file_bytes, usage_context)
        except Exception as extraction_error:  # noqa: BLE001  (any extraction problem is shown on the file card)
            document.ai_digest_status = DocumentDigestStatus.FAILED
            logger.warning("Could not read knowledge document %s: %s", knowledge_document_id, extraction_error)
            document.ai_digest_error_message = "Keigan could not read this file. Check that it is a valid document that is not password protected, then upload it again."
            return {"status": "failed"}
        masker = PiiMasker(MaskingContext())
        extracted_text = masker.mask_text(truncate_text(raw_text, MAXIMUM_EXTRACTED_CHARACTERS, ""))
        if not extracted_text.strip():
            document.ai_digest_status = DocumentDigestStatus.FAILED
            document.ai_digest_error_message = "No readable text was found in this file."
            return {"status": "failed"}
        document.extracted_text = extracted_text
        document.extracted_headings_json = extract_markdown_headings(extracted_text)
        document.estimated_token_count = estimate_token_count(extracted_text)
        document.possible_prompt_injection = assess_prompt_injection(extracted_text).is_suspicious
        await self._replace_chunks(document, extracted_text)
        await self._write_digest(document, extracted_text, usage_context)
        return {"status": document.ai_digest_status, "tokenCount": document.estimated_token_count}

    async def _extract_text(self, document: KnowledgeDocument, file_bytes: bytes, usage_context: LlmUsageContext) -> str:
        file_extension = Path(document.original_file_name).suffix.lower()
        if file_extension in TEXT_EXTENSIONS:
            return file_bytes.decode("utf-8", errors="replace")
        if file_extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(file_bytes))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages[:200])
        instruction = application_context.prompt_library().render("architecture_image_description")
        description = await application_context.llm_gateway().describe_image(
            image_bytes=file_bytes, content_type=document.content_type, instruction=instruction, usage_context=usage_context
        )
        return f"# {document.document_title}\n\n## Architecture diagram description\n\n{description.text}"

    async def _replace_chunks(self, document: KnowledgeDocument, extracted_text: str) -> None:
        await self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == document.knowledge_document_id))
        for sequence_number, chunk in enumerate(chunk_markdown(extracted_text)):
            self.session.add(
                KnowledgeChunk(
                    knowledge_document_id=document.knowledge_document_id,
                    application_id=document.application_id,
                    service_id=document.service_id,
                    chunk_sequence_number=sequence_number,
                    section_heading=chunk.section_heading,
                    chunk_text=chunk.chunk_text,
                    estimated_token_count=estimate_token_count(chunk.chunk_text),
                    search_terms_json=term_frequencies(f"{chunk.section_heading or ''} {chunk.chunk_text}"),
                )
            )
        await self.session.flush()

    async def _write_digest(self, document: KnowledgeDocument, extracted_text: str, usage_context: LlmUsageContext) -> None:
        application = await self.session.get(Application, document.application_id)
        gateway = application_context.llm_gateway()
        try:
            digest = await gateway.generate_structured(
                feature_name="knowledge_document_digest",
                model_tier=ModelTier.FAST,
                system_prompt=application_context.prompt_library().render("knowledge_document_digest", application_name=application.application_name if application else "the application"),
                prompt_sections=[
                    PromptSection("Document", truncate_text(extracted_text, DIGEST_INPUT_CHARACTERS), is_untrusted=True, source_label=f"knowledge:{document.original_file_name}"),
                    PromptSection("Task", "Write the structured digest of the document above."),
                ],
                output_schema=DocumentDigestResult,
                usage_context=usage_context,
            )
            document.ai_digest_markdown = format_digest_markdown(digest)
            document.ai_digest_status = DocumentDigestStatus.READY
        except KeiganException as digest_error:
            document.ai_digest_status = DocumentDigestStatus.FAILED
            document.ai_digest_error_message = f"The AI digest could not be written: {describe_failure_for_user(digest_error)} The text is still searchable."
        except Exception as digest_error:  # noqa: BLE001
            document.ai_digest_status = DocumentDigestStatus.FAILED
            logger.warning("Digest of knowledge document %s failed: %s", document.knowledge_document_id, digest_error)
            document.ai_digest_error_message = "The AI digest could not be written. The text is still searchable."

    # ── Contract: grounding, runbooks, topology graph ──────────────────────────
    async def build_grounding_context(
        self, application_id: str, query_text: str, service_ids: list[str] | None = None, token_budget: int | None = None
    ) -> GroundingContext:
        """Topology summary + relevant digests + top BM25 chunks for ``query_text``, labelled [K1]… within ``token_budget``."""
        remaining_budget = token_budget or self.settings.investigation_knowledge_token_budget
        context = GroundingContext()
        service_id_set = set(service_ids or [])
        reference_counter = 0

        def next_reference(title: str, source_kind: str, document_id: str | None = None, heading: str | None = None) -> str:
            nonlocal reference_counter
            reference_counter += 1
            code = f"K{reference_counter}"
            context.references.append(KnowledgeReference(code, title, source_kind, document_id, heading))
            return code

        topology = await self._current_topology(application_id)
        knowledge_sections: list[str] = []
        if topology is not None and topology.generation_status == TopologyGenerationStatus.READY:
            topology_text = self._topology_summary_text(topology)
            topology_text = truncate_text(topology_text, max(400, remaining_budget // 4) * 4)
            code = next_reference("Application topology", "topology")
            context.topology_summary_markdown = f"[{code}] Application topology\n{topology_text}"
            remaining_budget -= estimate_token_count(context.topology_summary_markdown)

        all_documents = await self.document_repository.find_all(KnowledgeDocument.application_id == application_id, KnowledgeDocument.ai_digest_status == DocumentDigestStatus.READY)
        flagged_document_ids = {document.knowledge_document_id for document in await self.document_repository.find_all(
            KnowledgeDocument.application_id == application_id, KnowledgeDocument.possible_prompt_injection.is_(True))}
        if get_ai_safety_settings().ai_flagged_document_policy == FlaggedDocumentPolicy.EXCLUDE:
            documents = [document for document in all_documents if document.knowledge_document_id not in flagged_document_ids]
        else:
            documents = all_documents
        used_document_ids: set[str] = set()
        relevant_documents = [document for document in documents if document.ai_digest_markdown and (not service_id_set or document.service_id is None or document.service_id in service_id_set)]
        relevant_documents.sort(key=lambda document: (document.service_id not in service_id_set, document.uploaded_at))
        digest_budget = remaining_budget * 35 // 100
        for document in relevant_documents:
            digest_text = truncate_text(document.ai_digest_markdown, 1800)
            digest_tokens = estimate_token_count(digest_text)
            if digest_tokens > digest_budget:
                break
            code = next_reference(document.document_title, "document_digest", document.knowledge_document_id)
            knowledge_sections.append(f"[{code}] Digest of {document.document_title}\n{digest_text}")
            used_document_ids.add(document.knowledge_document_id)
            digest_budget -= digest_tokens
            remaining_budget -= digest_tokens

        chunk_rows = await BaseRepository(self.session, KnowledgeChunk).find_all(KnowledgeChunk.application_id == application_id)
        excluded_document_ids = flagged_document_ids if get_ai_safety_settings().ai_flagged_document_policy == FlaggedDocumentPolicy.EXCLUDE else set()
        eligible_chunks = {
            chunk.knowledge_chunk_id: chunk for chunk in chunk_rows
            if chunk.search_terms_json and chunk.knowledge_document_id not in excluded_document_ids and (not service_id_set or chunk.service_id is None or chunk.service_id in service_id_set)
        }
        if query_text.strip() and eligible_chunks:
            titles_by_document_id = {document.knowledge_document_id: document.document_title for document in documents}
            ranked_chunks = rank_with_bm25(query_text, {key: chunk.search_terms_json or {} for key, chunk in eligible_chunks.items()}, maximum_results=12)
            for ranked_chunk in ranked_chunks:
                chunk = eligible_chunks[ranked_chunk.document_key]
                chunk_text = truncate_text(chunk.chunk_text, 2400)
                chunk_tokens = estimate_token_count(chunk_text)
                if chunk_tokens > remaining_budget:
                    continue
                document_title = titles_by_document_id.get(chunk.knowledge_document_id, "Knowledge document")
                code = next_reference(document_title, "document_chunk", chunk.knowledge_document_id, chunk.section_heading)
                knowledge_sections.append(f"[{code}] {document_title} — {chunk.section_heading or 'excerpt'}\n{chunk_text}")
                used_document_ids.add(chunk.knowledge_document_id)
                remaining_budget -= chunk_tokens
        context.knowledge_markdown = "\n\n".join(knowledge_sections)
        context.contains_flagged_content = bool(used_document_ids & flagged_document_ids)
        context.estimated_token_count = estimate_token_count(context.topology_summary_markdown) + estimate_token_count(context.knowledge_markdown)
        return context

    async def find_matching_runbooks(
        self, application_id: str, symptom_text: str, service_ids: list[str] | None = None, maximum_results: int = 3
    ) -> list[RunbookMatch]:
        """Lexical match of symptoms against runbook titles and trigger symptoms, labelled [R1]…"""
        runbooks = await BaseRepository(self.session, Runbook).find_all(Runbook.application_id == application_id)
        service_id_set = set(service_ids or [])
        eligible = {
            runbook.runbook_id: runbook
            for runbook in runbooks
            if not service_id_set or not runbook.applies_to_service_ids or service_id_set & set(runbook.applies_to_service_ids)
        }
        term_sets = {key: runbook.search_terms_json or term_frequencies(f"{runbook.runbook_title} {runbook.trigger_symptoms_text or ''}") for key, runbook in eligible.items()}
        ranked_runbooks = rank_with_bm25(symptom_text, term_sets, maximum_results=maximum_results)
        top_score = ranked_runbooks[0].score if ranked_runbooks else 1.0
        return [
            RunbookMatch(
                reference_code=f"R{position}",
                runbook_id=ranked.document_key,
                runbook_title=eligible[ranked.document_key].runbook_title,
                trigger_symptoms_text=eligible[ranked.document_key].trigger_symptoms_text or "",
                runbook_steps_markdown=eligible[ranked.document_key].runbook_steps_markdown or "",
                match_score=round(ranked.score / top_score, 3),
            )
            for position, ranked in enumerate(ranked_runbooks, start=1)
        ]

    async def get_current_topology_graph(self, application_id: str) -> dict[str, Any] | None:
        """``topology_graph_json`` of the current topology version (nodes/edges), or None."""
        topology = await self._current_topology(application_id)
        return topology.topology_graph_json if topology is not None else None

    async def record_runbook_references(self, runbook_ids: list[str]) -> None:
        """Increment ``times_referenced_count`` for runbooks used in an investigation."""
        if not runbook_ids:
            return
        runbooks = await BaseRepository(self.session, Runbook).find_all(Runbook.runbook_id.in_(runbook_ids))
        for runbook in runbooks:
            runbook.times_referenced_count = (runbook.times_referenced_count or 0) + 1
            runbook.last_referenced_at = utc_now()
        await self.session.flush()

    # ── Job handler delegating to the topology service ─────────────────────────
    async def build_topology(self, application_id: str, requested_by_user_principal_name: str | None = None) -> dict[str, Any] | None:
        from keigan.services.topology_service import TopologyService

        return await TopologyService(self.session).build_topology(application_id, requested_by_user_principal_name)

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _current_topology(self, application_id: str) -> ApplicationTopology | None:
        return await BaseRepository(self.session, ApplicationTopology).find_one(
            ApplicationTopology.application_id == application_id, ApplicationTopology.is_current_version.is_(True)
        )

    @staticmethod
    def _topology_summary_text(topology: ApplicationTopology) -> str:
        graph = topology.topology_graph_json or {}
        labels = {node["node_key"]: node["label"] for node in graph.get("nodes", [])}
        edge_lines = [
            f"- {labels.get(edge['source_node_key'], edge['source_node_key'])} {edge.get('relationship', 'calls')} {labels.get(edge['target_node_key'], edge['target_node_key'])}"
            for edge in graph.get("edges", [])
        ]
        node_lines = [f"- {node['label']} ({node.get('node_type', 'service')}{', ' + node['technology'] if node.get('technology') else ''})" for node in graph.get("nodes", [])]
        return "\n".join([topology.understanding_summary_markdown or "", "Nodes:", *node_lines, "Relationships:", *edge_lines]).strip()

    async def _get_document(self, application_id: str, knowledge_document_id: str) -> KnowledgeDocument:
        document = await self.document_repository.get_required(knowledge_document_id, "document")
        if document.application_id != application_id:
            raise NotFoundException("The document was not found.")
        return document

    async def _get_service(self, application_id: str, service_id: str) -> MonitoredService:
        service = await BaseRepository(self.session, MonitoredService).get_required(service_id, "service")
        if service.application_id != application_id:
            raise NotFoundException("The service was not found.")
        return service

    async def _service_names(self, application_id: str) -> dict[str, str]:
        return dict((await self.session.execute(select(MonitoredService.service_id, MonitoredService.service_name).where(MonitoredService.application_id == application_id))).all())

    @staticmethod
    def _to_response(document: KnowledgeDocument, service_names: dict[str, str]) -> KnowledgeDocumentResponse:
        return KnowledgeDocumentResponse(
            knowledge_document_id=document.knowledge_document_id,
            application_id=document.application_id,
            service_id=document.service_id,
            service_name=service_names.get(document.service_id or ""),
            document_title=document.document_title,
            document_category=document.document_category,
            original_file_name=document.original_file_name,
            content_type=document.content_type,
            file_size_bytes=document.file_size_bytes,
            headings=document.extracted_headings_json or [],
            ai_digest_status=document.ai_digest_status,
            ai_digest_error_message=document.ai_digest_error_message,
            possible_prompt_injection=document.possible_prompt_injection,
            estimated_token_count=document.estimated_token_count,
            uploaded_by_user_principal_name=document.uploaded_by_user_principal_name,
            uploaded_at=document.uploaded_at,
            stale_after_at=document.stale_after_at,
            is_stale=bool(document.stale_after_at and document.stale_after_at < utc_now()),
        )

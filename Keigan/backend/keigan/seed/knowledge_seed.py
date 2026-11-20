"""Demo knowledge: code-context documents with digests, runbooks, topologies (one reviewed, the rest awaiting review), record links and placeholder integrations."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.entities.application_entities import ApplicationRecordLink, ExternalIntegration
from keigan.entities.knowledge_entities import ApplicationTopology, KnowledgeDocument, Runbook, TopologyReviewComment
from keigan.integrations.file_storage import build_storage_path
from keigan.seed.foundation_seed import SeedContext
from keigan.seed.knowledge_seed_content import DEMO_DOCUMENTS, DEMO_RECORD_LINKS, DEMO_RUNBOOKS
from keigan.services.knowledge_service import KnowledgeService
from keigan.services.runbook_service import RunbookService
from keigan.services.topology_service import TopologyService
from keigan.utils.time_utils import utc_now

SEED_ORDER = 10
SEED_ACTOR = "system:seed"
REVIEWER = "aiko.appadmin@keigan.local"
logger = logging.getLogger(__name__)


async def seed(session: AsyncSession, seed_context: SeedContext) -> None:
    await _seed_documents(session, seed_context)
    await _seed_runbooks(session, seed_context)
    await _seed_topologies(session, seed_context)
    await _seed_record_links_and_integrations(session, seed_context)


async def _seed_documents(session: AsyncSession, seed_context: SeedContext) -> None:
    knowledge_service = KnowledgeService(session)
    for application_code, service_name, document_title, file_name, markdown_text in DEMO_DOCUMENTS:
        application_id = seed_context.application_ids_by_code.get(application_code)
        if application_id is None:
            continue
        file_bytes = markdown_text.encode("utf-8")
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        if await session.scalar(select(KnowledgeDocument.knowledge_document_id).where(KnowledgeDocument.application_id == application_id, KnowledgeDocument.file_sha256_hash == file_hash)):
            continue
        storage_path = build_storage_path(application_id, file_name)
        await application_context.file_storage().save_file(storage_path, file_bytes, "text/markdown")
        uploaded_at = utc_now() - timedelta(days=12)
        document = KnowledgeDocument(
            application_id=application_id,
            service_id=seed_context.service_ids_by_key.get(f"{application_code}/{service_name}"),
            document_title=document_title,
            document_category="code_context",
            original_file_name=file_name,
            content_type="text/markdown",
            file_size_bytes=len(file_bytes),
            storage_path=storage_path,
            file_sha256_hash=file_hash,
            ai_digest_status="pending",
            uploaded_by_user_principal_name=REVIEWER,
            uploaded_at=uploaded_at,
            stale_after_at=uploaded_at + timedelta(days=90),
        )
        session.add(document)
        await session.flush()
        try:
            await knowledge_service.digest_document(document.knowledge_document_id)
        except Exception:  # noqa: BLE001  (a missing LLM key must not stop seeding)
            logger.exception("Digest of seeded document %s failed", file_name)
            document.ai_digest_status = "failed"


async def _seed_runbooks(session: AsyncSession, seed_context: SeedContext) -> None:
    for application_code, title, symptoms, steps_markdown, service_names in DEMO_RUNBOOKS:
        application_id = seed_context.application_ids_by_code.get(application_code)
        if application_id is None:
            continue
        if await session.scalar(select(Runbook.runbook_id).where(Runbook.application_id == application_id, Runbook.runbook_title == title)):
            continue
        runbook = Runbook(
            application_id=application_id,
            runbook_title=title,
            trigger_symptoms_text=symptoms,
            runbook_steps_markdown=steps_markdown,
            created_by_user_principal_name=SEED_ACTOR,
            updated_by_user_principal_name=SEED_ACTOR,
        )
        runbook.replace_linked_ids("service_links", [seed_context.service_ids_by_key[key] for name in service_names if (key := f"{application_code}/{name}") in seed_context.service_ids_by_key])
        RunbookService._refresh_search_terms(runbook)
        session.add(runbook)
    await session.flush()


async def _seed_topologies(session: AsyncSession, seed_context: SeedContext) -> None:
    topology_service = TopologyService(session)
    for application_code, application_id in seed_context.application_ids_by_code.items():
        if await session.scalar(select(func.count()).select_from(ApplicationTopology).where(ApplicationTopology.application_id == application_id)):
            continue
        try:
            await topology_service.build_topology(application_id, SEED_ACTOR)
        except Exception:  # noqa: BLE001
            logger.exception("Topology seed for %s failed", application_code)
            continue
        if application_code == "CLMJP":
            topology = await session.scalar(select(ApplicationTopology).where(ApplicationTopology.application_id == application_id, ApplicationTopology.is_current_version.is_(True)))
            if topology is not None:
                topology.review_status = "reviewed"
                for node in (topology.topology_graph_json or {}).get("nodes", [])[:3]:
                    session.add(TopologyReviewComment(topology_id=topology.topology_id, target_element_key=node["node_key"], review_verdict="looks_right", reviewer_user_principal_name=REVIEWER))
    await session.flush()


async def _seed_record_links_and_integrations(session: AsyncSession, seed_context: SeedContext) -> None:
    for application_code, links in DEMO_RECORD_LINKS.items():
        application_id = seed_context.application_ids_by_code.get(application_code)
        if application_id is None:
            continue
        for record_system, record_identifier in links:
            if not await session.scalar(
                select(ApplicationRecordLink.application_record_link_id).where(
                    ApplicationRecordLink.application_id == application_id, ApplicationRecordLink.record_system == record_system, ApplicationRecordLink.record_identifier == record_identifier
                )
            ):
                session.add(ApplicationRecordLink(application_id=application_id, record_system=record_system, record_identifier=record_identifier))
    for application_code in ("CLMJP", "CHAD"):
        application_id = seed_context.application_ids_by_code.get(application_code)
        if application_id is None:
            continue
        for integration_kind, base_url in (("cmdb", "https://metlife.service-now.example"), ("ei_portal", "https://eiportal.metlife.example/api")):
            if not await session.scalar(select(ExternalIntegration.external_integration_id).where(ExternalIntegration.application_id == application_id, ExternalIntegration.integration_kind == integration_kind)):
                session.add(
                    ExternalIntegration(
                        application_id=application_id,
                        integration_kind=integration_kind,
                        integration_configuration_json={"base_url": base_url, "authentication_method": "managed_identity"},
                        integration_status="saved_reader_in_development",
                        integration_notes="Details saved; the reader is not available yet.",
                        created_by_user_principal_name=SEED_ACTOR,
                    )
                )
    await session.flush()

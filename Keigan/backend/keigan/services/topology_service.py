"""Topology: AI-built application graph (with a deterministic fallback), versions and stakeholder reviews."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.knowledge_ai_schemas import TopologyEdgeResult, TopologyNodeResult, TopologyResult
from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.config import application_context
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.knowledge_dtos import (
    TopologyDetailResponse,
    TopologyEdgeResponse,
    TopologyNodeResponse,
    TopologyResponse,
    TopologyReviewRequest,
    TopologyReviewResponse,
    TopologyVersionResponse,
)
from keigan.entities.application_entities import Application, DiscoveredResource, MonitoredService, ServiceDependency
from keigan.entities.knowledge_entities import ApplicationTopology, KnowledgeDocument, TopologyReviewComment
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.utils.text_utils import slugify, truncate_text
from keigan.workers.job_queue import JobQueue

NODE_TYPE_BY_SERVICE_TYPE = {
    "network_appliance": "hardware",
    "mainframe_subsystem": "mainframe",
    "batch_job_stream": "mainframe",
    "saas_service": "saas",
    "sql_database": "data_store",
}
ENTRY_POINT_SERVICE_TYPES = ("api_management",)
MAXIMUM_DIGEST_CHARACTERS = 2500


def build_edge_key(source_node_key: str, target_node_key: str) -> str:
    return f"{source_node_key}->{target_node_key}"


class TopologyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.topology_repository = BaseRepository(session, ApplicationTopology)
        self.audit_service = AuditService(session)

    # ── Queries ────────────────────────────────────────────────────────────────
    async def get_topology(self, application_id: str) -> TopologyResponse:
        versions = await self.topology_repository.find_all(ApplicationTopology.application_id == application_id, order_by=ApplicationTopology.topology_version_number.desc())
        current = next((version for version in versions if version.is_current_version), None)
        return TopologyResponse(
            current=await self._to_detail(current) if current else None,
            versions=[self._to_version(version) for version in versions],
            build_in_progress=any(version.generation_status == "building" for version in versions),
        )

    # ── Starting a build ───────────────────────────────────────────────────────
    async def start_build(self, current_user: CurrentUser, application_id: str) -> JobAcceptedResponse:
        if not await BaseRepository(self.session, MonitoredService).exists(MonitoredService.application_id == application_id):
            raise BusinessValidationException("Add at least one service before building the topology.")
        building_version = await self.topology_repository.find_one(ApplicationTopology.application_id == application_id, ApplicationTopology.generation_status == "building")
        if building_version is None:
            await self._create_building_version(application_id)
        job_id = await JobQueue(self.session).enqueue(
            "build_topology",
            {"application_id": application_id, "requested_by_user_principal_name": current_user.user_principal_name},
            deduplication_key=f"topology:{application_id}",
        )
        await self.audit_service.record(current_user, "topology.build", target_entity_type="application", target_entity_id=application_id, application_id=application_id)
        return JobAcceptedResponse(job_id=job_id)

    async def _create_building_version(self, application_id: str) -> ApplicationTopology:
        latest_number = await self.session.scalar(select(ApplicationTopology.topology_version_number).where(ApplicationTopology.application_id == application_id).order_by(ApplicationTopology.topology_version_number.desc()).limit(1))
        return await self.topology_repository.add(
            ApplicationTopology(application_id=application_id, topology_version_number=(latest_number or 0) + 1, generation_status="building", review_status="awaiting_review", is_current_version=False)
        )

    # ── Job: build ─────────────────────────────────────────────────────────────
    async def build_topology(self, application_id: str, requested_by_user_principal_name: str | None = None) -> dict[str, Any] | None:
        application = await self.session.get(Application, application_id)
        if application is None:
            return None
        topology = await self.topology_repository.find_one(ApplicationTopology.application_id == application_id, ApplicationTopology.generation_status == "building")
        if topology is None:
            topology = await self._create_building_version(application_id)
        services = await BaseRepository(self.session, MonitoredService).find_all(MonitoredService.application_id == application_id, order_by=MonitoredService.service_name)
        dependencies = await BaseRepository(self.session, ServiceDependency).find_all(ServiceDependency.application_id == application_id)
        documents = await BaseRepository(self.session, KnowledgeDocument).find_all(KnowledgeDocument.application_id == application_id, KnowledgeDocument.ai_digest_status == "ready")
        corrections = await self._open_corrections(application_id)
        gateway = application_context.llm_gateway()
        generated_by_model_name = "deterministic"
        result: TopologyResult | None = None
        if not gateway.is_mock and services:
            try:
                result = await self._build_with_ai(application, services, dependencies, documents, corrections, requested_by_user_principal_name)
                generated_by_model_name = gateway.model_name_for(ModelTier.DEEP)
            except Exception:  # noqa: BLE001  (AI problems fall back to the deterministic graph so the step always works)
                result = None
        if result is None:
            result = self._build_deterministic(services, dependencies, documents)
            if not gateway.is_mock:
                result.uncertainties.append("The AI builder was unavailable, so this graph uses declared services and dependencies only.")
        graph = self._validated_graph(result, services)
        await self.session.execute(update(ApplicationTopology).where(ApplicationTopology.application_id == application_id).values(is_current_version=False))
        topology.topology_graph_json = graph
        topology.understanding_summary_markdown = sanitize_ai_markdown(result.narrative_markdown)
        topology.generated_from_document_ids_json = [document.knowledge_document_id for document in documents]
        topology.generated_by_model_name = generated_by_model_name
        topology.generation_status = "ready"
        topology.review_status = "awaiting_review"
        topology.is_current_version = True
        await self.session.flush()
        return {"topologyId": topology.topology_id, "versionNumber": topology.topology_version_number, "nodeCount": len(graph["nodes"]), "edgeCount": len(graph["edges"]), "generatedBy": generated_by_model_name}

    async def _open_corrections(self, application_id: str) -> list[TopologyReviewComment]:
        topology_ids = list((await self.session.scalars(select(ApplicationTopology.topology_id).where(ApplicationTopology.application_id == application_id))).all())
        if not topology_ids:
            return []
        return list(
            (await self.session.scalars(
                select(TopologyReviewComment).where(TopologyReviewComment.topology_id.in_(topology_ids), TopologyReviewComment.review_verdict == "needs_correction").order_by(TopologyReviewComment.created_at)
            )).all()
        )

    async def _build_with_ai(
        self, application: Application, services: list[MonitoredService], dependencies: list[ServiceDependency], documents: list[KnowledgeDocument],
        corrections: list[TopologyReviewComment], requested_by: str | None,
    ) -> TopologyResult:
        service_lines = [{"service_id": service.service_id, "name": service.service_name, "type": service.service_type, "criticality": service.criticality_tier, "description": service.service_description} for service in services]
        name_by_id = {service.service_id: service.service_name for service in services}
        dependency_lines = [f"{name_by_id.get(dependency.upstream_service_id)} {dependency.dependency_kind} {name_by_id.get(dependency.downstream_service_id)}" for dependency in dependencies]
        discovered = await BaseRepository(self.session, DiscoveredResource).find_all(DiscoveredResource.application_id == application.application_id, DiscoveredResource.no_longer_found_at.is_(None))
        resource_lines = [f"{resource.resource_name} ({resource.resource_type})" for resource in discovered[:80]]
        digest_text = "\n\n".join(f"### {document.document_title}\n{truncate_text(document.ai_digest_markdown, MAXIMUM_DIGEST_CHARACTERS)}" for document in documents[:12])
        correction_text = "\n".join(f"- {comment.target_element_key or 'whole graph'}: {comment.review_comment_text or 'needs correction'}" for comment in corrections[-20:])
        sections = [
            PromptSection("Monitored services", json.dumps(service_lines, indent=1)),
            PromptSection("Declared dependencies", "\n".join(dependency_lines) or "None declared."),
            PromptSection("Discovered Azure resources", "\n".join(resource_lines) or "None.", is_untrusted=True, source_label="azure:resource-group"),
            PromptSection("Knowledge digests", digest_text or "No documents uploaded.", is_untrusted=True, source_label="knowledge:digests"),
            PromptSection("Reviewer corrections", correction_text or "None.", is_untrusted=True, source_label="topology:reviews"),
            PromptSection("Task", "Build the topology graph following the rules."),
        ]
        return await application_context.llm_gateway().generate_structured(
            feature_name="topology_builder",
            model_tier=ModelTier.DEEP,
            system_prompt=application_context.prompt_library().render("topology_builder", application_name=application.application_name, application_code=application.application_code),
            prompt_sections=sections,
            output_schema=TopologyResult,
            usage_context=LlmUsageContext(application_id=application.application_id, requested_by_user_principal_name=requested_by),
        )

    @staticmethod
    def _build_deterministic(services: list[MonitoredService], dependencies: list[ServiceDependency], documents: list[KnowledgeDocument]) -> TopologyResult:
        nodes = [
            TopologyNodeResult(
                node_key=slugify(service.service_name),
                label=service.service_name,
                node_type=NODE_TYPE_BY_SERVICE_TYPE.get(service.service_type, "service"),  # type: ignore[arg-type]
                service_id=service.service_id,
                technology=service.service_type.replace("_", " "),
                description=service.service_description or "",
                criticality=service.criticality_tier,
            )
            for service in services
        ]
        node_key_by_service_id = {service.service_id: slugify(service.service_name) for service in services}
        edges = [
            TopologyEdgeResult(
                source_node_key=node_key_by_service_id[dependency.upstream_service_id],
                target_node_key=node_key_by_service_id[dependency.downstream_service_id],
                relationship=dependency.dependency_kind,
            )
            for dependency in dependencies
            if dependency.upstream_service_id in node_key_by_service_id and dependency.downstream_service_id in node_key_by_service_id
        ]
        downstream_keys = {edge.target_node_key for edge in edges}
        upstream_keys = {edge.source_node_key for edge in edges}
        entry_labels = [node.label for node in nodes if node.node_key not in downstream_keys and node.node_key in upstream_keys]
        data_store_labels = [node.label for node in nodes if node.node_type == "data_store"]
        isolated_labels = [node.label for node in nodes if node.node_key not in downstream_keys and node.node_key not in upstream_keys]
        narrative_lines = [f"Keigan sees {len(nodes)} monitored services and {len(edges)} declared relationships."]
        if entry_labels:
            narrative_lines.append(f"**Entry points:** {', '.join(entry_labels)}.")
        if data_store_labels:
            narrative_lines.append(f"**Data stores:** {', '.join(data_store_labels)}.")
        if documents:
            narrative_lines.append(f"The graph was checked against {len(documents)} knowledge document(s); only relationships that were declared are drawn.")
        uncertainties = [f"No dependencies are declared for {label}." for label in isolated_labels[:8]]
        if not documents:
            uncertainties.append("No knowledge documents were available, so external systems and data stores outside the service list are not shown.")
        return TopologyResult(nodes=nodes, edges=edges, narrative_markdown="\n\n".join(narrative_lines), uncertainties=uncertainties)

    @staticmethod
    def _sanitized_result(result: TopologyResult) -> TopologyResult:
        """Model-written text (labels, descriptions, narrative, uncertainties) has no links, images or HTML; keys and ids are left alone (V8)."""
        return result.model_copy(update={
            "nodes": [node.model_copy(update={"label": sanitize_ai_line(node.label, maximum_characters=200), "technology": sanitize_ai_line(node.technology, maximum_characters=200),
                                              "description": sanitize_ai_markdown(node.description)}) for node in result.nodes],
            "edges": [edge.model_copy(update={"protocol": sanitize_ai_line(edge.protocol, maximum_characters=100), "description": sanitize_ai_markdown(edge.description)}) for edge in result.edges],
            "narrative_markdown": sanitize_ai_markdown(result.narrative_markdown),
            "uncertainties": [sanitize_ai_line(item, maximum_characters=500) for item in result.uncertainties],
        })

    @staticmethod
    def _validated_graph(result: TopologyResult, services: list[MonitoredService]) -> dict[str, Any]:
        """Unique node keys, real service ids only (unknown nodes become ``external``), every service present, edges between existing nodes."""
        result = TopologyService._sanitized_result(result)
        valid_service_ids = {service.service_id: service for service in services}
        nodes: dict[str, dict[str, Any]] = {}
        for node in result.nodes:
            node_key = slugify(node.node_key) or slugify(node.label)
            if not node_key or node_key in nodes:
                continue
            service_id = node.service_id if node.service_id in valid_service_ids else None
            node_type = node.node_type if (service_id or node.node_type != "service") else "external"
            nodes[node_key] = {
                "node_key": node_key, "label": node.label, "node_type": node_type, "service_id": service_id,
                "technology": node.technology, "description": node.description, "criticality": node.criticality,
            }
        represented_service_ids = {node["service_id"] for node in nodes.values() if node["service_id"]}
        for service in services:
            if service.service_id not in represented_service_ids:
                node_key = slugify(service.service_name)
                nodes.setdefault(node_key, {
                    "node_key": node_key, "label": service.service_name, "node_type": NODE_TYPE_BY_SERVICE_TYPE.get(service.service_type, "service"),
                    "service_id": service.service_id, "technology": service.service_type.replace("_", " "), "description": service.service_description or "", "criticality": service.criticality_tier,
                })
        edges: dict[str, dict[str, Any]] = {}
        for edge in result.edges:
            source_key, target_key = slugify(edge.source_node_key), slugify(edge.target_node_key)
            if source_key in nodes and target_key in nodes and source_key != target_key:
                edges.setdefault(build_edge_key(source_key, target_key), {
                    "source_node_key": source_key, "target_node_key": target_key, "relationship": edge.relationship, "protocol": edge.protocol, "description": edge.description,
                })
        return {"nodes": list(nodes.values()), "edges": list(edges.values()), "uncertainties": result.uncertainties}

    # ── Reviews ────────────────────────────────────────────────────────────────
    async def add_review(self, current_user: CurrentUser, application_id: str, topology_id: str, request: TopologyReviewRequest) -> TopologyReviewResponse:
        topology = await self.topology_repository.get_required(topology_id, "topology")
        if topology.application_id != application_id:
            raise NotFoundException("The topology was not found.")
        if request.target_element_key and not self._element_exists(topology, request.target_element_key):
            raise BusinessValidationException("That element is not part of this topology.", field_errors=[{"field": "targetElementKey", "message": "Unknown node or edge."}])
        if request.review_verdict != "looks_right" and not (request.review_comment_text or "").strip():
            raise BusinessValidationException("Add a short comment so the next build can use it.", field_errors=[{"field": "reviewCommentText", "message": "Required."}])
        review = TopologyReviewComment(
            topology_id=topology_id, target_element_key=request.target_element_key, review_verdict=request.review_verdict,
            review_comment_text=(request.review_comment_text or "").strip() or None, reviewer_user_principal_name=current_user.user_principal_name,
        )
        self.session.add(review)
        await self.session.flush()
        topology.review_status = await self._recompute_review_status(topology)
        await self.audit_service.record(
            current_user, "topology.review", target_entity_type="application_topology", target_entity_id=topology_id, application_id=application_id,
            action_details={"target": request.target_element_key, "verdict": request.review_verdict},
        )
        return TopologyReviewResponse(
            topology_review_comment_id=review.topology_review_comment_id, topology_id=topology_id, target_element_key=review.target_element_key,
            review_verdict=review.review_verdict, review_comment_text=review.review_comment_text, reviewer_user_principal_name=review.reviewer_user_principal_name,
            created_at=review.created_at, topology_review_status=topology.review_status,
        )

    @staticmethod
    def _element_exists(topology: ApplicationTopology, element_key: str) -> bool:
        graph = topology.topology_graph_json or {}
        return any(node["node_key"] == element_key for node in graph.get("nodes", [])) or any(
            build_edge_key(edge["source_node_key"], edge["target_node_key"]) == element_key for edge in graph.get("edges", [])
        )

    async def _recompute_review_status(self, topology: ApplicationTopology) -> str:
        """Latest verdict per element wins; any open correction → needs_correction; otherwise any review → reviewed."""
        reviews = await self._latest_reviews(topology.topology_id)
        if not reviews:
            return "awaiting_review"
        return "needs_correction" if any(review.review_verdict == "needs_correction" for review in reviews.values()) else "reviewed"

    async def _latest_reviews(self, topology_id: str) -> dict[str | None, TopologyReviewComment]:
        rows = await self.session.scalars(select(TopologyReviewComment).where(TopologyReviewComment.topology_id == topology_id).order_by(TopologyReviewComment.created_at))
        latest: dict[str | None, TopologyReviewComment] = {}
        for row in rows.all():
            latest[row.target_element_key] = row
        return latest

    # ── Mapping ────────────────────────────────────────────────────────────────
    @staticmethod
    def _to_version(topology: ApplicationTopology) -> TopologyVersionResponse:
        return TopologyVersionResponse(
            topology_id=topology.topology_id, topology_version_number=topology.topology_version_number, generation_status=topology.generation_status,
            review_status=topology.review_status, is_current_version=topology.is_current_version, generated_by_model_name=topology.generated_by_model_name, created_at=topology.created_at,
        )

    async def _to_detail(self, topology: ApplicationTopology) -> TopologyDetailResponse:
        graph = topology.topology_graph_json or {}
        reviews = await self._latest_reviews(topology.topology_id)
        nodes = [
            TopologyNodeResponse(**node, review_verdict=getattr(reviews.get(node["node_key"]), "review_verdict", None), review_comment_text=getattr(reviews.get(node["node_key"]), "review_comment_text", None))
            for node in graph.get("nodes", [])
        ]
        edges = []
        for edge in graph.get("edges", []):
            edge_key = build_edge_key(edge["source_node_key"], edge["target_node_key"])
            edges.append(TopologyEdgeResponse(**edge, edge_key=edge_key, review_verdict=getattr(reviews.get(edge_key), "review_verdict", None), review_comment_text=getattr(reviews.get(edge_key), "review_comment_text", None)))
        return TopologyDetailResponse(
            **self._to_version(topology).model_dump(), nodes=nodes, edges=edges, understanding_summary_markdown=topology.understanding_summary_markdown,
            uncertainties=graph.get("uncertainties", []), generated_from_document_ids=topology.generated_from_document_ids_json or [],
        )

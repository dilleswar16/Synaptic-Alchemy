"""The investigation engine (doc 06 section 3) as a LangGraph state machine.

triage -> context -> evidence -(planner loop once)-> hypotheses (3 in parallel) -> synthesis -> blast radius -> communications

Deterministic code decides where to look and what was found; the model decides what it means. One
:class:`InvestigationGraphRunner` instance owns the session and the working data for a single run; the graph state only
carries small flags and the hypothesis results. Progress is committed after every stage so the UI can poll it.
"""

from __future__ import annotations

import logging
import operator
import re
from datetime import timedelta
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.command_risk_classifier import RISK_RANK, classify_command_risk
from keigan.ai.investigation_ai_caller import InvestigationAiCaller, build_mock_context
from keigan.ai.investigation_ai_schemas import AdditionalQueryPlan, BlastRadiusNarrative, HypothesisResult, RcaSynthesisResult, TriageResult
from keigan.ai.investigation_mock_responses import MockInvestigationContext, MockServiceInfo
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.ai.prompt_safety import build_valid_citation_codes, remove_invalid_citations, restrict_to_known_file_path, strip_invisible_characters
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.application_entities import Application, MonitoredService, ServiceDependency
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.exceptions.keigan_exceptions import KeiganException, LlmUnavailableException, TokenBudgetExceededException
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.services.evidence_service import EvidenceDraft, EvidenceService, ServiceTelemetryContext
from keigan.services.incident_priority_rules import map_servicenow_priority, most_severe_priority
from keigan.utils.pii_masker import MaskingContext, PiiMasker
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import utc_now
from keigan.entities.status_values import AnalysisPerspective, CriticalityTier, IncidentStatus, InvestigationFeedbackVerdict, InvestigationStage, InvestigationStatus, Priority, RiskLevel

logger = logging.getLogger(__name__)

PERSPECTIVES = (AnalysisPerspective.APPLICATION, AnalysisPerspective.DEPENDENCIES, AnalysisPerspective.INFRASTRUCTURE)
STAGE_PERCENT = {InvestigationStage.TRIAGE: 8, InvestigationStage.CONTEXT: 22, InvestigationStage.EVIDENCE: 35, InvestigationStage.HYPOTHESES: 62, InvestigationStage.SYNTHESIS: 82, InvestigationStage.COMMUNICATIONS: 94}
_FENCED_BLOCK_PATTERN = re.compile(r"```[a-z]*\n(.*?)```", re.DOTALL)


class InvestigationState(TypedDict, total=False):
    investigation_id: str
    needs_planner: bool
    evidence_only: bool
    hypotheses: Annotated[list[dict[str, Any]], operator.add]


class InvestigationGraphRunner:
    def __init__(self, session: AsyncSession, investigation: Investigation, *, offline_ai: bool = False, auto_send_communications: bool = True):
        self.session = session
        self.investigation = investigation
        self.settings = get_settings()
        self.offline_ai = offline_ai
        self.auto_send_communications = auto_send_communications
        self.evidence_service = EvidenceService(session)
        self.masking_context = MaskingContext()
        self.masker = PiiMasker(self.masking_context)
        self.application: Application
        self.incident: Incident | None = None
        self.services: list[MonitoredService] = []
        self.all_services: list[MonitoredService] = []
        self.dependencies: list[ServiceDependency] = []
        self.service_contexts: list[ServiceTelemetryContext] = []
        self.triage: TriageResult | None = None
        self.incident_text = ""
        self.knowledge_markdown = ""
        self.resource_group_by_service_id: dict[str, str] = {}  # so prompts can name real resource groups instead of inviting guesses
        self.knowledge_reference_codes: set[str] = set()  # the K# codes of the knowledge that was really given to the model
        self.knowledge_contains_flagged_content = False
        self.runbook_matches: list[Any] = []
        self.recurring_issues_markdown = ""
        self.evidence_drafts: list[EvidenceDraft] = []
        self.evidence_rows: list[InvestigationEvidence] = []
        self.hypothesis_rows: list[InvestigationHypothesis] = []
        self.synthesis: RcaSynthesisResult | None = None
        self.has_planned_once = False
        self.evidence_only = False
        self.ai_caller: InvestigationAiCaller
        self.mock_context: MockInvestigationContext | None = None

    # ── Graph ──────────────────────────────────────────────────────────────────
    def build_graph(self) -> Any:
        graph = StateGraph(InvestigationState)
        graph.add_node("triage", self.triage_node)
        graph.add_node("context", self.context_node)
        graph.add_node("evidence", self.evidence_node)
        graph.add_node("planner", self.planner_node)
        graph.add_node("finalize_evidence", self.finalize_evidence_node)
        for perspective in PERSPECTIVES:
            graph.add_node(f"hypothesis_{perspective}", self._hypothesis_node(perspective))
        graph.add_node("synthesis", self.synthesis_node)
        graph.add_node("blast_radius", self.blast_radius_node)
        graph.add_node("communications", self.communications_node)
        graph.add_edge(START, "triage")
        graph.add_edge("triage", "context")
        graph.add_edge("context", "evidence")
        graph.add_conditional_edges("evidence", lambda state: "planner" if state.get("needs_planner") else "finalize_evidence", ["planner", "finalize_evidence"])
        graph.add_edge("planner", "finalize_evidence")
        graph.add_conditional_edges(
            "finalize_evidence", lambda state: ["blast_radius"] if state.get("evidence_only") else [f"hypothesis_{name}" for name in PERSPECTIVES],
            [*(f"hypothesis_{name}" for name in PERSPECTIVES), "blast_radius"],
        )
        graph.add_edge([f"hypothesis_{name}" for name in PERSPECTIVES], "synthesis")
        graph.add_edge("synthesis", "blast_radius")
        graph.add_edge("blast_radius", "communications")
        graph.add_edge("communications", END)
        return graph.compile()

    async def run(self) -> dict[str, Any]:
        await self._load_inputs()
        await self._update_progress("triage", "Reading the incident and the application's service catalogue", 3)
        final_state = await self.build_graph().ainvoke({"investigation_id": self.investigation.investigation_id, "hypotheses": [], "evidence_only": False, "needs_planner": False})
        await self._complete(bool(final_state.get("evidence_only")) or self.evidence_only)
        return {"investigationId": self.investigation.investigation_id, "status": self.investigation.investigation_status, "evidenceCount": len(self.evidence_rows)}

    # ── Loading and progress ───────────────────────────────────────────────────
    async def _load_inputs(self) -> None:
        investigation = self.investigation
        self.application = await self.session.get(Application, investigation.application_id)  # type: ignore[assignment]
        if investigation.incident_id:
            self.incident = await self.session.get(Incident, investigation.incident_id)
        self.all_services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == investigation.application_id, MonitoredService.is_monitoring_enabled.is_(True)))).all())
        self.dependencies = list((await self.session.scalars(select(ServiceDependency).where(ServiceDependency.application_id == investigation.application_id))).all())
        if investigation.investigation_window_start is None or investigation.investigation_window_end is None:
            anchor = self.incident.opened_at if self.incident else investigation.created_at
            window_start = anchor - timedelta(minutes=self.settings.investigation_lookback_minutes)
            window_end = min(utc_now(), window_start + timedelta(minutes=self.settings.investigation_max_window_minutes))
            investigation.investigation_window_start, investigation.investigation_window_end = window_start, window_end
        maximum_window = timedelta(minutes=self.settings.investigation_max_window_minutes)  # also for callers other than the manual form (V17)
        if investigation.investigation_window_end - investigation.investigation_window_start > maximum_window:
            investigation.investigation_window_start = investigation.investigation_window_end - maximum_window
        window_length = investigation.investigation_window_end - investigation.investigation_window_start
        investigation.baseline_window_end = investigation.investigation_window_start
        investigation.baseline_window_start = investigation.investigation_window_start - window_length
        investigation.investigation_status = InvestigationStatus.RUNNING
        investigation.started_at = investigation.started_at or utc_now()
        investigation.stage_messages_json = []
        await self._build_initial_mock_context()
        self.ai_caller = InvestigationAiCaller(
            self.application.application_id, self.application.application_name, self.application.criticality_tier, investigation.investigation_id,
            investigation.requested_by_user_principal_name, self.mock_context, self.offline_ai,
        )

    async def _update_progress(self, stage_name: str, message: str, percent: int | None = None) -> None:
        investigation = self.investigation
        investigation.current_stage_name = stage_name
        investigation.progress_percent = percent if percent is not None else STAGE_PERCENT.get(stage_name, investigation.progress_percent)
        investigation.stage_messages_json = [*(investigation.stage_messages_json or []), {"at": utc_now().isoformat(), "stage": stage_name, "message": message}]
        await self.session.commit()

    def _add_timeline_event(self, event_type: str, title: str, details: str | None = None, occurred_at: Any = None, source: str = "keigan") -> None:
        self.session.add(
            InvestigationTimelineEvent(
                incident_id=self.investigation.incident_id, investigation_id=self.investigation.investigation_id, event_occurred_at=occurred_at or utc_now(),
                event_type=event_type, event_title=title[:400], event_details_markdown=details, event_source=source,
            )
        )

    # ── LLM access ─────────────────────────────────────────────────────────────
    async def _ask(self, feature_name: str, prompt_sections: list[PromptSection], output_schema: type[BaseModel], **template_variables: Any) -> Any:
        return await self.ai_caller.ask(feature_name, prompt_sections, output_schema, **template_variables)

    # ── Mock context (used only when the provider is mock) ─────────────────────
    async def _build_initial_mock_context(self) -> None:
        self.mock_context = await build_mock_context(self.investigation, self.incident, self.application.application_name, self.all_services)

    # ── Stage 1: triage ────────────────────────────────────────────────────────
    async def triage_node(self, state: InvestigationState) -> dict[str, Any]:
        incident, investigation = self.incident, self.investigation
        raw_text = f"{incident.incident_title}\n\n{incident.incident_description or ''}" if incident else (investigation.triage_result_json or {}).get("manual_description", "")
        covered_group_ids = select(AlertGroup.alert_group_id).where(AlertGroup.investigation_id == investigation.investigation_id)
        alerts = (await self.session.scalars(select(Alert).where(Alert.alert_group_id.in_(covered_group_ids)).order_by(Alert.first_seen_at).limit(20))).all()
        if alerts:
            raw_text += "\n\nAlerts in the group:\n" + "\n".join(f"- {alert.rule_name}: {alert.alert_summary}" for alert in alerts)
        self.incident_text = self.masker.mask_text(raw_text)
        catalogue = self._describe_services(self.all_services)
        sections = [
            PromptSection("Service catalogue", catalogue),
            PromptSection("ServiceNow fields", f"Priority {incident.servicenow_priority}, impact {incident.servicenow_impact}, urgency {incident.servicenow_urgency}, assignment group {incident.assignment_group_name}" if incident else "Manual investigation: no ServiceNow record."),
            PromptSection("Incident from ServiceNow" if incident else "Incident description", self.incident_text, is_untrusted=True, source_label=f"servicenow:{incident.external_incident_number}" if incident else "manual"),
            PromptSection("Task", "Triage this incident as instructed."),
        ]
        try:
            self.triage = await self._ask("incident_triage", sections, TriageResult)
        except (TokenBudgetExceededException, LlmUnavailableException) as unavailable:
            logger.info("Triage fell back to deterministic mode: %s", unavailable)
            self.evidence_only = True
            self.triage = TriageResult(suggested_priority=Priority.P3, priority_rationale="AI unavailable; priority taken from ServiceNow fields.", incident_category="errors", incident_summary=truncate_text(self.incident_text, 400))
        triage = self.triage
        triage.incident_summary, triage.priority_rationale = sanitize_ai_markdown(triage.incident_summary), sanitize_ai_markdown(triage.priority_rationale)
        triage.key_symptoms = [sanitize_ai_line(symptom, maximum_characters=200) for symptom in triage.key_symptoms[:8]]
        catalogue_names = {service.service_name.lower(): service for service in self.all_services}
        triage.candidate_service_names = [name for name in triage.candidate_service_names if name.lower() in catalogue_names]
        self.services = self._resolve_candidate_services(triage.candidate_service_names)
        investigation.replace_linked_ids("investigated_service_links", [service.service_id for service in self.services])
        guardrail_priority = await self._guardrail_priority()
        mapped_priority = map_servicenow_priority(incident.servicenow_impact, incident.servicenow_urgency, incident.servicenow_priority) if incident else None
        final_priority = most_severe_priority(triage.suggested_priority, mapped_priority, guardrail_priority) or triage.suggested_priority
        if incident:
            incident.keigan_priority, incident.priority_rationale = final_priority, triage.priority_rationale
            incident.incident_category = triage.incident_category
            incident.replace_linked_ids("affected_service_links", investigation.investigated_service_ids)
            incident.incident_status = IncidentStatus.INVESTIGATING if incident.incident_status in (IncidentStatus.NEW, IncidentStatus.INVESTIGATING) else incident.incident_status
        investigation.triage_result_json = {**(investigation.triage_result_json or {}), **triage.model_dump(), "final_priority": final_priority, "guardrail_priority": guardrail_priority, "mapped_servicenow_priority": mapped_priority}
        if self.mock_context:
            self.mock_context.priority = final_priority
        self._add_timeline_event("investigation_started", "Keigan started investigating", f"Priority {final_priority}; category {triage.incident_category}; services: {', '.join(service.service_name for service in self.services) or 'none identified'}.")
        if triage.contains_instruction_like_text:
            self._add_timeline_event("note", "The incident text contained instruction-like content, which Keigan ignored", "Review the original ticket before trusting this analysis.")
        await self._update_progress("triage", f"Triage complete: priority {final_priority}, category {triage.incident_category}, {len(self.services)} service(s) to examine", 15)
        return {"evidence_only": self.evidence_only}

    def _resolve_candidate_services(self, triage_names: list[str]) -> list[MonitoredService]:
        services_by_id = {service.service_id: service for service in self.all_services}
        services_by_name = {service.service_name.lower(): service for service in self.all_services}
        ordered_ids: list[str] = list(self.investigation.investigated_service_ids)
        if self.incident:
            ordered_ids += self.incident.affected_service_ids
        ordered_ids += [services_by_name[name.lower()].service_id for name in triage_names if name.lower() in services_by_name]
        ordered_ids = [service_id for service_id in dict.fromkeys(ordered_ids) if service_id in services_by_id]
        for service_id in list(ordered_ids[:3]):  # dependency neighbourhood: downstream first, then upstream callers
            ordered_ids += [dependency.downstream_service_id for dependency in self.dependencies if dependency.upstream_service_id == service_id]
        for service_id in list(ordered_ids[:3]):
            ordered_ids += [dependency.upstream_service_id for dependency in self.dependencies if dependency.downstream_service_id == service_id]
        if not ordered_ids:
            ordered_ids = [service.service_id for service in sorted(self.all_services, key=lambda service: service.criticality_tier)]
        unique_ids = [service_id for service_id in dict.fromkeys(ordered_ids) if service_id in services_by_id]
        return [services_by_id[service_id] for service_id in unique_ids[: self.settings.investigation_max_services]]

    async def _guardrail_priority(self) -> str | None:
        if self.application.criticality_tier != CriticalityTier.TIER_1:
            return None
        try:
            from keigan.services.slo_service import SloService

            summaries = await SloService(self.session).summarize_slos([self.application.application_id])
        except Exception as slo_error:  # noqa: BLE001 — S3 may not be implemented yet
            logger.debug("SLO guardrail skipped: %s", slo_error)
            return None
        return Priority.P2 if any((summary.get("burnRateOneHour") or 0) > 6 for summary in summaries) else None

    def _describe_services(self, services: list[MonitoredService]) -> str:
        names_by_id = {service.service_id: service.service_name for service in self.all_services}
        lines = [f"Application {self.application.application_name} ({self.application.application_code}), tier {self.application.criticality_tier}, region {self.application.region_code}"]
        for service in services:
            calls = [names_by_id[dependency.downstream_service_id] for dependency in self.dependencies if dependency.upstream_service_id == service.service_id and dependency.downstream_service_id in names_by_id]
            namespace_text = f", namespace {service.aks_namespace_filter}" if service.aks_namespace_filter else ""
            resource_group = self.resource_group_by_service_id.get(service.service_id)
            resource_text = (f", resource group {resource_group}" if resource_group else "") + (f", resource id {service.external_resource_identifier}" if service.external_resource_identifier else "")
            lines.append(f"- {service.service_name} ({service.service_type}, {service.criticality_tier}{namespace_text}{resource_text})" + (f" calls: {', '.join(calls)}" if calls else ""))
        return "\n".join(lines)

    # ── Stage 2: context ───────────────────────────────────────────────────────
    async def context_node(self, state: InvestigationState) -> dict[str, Any]:
        assert self.triage is not None
        query_text = f"{self.triage.incident_summary} {' '.join(self.triage.key_symptoms)}"
        service_ids = [service.service_id for service in self.services]
        try:
            from keigan.services.knowledge_service import KnowledgeService

            knowledge_service = KnowledgeService(self.session)
            grounding = await knowledge_service.build_grounding_context(self.application.application_id, query_text, service_ids, self.settings.investigation_knowledge_token_budget)
            self.knowledge_markdown = f"{grounding.topology_summary_markdown}\n\n{grounding.knowledge_markdown}".strip()
            self.knowledge_reference_codes = {reference.reference_code for reference in grounding.references}
            self.knowledge_contains_flagged_content = grounding.contains_flagged_content
            self.investigation.knowledge_references_json = [{"referenceCode": reference.reference_code, "title": reference.title, "sourceKind": reference.source_kind, "knowledgeDocumentId": reference.knowledge_document_id} for reference in grounding.references]
            self.runbook_matches = await knowledge_service.find_matching_runbooks(self.application.application_id, query_text, service_ids, 3)
        except Exception as knowledge_error:  # noqa: BLE001 — guarded cross-slice call
            logger.info("Knowledge context not available: %s", knowledge_error)
            self.knowledge_markdown, self.runbook_matches = "", []
            self.knowledge_reference_codes, self.knowledge_contains_flagged_content = set(), False
        previous = (
            await self.session.scalars(
                select(Investigation).where(
                    Investigation.application_id == self.application.application_id, Investigation.user_feedback_verdict == InvestigationFeedbackVerdict.CORRECT, Investigation.investigation_id != self.investigation.investigation_id
                ).order_by(Investigation.completed_at.desc()).limit(3)
            )
        ).all()
        self.recurring_issues_markdown = "\n".join(f"- Confirmed earlier: {truncate_text(investigation.executive_summary, 300)}" for investigation in previous if investigation.executive_summary)
        self.service_contexts = await self.evidence_service.load_service_contexts(self.services)
        self.resource_group_by_service_id = {context.service.service_id: context.component.azure_resource_group_name for context in self.service_contexts if context.component and context.component.azure_resource_group_name}
        if self.mock_context:
            self.mock_context.services = [
                MockServiceInfo(
                    context.service.service_id, context.service.service_name, context.service.service_type, context.service.aks_namespace_filter,
                    context.component.azure_resource_group_name if context.component else None, context.service.external_resource_identifier,
                )
                for context in self.service_contexts
            ]
        await self._update_progress("context", f"Context ready: {len(self.runbook_matches)} runbook match(es), {len(self.dependencies)} dependency link(s) in the neighbourhood", 28)
        return {}

    # ── Stage 3: evidence ──────────────────────────────────────────────────────
    async def evidence_node(self, state: InvestigationState) -> dict[str, Any]:
        investigation = self.investigation
        assert investigation.investigation_window_start and investigation.investigation_window_end and investigation.baseline_window_start and investigation.baseline_window_end
        await self._update_progress("evidence", f"Querying telemetry for {len(self.services)} service(s) over {int((investigation.investigation_window_end - investigation.investigation_window_start).total_seconds() // 60)} minutes and a matching baseline", 38)
        self.evidence_drafts = await self.evidence_service.collect_evidence(
            self.service_contexts, investigation.investigation_window_start, investigation.investigation_window_end, investigation.baseline_window_start, investigation.baseline_window_end, self.masking_context
        )
        change_events, change_draft = await self.evidence_service.collect_change_evidence(
            self.application.application_id, self.service_contexts, investigation.investigation_window_start - timedelta(hours=24), investigation.investigation_window_end,
            masking_context=self.masking_context,
        )
        if change_draft:
            self.evidence_drafts.append(change_draft)
        for change_event in change_events:
            self._add_timeline_event(
                "change", self.masker.mask_text(change_event.description), self.masker.mask_text(f"{change_event.operation_name} ({change_event.change_kind}) by {change_event.caller or 'unknown'}"),
                change_event.occurred_at, "azure_activity_log",
            )
        strong_count = sum(1 for draft in self.evidence_drafts if draft.signal_strength in (RiskLevel.HIGH, RiskLevel.MEDIUM) and not draft.is_rule_out)
        await self._update_progress("evidence", f"Collected {len(self.evidence_drafts)} evidence items; {strong_count} with a medium or high signal", 52)
        return {"needs_planner": strong_count < 2 and not self.has_planned_once and not self.evidence_only}

    async def planner_node(self, state: InvestigationState) -> dict[str, Any]:
        self.has_planned_once = True
        investigation = self.investigation
        await self._update_progress("evidence", "Few strong signals found; asking the planner for up to three extra read-only queries", 54)
        sections = [
            PromptSection("Service catalogue", self._describe_services(self.services)),
            PromptSection("Query limits per service", self.evidence_service.describe_query_limits_for_planner(self.service_contexts)),
            PromptSection("Incident", self.incident_text, is_untrusted=True, source_label="incident"),
            PromptSection("Evidence already collected", "\n".join(f"- {draft.evidence_title}: {truncate_text(draft.evidence_summary, 160)}" for draft in self.evidence_drafts), is_untrusted=True, source_label="evidence"),
        ]
        try:
            plan: AdditionalQueryPlan = await self._ask("evidence_query_planner", sections, AdditionalQueryPlan)
        except (TokenBudgetExceededException, LlmUnavailableException, KeiganException):
            return {}
        assert investigation.investigation_window_start and investigation.investigation_window_end and investigation.baseline_window_start and investigation.baseline_window_end
        extra_drafts = await self.evidence_service.run_planned_queries(
            plan.queries, self.service_contexts, investigation.investigation_window_start, investigation.investigation_window_end, investigation.baseline_window_start, investigation.baseline_window_end, self.masking_context
        )
        self.evidence_drafts.extend(extra_drafts)
        return {}

    async def finalize_evidence_node(self, state: InvestigationState) -> dict[str, Any]:
        ranked_drafts = self.evidence_service.rank_and_trim(self.evidence_drafts, self.settings.investigation_evidence_token_budget)
        self.evidence_rows = await self.evidence_service.persist_evidence(self.investigation.investigation_id, ranked_drafts)
        self.investigation.replace_linked_ids("matched_runbook_links", [])
        await self._refine_runbook_matches()
        if self.mock_context:
            names_by_id = {service.service_id: service.service_name for service in self.all_services}
            self.mock_context.evidence = [
                {"code": row.evidence_code, "service_name": names_by_id.get(row.service_id or "", "Azure Activity Log"), "category": row.evidence_category, "strength": row.signal_strength, "title": row.evidence_title, "summary": row.evidence_summary or "", "is_rule_out": row.matched_record_count == 0 or (row.evidence_summary or "").startswith(("Rule-out", "Not available"))}
                for row in self.evidence_rows
            ]
        strong_rows = [row for row in self.evidence_rows if row.signal_strength in (RiskLevel.HIGH, RiskLevel.MEDIUM)]
        self._add_timeline_event("evidence_collected", f"Evidence collected: {len(self.evidence_rows)} items, {len(strong_rows)} strong", "Top signals: " + "; ".join(truncate_text(row.evidence_title, 80) for row in strong_rows[:3]))
        if self.evidence_only:
            await self._update_progress("hypotheses", "AI is unavailable; continuing in evidence-only mode", 70)
        else:
            await self._update_progress("hypotheses", "Three analysts (application, dependencies, infrastructure) are forming hypotheses in parallel", STAGE_PERCENT["hypotheses"])
        return {"evidence_only": self.evidence_only}

    # ── Stage 4: hypotheses (three perspectives in parallel) ───────────────────
    async def _refine_runbook_matches(self) -> None:
        """Re-rank runbooks against the error signatures actually observed; runbooks describe log messages, not ticket wording."""
        signature_lines = [row.evidence_title for row in self.evidence_rows if row.signal_strength in (RiskLevel.HIGH, RiskLevel.MEDIUM)][:8]
        for evidence_row in self.evidence_rows[:8]:
            signature_lines.extend(str(pattern.get("template", ""))[:200] for pattern in (evidence_row.condensed_patterns_json or [])[:2])
        if not signature_lines:
            return
        refined_query_text = f"{self.triage.incident_summary if self.triage else ''} {' '.join(signature_lines)}"
        try:
            from keigan.services.knowledge_service import KnowledgeService

            refined_matches = await KnowledgeService(self.session).find_matching_runbooks(
                self.application.application_id, refined_query_text, [service.service_id for service in self.services], 3
            )
        except Exception as knowledge_error:  # noqa: BLE001 — guarded cross-slice call
            logger.info("Runbook re-ranking skipped: %s", knowledge_error)
            return
        if refined_matches:
            self.runbook_matches = refined_matches

    def _hypothesis_node(self, perspective: str) -> Any:
        async def run_hypothesis(state: InvestigationState) -> dict[str, Any]:
            service_names_by_id = {service.service_id: service.service_name for service in self.all_services}
            runbook_text = "\n\n".join(f"[{match.reference_code}] {match.runbook_title}\nSymptoms: {match.trigger_symptoms_text}\nSteps:\n{match.runbook_steps_markdown}" for match in self.runbook_matches) or "No matching runbooks."
            sections = [
                PromptSection("Analysis perspective", perspective),
                PromptSection("Application and services", self._describe_services(self.services)),
                self._knowledge_section(),
                PromptSection("Known issues (runbooks)", runbook_text, is_untrusted=True, source_label="runbooks"),
                PromptSection("Recurring issues confirmed in the past", self.recurring_issues_markdown or "None recorded.", is_untrusted=True, source_label="earlier investigations"),
                PromptSection("Incident", f"{self.incident_text}\n\nTriage summary: {self.triage.incident_summary if self.triage else ''}", is_untrusted=True, source_label="incident"),
                PromptSection("Evidence index", EvidenceService.render_evidence_markdown(self.evidence_rows, service_names_by_id), is_untrusted=True, source_label="telemetry evidence", maximum_characters=60_000),
                PromptSection("Task", f"Give your {perspective} perspective hypothesis."),
            ]
            try:
                result: HypothesisResult = await self._ask(f"hypothesis_{perspective}", sections, HypothesisResult)
            except (TokenBudgetExceededException, LlmUnavailableException) as unavailable:
                logger.info("Hypothesis %s skipped: %s", perspective, unavailable)
                self.evidence_only = True
                return {}
            except KeiganException as invalid_output:
                logger.warning("Hypothesis %s failed: %s", perspective, invalid_output)
                return {}
            return {"hypotheses": [self._validated_hypothesis(perspective, result)]}

        return run_hypothesis

    def _knowledge_section(self) -> PromptSection:
        """Uploaded documents are written by people outside Keigan, so they are data, not instructions (V7)."""
        return PromptSection(
            "Application knowledge", self.knowledge_markdown or "No knowledge documents are available for this application.", is_untrusted=True, source_label="knowledge documents",
            maximum_characters=60_000, is_flagged=self.knowledge_contains_flagged_content,
        )

    def _valid_citation_codes(self) -> set[str]:
        """Codes that exist for this investigation: its evidence, its matched runbooks and the knowledge that was given to the model."""
        return build_valid_citation_codes((row.evidence_code for row in self.evidence_rows), (match.reference_code for match in self.runbook_matches), self.knowledge_reference_codes)

    def _clean_ai_text(self, markdown_text: str, valid_codes: set[str]) -> str:
        """Citations that do not exist are removed, then links, images and HTML are neutralised (V8, V20)."""
        return sanitize_ai_markdown(remove_invalid_citations(markdown_text, valid_codes))

    def _clean_synthesis_text(self, markdown_text: str, runbook_codes: dict[str, Any]) -> str:
        valid_codes = self._valid_citation_codes() | set(runbook_codes)
        return self._flag_high_risk_commands(self._clean_ai_text(markdown_text, valid_codes))

    def _validated_hypothesis(self, perspective: str, result: HypothesisResult) -> dict[str, Any]:
        valid_codes = self._valid_citation_codes()
        known_knowledge_text = f"{self.knowledge_markdown}\n" + "\n".join(f"{match.runbook_title}\n{match.runbook_steps_markdown}" for match in self.runbook_matches)
        highest_risk = result.fix_risk_level
        steps = []
        for step in result.proposed_fix.steps:
            command_text = strip_invisible_characters(step.command_text) if step.command_text else None
            command_risk = classify_command_risk(command_text) if command_text else None
            if command_risk and RISK_RANK[command_risk] > RISK_RANK[highest_risk]:
                highest_risk = command_risk
            steps.append({**step.model_dump(), "description": self._clean_ai_text(step.description, valid_codes), "command_text": command_text, "command_risk_level": command_risk})
        fix = result.proposed_fix
        proposed_fix = {
            "summary": self._clean_ai_text(fix.summary, valid_codes), "steps": steps,
            "code_changes": [
                {**change.model_dump(), "file_path": restrict_to_known_file_path(change.file_path, known_knowledge_text), "change_description": self._clean_ai_text(change.change_description, valid_codes),
                 "before_snippet": strip_invisible_characters(change.before_snippet) if change.before_snippet else None, "after_snippet": strip_invisible_characters(change.after_snippet) if change.after_snippet else None}
                for change in fix.code_changes
            ],
            "verification_steps": [self._clean_ai_text(text, valid_codes) for text in fix.verification_steps],
            "rollback_steps": [self._clean_ai_text(text, valid_codes) for text in fix.rollback_steps],
        }
        runbook_code = result.matched_runbook_code if result.matched_runbook_code in {match.reference_code for match in self.runbook_matches} else None
        return {
            "analysis_perspective": perspective, "hypothesis_title": sanitize_ai_line(result.hypothesis_title, maximum_characters=300),
            "hypothesis_statement_markdown": self._clean_ai_text(result.hypothesis_statement_markdown, valid_codes),
            "reasoning_markdown": self._clean_ai_text(result.reasoning_markdown, valid_codes),
            "confidence_score": max(0.0, min(1.0, result.confidence_score)),
            "supporting_evidence_codes": [code for code in result.supporting_evidence_codes if code in valid_codes], "contradicting_evidence_codes": [code for code in result.contradicting_evidence_codes if code in valid_codes],
            "proposed_fix": proposed_fix, "fix_risk_level": highest_risk, "matched_runbook_code": runbook_code,
        }

    # ── Stage 5: synthesis ─────────────────────────────────────────────────────
    async def synthesis_node(self, state: InvestigationState) -> dict[str, Any]:
        hypotheses = sorted(state.get("hypotheses", []), key=lambda hypothesis: PERSPECTIVES.index(hypothesis["analysis_perspective"]))
        if not hypotheses or self.evidence_only:
            self.evidence_only = True
            return {"evidence_only": True}
        investigation = self.investigation
        await self._update_progress("synthesis", "Comparing the three hypotheses and writing the root cause analysis", 74)
        runbook_codes = {match.reference_code: match for match in self.runbook_matches}
        hypotheses_text = "\n\n".join(
            f"### {hypothesis['analysis_perspective'].capitalize()} (confidence {hypothesis['confidence_score']:.2f})\n{hypothesis['hypothesis_title']}\n{hypothesis['hypothesis_statement_markdown']}\nReasoning: {hypothesis['reasoning_markdown']}\n"
            f"Supporting: {', '.join(hypothesis['supporting_evidence_codes']) or 'none'}; contradicting: {', '.join(hypothesis['contradicting_evidence_codes']) or 'none'}\nFix summary: {hypothesis['proposed_fix']['summary']}"
            for hypothesis in hypotheses
        )
        service_names_by_id = {service.service_id: service.service_name for service in self.all_services}
        sections = [
            PromptSection("Service catalogue", self._describe_services(self.services)),
            PromptSection("Hypotheses from the three analysts", hypotheses_text, is_untrusted=True, source_label="analyst hypotheses"),
            PromptSection("Evidence index", EvidenceService.render_evidence_markdown(self.evidence_rows, service_names_by_id), is_untrusted=True, source_label="telemetry evidence", maximum_characters=60_000),
            PromptSection("Known issues (runbooks)", "\n\n".join(f"[{code}] {match.runbook_title}\n{match.runbook_steps_markdown}" for code, match in runbook_codes.items()) or "No matching runbooks.", is_untrusted=True, source_label="runbooks"),
            self._knowledge_section(),
            PromptSection("Task", "Decide the leading perspective and write the root cause analysis."),
        ]
        try:
            synthesis: RcaSynthesisResult = await self._ask("rca_synthesis", sections, RcaSynthesisResult)
        except (TokenBudgetExceededException, LlmUnavailableException, KeiganException) as failure:
            logger.warning("Synthesis failed (%s); using the strongest hypothesis", failure)
            best_hypothesis = max(hypotheses, key=lambda hypothesis: hypothesis["confidence_score"])
            synthesis = RcaSynthesisResult(
                leading_perspective=best_hypothesis["analysis_perspective"], leading_perspective_reason="Synthesis was unavailable; the highest-confidence hypothesis is shown.", overall_confidence_score=best_hypothesis["confidence_score"],
                executive_summary=best_hypothesis["hypothesis_title"], what_went_wrong_markdown=best_hypothesis["hypothesis_statement_markdown"], why_it_happened_markdown=best_hypothesis["reasoning_markdown"],
                how_to_fix_markdown=best_hypothesis["proposed_fix"]["summary"], open_questions=[],
            )
        clean = lambda markdown_text: self._clean_synthesis_text(markdown_text, runbook_codes)  # noqa: E731
        leading = next((hypothesis for hypothesis in hypotheses if hypothesis["analysis_perspective"] == synthesis.leading_perspective), max(hypotheses, key=lambda hypothesis: hypothesis["confidence_score"]))
        maximum_confidence = max(hypothesis["confidence_score"] for hypothesis in hypotheses)
        investigation.overall_confidence_score = round(min(synthesis.overall_confidence_score, maximum_confidence + 0.05), 2)
        investigation.executive_summary = clean(synthesis.executive_summary)
        investigation.what_went_wrong_markdown = clean(synthesis.what_went_wrong_markdown)
        investigation.why_it_happened_markdown = clean(synthesis.why_it_happened_markdown)
        investigation.how_to_fix_markdown = clean(synthesis.how_to_fix_markdown)
        investigation.open_questions_json = [sanitize_ai_line(question, maximum_characters=500) for question in synthesis.open_questions[:5]]
        applied_runbook_ids = [runbook_codes[code].runbook_id for code in synthesis.applied_runbook_codes if code in runbook_codes]
        investigation.replace_linked_ids("matched_runbook_links", applied_runbook_ids)
        if applied_runbook_ids:
            try:
                from keigan.services.knowledge_service import KnowledgeService

                await KnowledgeService(self.session).record_runbook_references(applied_runbook_ids)
            except Exception as reference_error:  # noqa: BLE001
                logger.debug("Runbook reference counting skipped: %s", reference_error)
        self.synthesis = synthesis
        if self.mock_context:
            self.mock_context.synthesis = {**synthesis.model_dump(), "overall_confidence_score": investigation.overall_confidence_score}
        for display_order, hypothesis in enumerate(hypotheses):
            runbook_match = runbook_codes.get(hypothesis["matched_runbook_code"] or "")
            row = InvestigationHypothesis(
                investigation_id=investigation.investigation_id, analysis_perspective=hypothesis["analysis_perspective"], hypothesis_title=hypothesis["hypothesis_title"],
                hypothesis_statement_markdown=hypothesis["hypothesis_statement_markdown"], reasoning_markdown=hypothesis["reasoning_markdown"], confidence_score=hypothesis["confidence_score"],
                supporting_evidence_codes_json=hypothesis["supporting_evidence_codes"], contradicting_evidence_codes_json=hypothesis["contradicting_evidence_codes"],
                proposed_fix_json=hypothesis["proposed_fix"], fix_risk_level=hypothesis["fix_risk_level"], matched_runbook_id=runbook_match.runbook_id if runbook_match else None,
                is_leading_hypothesis=hypothesis is leading, display_order=display_order,
            )
            self.session.add(row)
            self.hypothesis_rows.append(row)
        await self.session.flush()
        investigation.leading_hypothesis_id = next(row.hypothesis_id for row in self.hypothesis_rows if row.is_leading_hypothesis)
        self._add_timeline_event("rca_completed", f"Root cause analysis ready (confidence {int((investigation.overall_confidence_score or 0) * 100)}%)", investigation.executive_summary)
        await self._update_progress("synthesis", "Root cause analysis written; mapping the blast radius", 86)
        return {}

    @staticmethod
    def _flag_high_risk_commands(markdown_text: str) -> str:
        def annotate(block_match: re.Match[str]) -> str:
            is_high_risk = classify_command_risk(block_match.group(1)) == RiskLevel.HIGH
            return block_match.group(0) + ("\n> **High risk.** Confirm with your change process before running this command.\n" if is_high_risk else "")

        return _FENCED_BLOCK_PATTERN.sub(annotate, markdown_text)

    # ── Stage 5b: blast radius ─────────────────────────────────────────────────
    async def blast_radius_node(self, state: InvestigationState) -> dict[str, Any]:
        services_by_id = {service.service_id: service for service in self.all_services}
        names_by_id = {service_id: service.service_name for service_id, service in services_by_id.items()}
        strong_service_ids = {row.service_id for row in self.evidence_rows if row.service_id and row.signal_strength in (RiskLevel.HIGH, RiskLevel.MEDIUM) and row.matched_record_count > 0 and row.evidence_category != "change_event"}
        direct_ids = [service.service_id for service in self.services if service.service_id in strong_service_ids] or [service.service_id for service in self.services[:1]]
        indirect_ids: list[str] = []
        frontier = list(direct_ids)
        for _ in range(2):  # callers of an impacted service are impacted too
            frontier = [dependency.upstream_service_id for dependency in self.dependencies if dependency.downstream_service_id in frontier and dependency.upstream_service_id not in direct_ids + indirect_ids]
            indirect_ids += list(dict.fromkeys(frontier))
        impacted_ids = set(direct_ids) | set(indirect_ids)
        slo_summaries: list[dict[str, Any]] = []
        try:
            from keigan.services.slo_service import SloService

            all_slos = await SloService(self.session).summarize_slos([self.application.application_id])
            slo_summaries = [summary for summary in all_slos if summary.get("serviceId") in impacted_ids or summary.get("status") in ("at_risk", "breached")][:10]
        except Exception as slo_error:  # noqa: BLE001
            logger.debug("Impacted SLOs skipped: %s", slo_error)
        stakeholders = list(
            (await self.session.scalars(select(Stakeholder).where(Stakeholder.application_id == self.application.application_id, Stakeholder.is_active.is_(True)))).all()
        )
        relevant_stakeholders = [stakeholder for stakeholder in stakeholders if not stakeholder.subscribed_service_ids or impacted_ids & set(stakeholder.subscribed_service_ids)]
        node_ids = list(dict.fromkeys([*direct_ids, *indirect_ids, *(service.service_id for service in self.services)]))
        blast_radius = {
            "nodes": [
                {"serviceId": service_id, "serviceName": names_by_id[service_id], "serviceType": services_by_id[service_id].service_type, "criticalityTier": services_by_id[service_id].criticality_tier,
                 "impactLevel": "direct" if service_id in direct_ids else "indirect" if service_id in indirect_ids else "investigated"}
                for service_id in node_ids if service_id in services_by_id
            ],
            "edges": [{"fromServiceId": dependency.upstream_service_id, "toServiceId": dependency.downstream_service_id, "kind": dependency.dependency_kind} for dependency in self.dependencies if dependency.upstream_service_id in node_ids and dependency.downstream_service_id in node_ids],
            "impactedSlos": slo_summaries,
            "stakeholders": [{"displayName": stakeholder.display_name, "role": stakeholder.stakeholder_role, "preferredLanguageCode": stakeholder.preferred_language_code} for stakeholder in relevant_stakeholders],
            "narrativeMarkdown": None, "userImpactSummary": None,
        }
        deterministic_text = (
            f"Directly impacted: {', '.join(names_by_id[service_id] for service_id in direct_ids) or 'none'}\nIndirectly impacted: {', '.join(names_by_id[service_id] for service_id in indirect_ids) or 'none'}\n"
            f"Impacted SLOs: {'; '.join(truncate_text(str(summary.get('sliName', 'SLO')) + ' ' + str(summary.get('status')), 60) for summary in slo_summaries) or 'none reported'}\nStakeholders: {len(relevant_stakeholders)} subscribed"
        )
        if not self.evidence_only:
            try:
                narrative: BlastRadiusNarrative = await self._ask("blast_radius_narrative", [
                    PromptSection("Service catalogue", self._describe_services(self.all_services)), PromptSection("Blast radius (deterministic)", deterministic_text),
                    PromptSection("Root cause summary", self.investigation.executive_summary or "", is_untrusted=True, source_label="rca"), PromptSection("Task", "Write the impact narrative."),
                ], BlastRadiusNarrative)
                blast_radius["narrativeMarkdown"] = sanitize_ai_markdown(narrative.narrative_markdown)
                blast_radius["userImpactSummary"] = sanitize_ai_markdown(narrative.user_impact_summary)
            except (TokenBudgetExceededException, LlmUnavailableException, KeiganException):
                logger.info("Blast radius narrative skipped; using the deterministic summary")
        if not blast_radius["narrativeMarkdown"]:
            blast_radius["narrativeMarkdown"] = deterministic_text.replace("\n", "  \n")
        self.investigation.blast_radius_json = blast_radius
        if self.incident is not None:
            self.incident.replace_linked_ids("affected_service_links", [*direct_ids, *indirect_ids])
        await self._update_progress("synthesis", f"Blast radius mapped: {len(direct_ids)} direct, {len(indirect_ids)} indirect", 90)
        return {}

    # ── Stage 6: communications ────────────────────────────────────────────────
    async def communications_node(self, state: InvestigationState) -> dict[str, Any]:
        if self.evidence_only or self.synthesis is None:
            await self._update_progress("communications", "Skipped drafts because AI analysis is unavailable", 97)
            return {}
        await self._update_progress("communications", "Drafting English and Japanese updates", STAGE_PERCENT["communications"])
        from keigan.services.communication_service import CommunicationService

        try:
            await CommunicationService(self.session).draft_investigation_communications(
                self.investigation, ["initial_update", "executive_summary", "preliminary_report"], None, auto_send=self.auto_send_communications, ask=self._ask,
            )
        except Exception as draft_error:  # noqa: BLE001 — drafts are helpful but never block the RCA
            logger.warning("Communication drafting failed: %s", draft_error)
        return {}

    # ── Completion ─────────────────────────────────────────────────────────────
    async def _complete(self, evidence_only: bool) -> None:
        investigation = self.investigation
        investigation.investigation_status = InvestigationStatus.COMPLETED_EVIDENCE_ONLY if evidence_only or self.evidence_only else InvestigationStatus.COMPLETED
        investigation.progress_percent, investigation.current_stage_name, investigation.completed_at = 100, InvestigationStage.COMPLETED, utc_now()
        model_names = set(self.ai_caller.model_names)
        if self.ai_caller.uses_estimated_tokens:
            investigation.total_input_token_count, investigation.total_output_token_count = self.ai_caller.estimated_input_tokens, self.ai_caller.estimated_output_tokens
        else:
            token_rows = (await self.session.execute(select(LlmUsageRecord.input_token_count, LlmUsageRecord.output_token_count, LlmUsageRecord.model_name).where(LlmUsageRecord.investigation_id == investigation.investigation_id))).all()
            investigation.total_input_token_count = sum(row.input_token_count for row in token_rows)
            investigation.total_output_token_count = sum(row.output_token_count for row in token_rows)
            model_names |= {row.model_name for row in token_rows}
        investigation.model_names_json = sorted(model_names)
        if self.incident and self.incident.incident_status in (IncidentStatus.NEW, IncidentStatus.INVESTIGATING) and investigation.investigation_status == InvestigationStatus.COMPLETED:
            self.incident.incident_status = IncidentStatus.IDENTIFIED
        message = "Investigation complete" + (" (evidence only: AI was unavailable)" if investigation.investigation_status == InvestigationStatus.COMPLETED_EVIDENCE_ONLY else "")
        investigation.stage_messages_json = [*(investigation.stage_messages_json or []), {"at": utc_now().isoformat(), "stage": "completed", "message": message}]
        await self.session.commit()

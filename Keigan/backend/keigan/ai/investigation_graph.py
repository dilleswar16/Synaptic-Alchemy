"""The investigation engine (doc 06 section 3) as a LangGraph state machine.

triage -> context -> evidence -(planner loop once)-> hypotheses (3 in parallel) -> synthesis -> blast radius -> communications

Deterministic code decides where to look and what was found; the model decides what it means. One
:class:`InvestigationGraphRunner` instance owns the session and the working data for a single run; the graph state only
carries small flags and the hypothesis results. Progress is committed after every stage so the UI can poll it.
"""

from __future__ import annotations

import hashlib
import logging
import operator
import re
from collections import Counter
from datetime import timedelta
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.fix_command_check import check_suggested_command, command_warnings
from keigan.ai.fix_plan import PLAN_SCHEMA_VERSION as FIX_SCHEMA_VERSION, build_fix_plan, resolve_plan_steps
from keigan.ai.fix_configuration_command import ServiceFacts
from keigan.ai.fix_plan_markdown import render_fix_plan_markdown
from keigan.ai.fix_step_validator import FixValidationContext, validate_fix_step
from keigan.ai.command_risk_classifier import RISK_RANK, classify_command_risk
from keigan.ai.investigation_ai_caller import InvestigationAiCaller, build_mock_context
from keigan.ai.investigation_ai_schemas import AdditionalQueryPlan, BlastRadiusNarrative, HypothesisResult, RcaSynthesisResult, TriageResult
from keigan.ai.investigation_mock_responses import MockInvestigationContext, MockServiceInfo
from keigan.ai.investigation_outcome_rules import EvidenceFacts, StateThresholds, decide_hypothesis_state, decide_outcome
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.operating_notes_prompt import build_operating_notes_section
from keigan.ai.output_sanitizer import sanitize_ai_line, sanitize_ai_markdown
from keigan.ai.prompt_safety import build_valid_citation_codes, remove_invalid_citations, restrict_to_known_file_path, strip_invisible_characters
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.application_entities import Application, MonitoredService, ServiceDependency
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.entities.status_values import (
    AnalysisPerspective, CoverageGapKind, CoverageGapReason, CriticalityTier, EvidenceCheckOutcome, HypothesisState, IncidentStatus, InvestigationFeedbackVerdict,
    InvestigationDecisionKind, InvestigationOutcome, InvestigationStage, InvestigationStatus, InvestigationTraceStepStatus, Priority, RiskLevel, SloHealthStatus,
)
from keigan.exceptions.keigan_exceptions import KeiganException, LlmUnavailableException, TokenBudgetExceededException
from keigan.integrations.simulation.simulation_scenarios import SCENARIO_CATALOG
from keigan.services.evidence_service import EvidenceDraft, EvidenceService, ServiceTelemetryContext
from keigan.services.incident_priority_rules import map_servicenow_priority, most_severe_priority
from keigan.services.audit_service import AuditService
from keigan.services.investigation_coverage import CoverageGapCollector
from keigan.services.investigation_trace_adjustments import hypothesis_adjustments, synthesis_adjustments
from keigan.services.investigation_trace_recorder import InvestigationTraceRecorder
from keigan.utils.pii_masker import MaskingContext, PiiMasker
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)

INVESTIGATION_PIPELINE_VERSION = "1"  # bumped when the order of the stages or the rules that decide between them change; the decision trace records it
PLANNER_STRONG_SIGNAL_THRESHOLD = 2  # the planner asks for extra queries when fewer strong signals than this were found
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
        self.coverage = CoverageGapCollector()  # what this run could not check; stored as rows and told to the model
        self.evidence_service = EvidenceService(session, self.coverage)
        self.masking_context = MaskingContext()
        self.masker = PiiMasker(self.masking_context)
        self.recorder = InvestigationTraceRecorder(session, investigation.investigation_id, self.masker, self.settings)  # the decision trace (spec 28); never affects the run
        self.planner_strong_signal_count = 0
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
        self.operating_notes_section: PromptSection | None = None  # the team's guidance for the AI: untrusted, masked, never evidence; None when the team wrote none
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
            investigation.requested_by_user_principal_name, self.mock_context, self.offline_ai, call_observer=self.recorder.record_ai_call,
        )
        self.recorder.record_inputs(self._input_snapshot())

    def _input_snapshot(self) -> dict[str, Any]:
        """What the run started from, as the decision trace records it: ids, windows, the settings that shape the run, and whether operating notes were present (a hash, not the notes)."""
        investigation, settings = self.investigation, self.settings
        notes_text = self.application.operating_notes_text
        return {
            "pipelineVersion": INVESTIGATION_PIPELINE_VERSION, "trigger": investigation.investigation_trigger, "incidentId": investigation.incident_id,
            "incidentNumber": self.incident.external_incident_number if self.incident else None,
            "window": {"start": investigation.investigation_window_start.isoformat(), "end": investigation.investigation_window_end.isoformat()},
            "baselineWindow": {"start": investigation.baseline_window_start.isoformat(), "end": investigation.baseline_window_end.isoformat()},
            "requestedServiceIds": list(investigation.investigated_service_ids),
            "provider": {"name": self.ai_caller.gateway.provider_name, "isMock": bool(self.ai_caller.gateway.is_mock), "offlineAi": self.offline_ai},
            "models": {"fast": settings.llm_fast_model, "deep": settings.llm_deep_model},
            "settings": {
                "lookbackMinutes": settings.investigation_lookback_minutes, "maximumWindowMinutes": settings.investigation_max_window_minutes, "maximumServices": settings.investigation_max_services,
                "maximumChecksPerService": settings.investigation_max_checks_per_service, "evidenceTokenBudget": settings.investigation_evidence_token_budget,
                "knowledgeTokenBudget": settings.investigation_knowledge_token_budget, "supportedMinimumConfidence": settings.investigation_supported_minimum_confidence,
                "ruledOutMaximumConfidence": settings.investigation_ruled_out_maximum_confidence, "plannerStrongSignalThreshold": PLANNER_STRONG_SIGNAL_THRESHOLD,
            },
            "operatingNotes": {"present": bool(notes_text), "sha256": hashlib.sha256(notes_text.encode("utf-8")).hexdigest() if notes_text else None},
        }

    def _enter_evidence_only_mode(self, reason: str, stage: str) -> None:
        """The AI is not used from here on. Recorded once, with why (a code) and where."""
        if not self.evidence_only:
            self.recorder.record_decision(InvestigationDecisionKind.EVIDENCE_ONLY_MODE, {"reason": reason, "stage": stage})
        self.evidence_only = True

    @staticmethod
    def _unavailable_reason(failure: Exception) -> str:
        return "token_budget_exceeded" if isinstance(failure, TokenBudgetExceededException) else "ai_unavailable"

    async def _update_progress(self, stage_name: str, message: str, percent: int | None = None) -> None:
        investigation = self.investigation
        self.recorder.stage = stage_name
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
            self._enter_evidence_only_mode(self._unavailable_reason(unavailable), InvestigationStage.TRIAGE)
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
        cut_service_names = [name for entry in self.coverage.entries if entry.kind == CoverageGapKind.SERVICES_BEYOND_LIMIT for name in entry.parameters.get("serviceNames", [])]
        self.recorder.record_decision(InvestigationDecisionKind.SERVICES_SELECTED, {
            "selectedServiceIds": [service.service_id for service in self.services], "requestedServiceIds": list(investigation.investigated_service_ids),
            "fromTriage": list(triage.candidate_service_names), "cutServiceNames": cut_service_names, "limit": self.settings.investigation_max_services,
        })
        self.recorder.record_decision(InvestigationDecisionKind.PRIORITY_SET, {
            "suggested": triage.suggested_priority, "mappedFromServiceNow": mapped_priority, "guardrail": guardrail_priority, "final": final_priority,
        })
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
        limit = self.settings.investigation_max_services
        cut_ids = unique_ids[limit:]
        if cut_ids:
            self.coverage.add(
                CoverageGapKind.SERVICES_BEYOND_LIMIT,
                parameters={"count": len(cut_ids), "limit": limit, "serviceNames": [services_by_id[service_id].service_name for service_id in cut_ids]},
            )
        return [services_by_id[service_id] for service_id in unique_ids[:limit]]

    async def _guardrail_priority(self) -> str | None:
        if self.application.criticality_tier != CriticalityTier.TIER_1:
            return None
        try:
            from keigan.services.slo_service import SloService

            summaries = await SloService(self.session).summarize_slos([self.application.application_id])
        except Exception as slo_error:  # noqa: BLE001 — the tier-one guardrail cannot read SLOs; the investigation continues without it
            logger.warning("SLO guardrail for application %s could not be read, so the guardrail was not applied: %s", self.application.application_id, slo_error)
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
        self.operating_notes_section = build_operating_notes_section(self.application.operating_notes_text, self.masker)
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
        self.planner_strong_signal_count = strong_count
        return {"needs_planner": strong_count < PLANNER_STRONG_SIGNAL_THRESHOLD and not self.has_planned_once and not self.evidence_only}

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
            self.recorder.record_decision(
                InvestigationDecisionKind.PLANNER_REQUESTED, {"strongSignalCount": self.planner_strong_signal_count, "threshold": PLANNER_STRONG_SIGNAL_THRESHOLD, "queriesPlanned": 0, "queriesRun": 0},
                InvestigationTraceStepStatus.FAILED,
            )
            return {}
        assert investigation.investigation_window_start and investigation.investigation_window_end and investigation.baseline_window_start and investigation.baseline_window_end
        extra_drafts = await self.evidence_service.run_planned_queries(
            plan.queries, self.service_contexts, investigation.investigation_window_start, investigation.investigation_window_end, investigation.baseline_window_start, investigation.baseline_window_end, self.masking_context
        )
        self.evidence_drafts.extend(extra_drafts)
        self.recorder.record_decision(InvestigationDecisionKind.PLANNER_REQUESTED, {
            "strongSignalCount": self.planner_strong_signal_count, "threshold": PLANNER_STRONG_SIGNAL_THRESHOLD, "queriesPlanned": len(plan.queries), "queriesRun": len(extra_drafts),
        })
        return {}

    async def finalize_evidence_node(self, state: InvestigationState) -> dict[str, Any]:
        ranked_drafts = self.evidence_service.select_for_investigation(self.evidence_drafts, self.settings.investigation_evidence_token_budget)
        self.evidence_rows = await self.evidence_service.persist_evidence(self.investigation.investigation_id, ranked_drafts)
        await self.coverage.persist_new(self.session, self.investigation.investigation_id)
        self.recorder.record_evidence({
            "evidenceIds": {row.evidence_code: row.evidence_id for row in self.evidence_rows}, "countsByCheckOutcome": dict(Counter(row.check_outcome for row in self.evidence_rows)),
            "countsByBaselineComparison": dict(Counter(row.baseline_comparison for row in self.evidence_rows)), "coverageGapCount": len(self.coverage.entries),
            "kept": len(self.evidence_rows), "collected": len(self.evidence_drafts), "tokenBudget": self.settings.investigation_evidence_token_budget,
        })
        self.investigation.replace_linked_ids("matched_runbook_links", [])
        await self._refine_runbook_matches()
        if self.mock_context:
            names_by_id = {service.service_id: service.service_name for service in self.all_services}
            self.mock_context.evidence = [
                {"code": row.evidence_code, "service_name": names_by_id.get(row.service_id or "", "Azure Activity Log"), "category": row.evidence_category, "strength": row.signal_strength, "title": row.evidence_title, "summary": row.evidence_summary or "", "is_rule_out": row.check_outcome != EvidenceCheckOutcome.SIGNAL}
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
                *self._operating_notes_sections(),
                PromptSection("Known issues (runbooks)", runbook_text, is_untrusted=True, source_label="runbooks"),
                PromptSection("Recurring issues confirmed in the past", self.recurring_issues_markdown or "None recorded.", is_untrusted=True, source_label="earlier investigations"),
                PromptSection("Incident", f"{self.incident_text}\n\nTriage summary: {self.triage.incident_summary if self.triage else ''}", is_untrusted=True, source_label="incident"),
                PromptSection("What Keigan could not check", self.coverage.render_for_prompt()),  # trusted: written by code from catalogue names and fixed sentences
                PromptSection("Evidence index", EvidenceService.render_evidence_markdown(self.evidence_rows, service_names_by_id), is_untrusted=True, source_label="telemetry evidence", maximum_characters=60_000),
                PromptSection("Task", f"Give your {perspective} perspective hypothesis."),
            ]
            try:
                result: HypothesisResult = await self._ask(
                    f"hypothesis_{perspective}", sections, HypothesisResult,
                    supported_minimum_confidence=self.settings.investigation_supported_minimum_confidence, ruled_out_maximum_confidence=self.settings.investigation_ruled_out_maximum_confidence, maximum_fix_steps=self.settings.suggested_fix_maximum_steps,
                )
            except (TokenBudgetExceededException, LlmUnavailableException) as unavailable:
                logger.info("Hypothesis %s skipped: %s", perspective, unavailable)
                self.coverage.add(CoverageGapKind.PERSPECTIVE_NOT_ANALYSED, CoverageGapReason.AI_UNAVAILABLE, parameters={"perspective": perspective})
                self._enter_evidence_only_mode(self._unavailable_reason(unavailable), InvestigationStage.HYPOTHESES)
                return {}
            except KeiganException as invalid_output:
                logger.warning("Hypothesis %s failed: %s", perspective, invalid_output)
                self.coverage.add(CoverageGapKind.PERSPECTIVE_NOT_ANALYSED, CoverageGapReason.AI_OUTPUT_INVALID, parameters={"perspective": perspective})
                return {}
            validated = self._validated_hypothesis(perspective, result)
            self.recorder.add_adjustments(f"hypothesis_{perspective}", validated.pop("adjustments"))
            return {"hypotheses": [validated]}

        return run_hypothesis

    def _knowledge_section(self) -> PromptSection:
        """Uploaded documents are written by people outside Keigan, so they are data, not instructions (V7)."""
        return PromptSection(
            "Application knowledge", self.knowledge_markdown or "No knowledge documents are available for this application.", is_untrusted=True, source_label="knowledge documents",
            maximum_characters=60_000, is_flagged=self.knowledge_contains_flagged_content,
        )

    def _operating_notes_sections(self) -> list[PromptSection]:
        """The team's operating notes when there are any. They are guidance with no citation code, so they never enter ``_valid_citation_codes``."""
        return [self.operating_notes_section] if self.operating_notes_section else []

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
        fix = result.proposed_fix
        validation_context = self._fix_validation_context(valid_codes, known_knowledge_text)
        steps = [
            validate_fix_step(step, f"{perspective}-{number}", validation_context, lambda path: restrict_to_known_file_path(path, known_knowledge_text))
            for number, step in enumerate(fix.steps[:self.settings.suggested_fix_maximum_steps], start=1)
        ]
        highest_risk = result.fix_risk_level
        for step in steps:
            if RISK_RANK[step["risk_level"]] > RISK_RANK[highest_risk]:
                highest_risk = step["risk_level"]  # a withheld step still counts: the hypothesis stays as risky as what it proposed
        proposed_fix = {
            "schema_version": FIX_SCHEMA_VERSION, "summary": self._clean_ai_text(fix.summary, valid_codes), "steps": steps,
            "code_changes": [
                {**change.model_dump(), "file_path": restrict_to_known_file_path(change.file_path, known_knowledge_text), "change_description": self._clean_ai_text(change.change_description, valid_codes),
                 "before_snippet": strip_invisible_characters(change.before_snippet) if change.before_snippet else None, "after_snippet": strip_invisible_characters(change.after_snippet) if change.after_snippet else None}
                for change in fix.code_changes
            ],
        }
        runbook_code = result.matched_runbook_code if result.matched_runbook_code in {match.reference_code for match in self.runbook_matches} else None
        replaced_file_paths = sum(1 for change, kept in zip(fix.code_changes, proposed_fix["code_changes"]) if kept["file_path"] != change.file_path)
        supporting_codes = [code for code in result.supporting_evidence_codes if code in valid_codes]
        contradicting_codes = [code for code in result.contradicting_evidence_codes if code in valid_codes]
        confidence = max(0.0, min(1.0, result.confidence_score))
        state_decision = decide_hypothesis_state(
            HypothesisState(result.assessment), confidence, self._evidence_facts(supporting_codes), self._evidence_facts(contradicting_codes),
            StateThresholds(self.settings.investigation_supported_minimum_confidence, self.settings.investigation_ruled_out_maximum_confidence),
        )
        raw_texts = [
            result.hypothesis_statement_markdown, result.reasoning_markdown, result.assessment_reason_markdown, fix.summary, *(step.title for step in fix.steps),
            *(action.description for step in fix.steps for action in (step.action, step.check, step.revert) if action is not None), *(change.change_description for change in fix.code_changes),
        ]
        adjustments = hypothesis_adjustments(
            raw_texts=raw_texts, valid_codes=valid_codes, dropped_evidence_codes=[code for code in (*result.supporting_evidence_codes, *result.contradicting_evidence_codes) if code not in valid_codes],
            replaced_file_path_count=replaced_file_paths, risk_from=result.fix_risk_level, risk_to=highest_risk, state_decision=state_decision,
        )
        return {
            "analysis_perspective": perspective, "hypothesis_title": sanitize_ai_line(result.hypothesis_title, maximum_characters=300), "adjustments": adjustments,
            "hypothesis_statement_markdown": self._clean_ai_text(result.hypothesis_statement_markdown, valid_codes),
            "reasoning_markdown": self._clean_ai_text(result.reasoning_markdown, valid_codes),
            "confidence_score": confidence, "supporting_evidence_codes": supporting_codes, "contradicting_evidence_codes": contradicting_codes,
            "hypothesis_state": state_decision.final, "proposed_hypothesis_state": state_decision.proposed, "state_guard_code": state_decision.guard,
            "state_reason_markdown": self._clean_ai_text(result.assessment_reason_markdown, valid_codes), "state_decision": state_decision,
            "proposed_fix": proposed_fix, "fix_risk_level": highest_risk, "matched_runbook_code": runbook_code,
        }

    def _fix_validation_context(self, valid_codes: set[str], knowledge_text: str) -> FixValidationContext:
        """What a value in a suggested command may be checked against: the catalogue, this investigation's evidence and the knowledge the model was given (spec 33, 4.4)."""
        catalogue_values = {value for service in self.all_services for value in (service.service_name, service.aks_namespace_filter, service.external_resource_identifier) if value}
        catalogue_values.update(self.resource_group_by_service_id.values())
        return FixValidationContext(
            catalogue_values=frozenset(catalogue_values),
            evidence_texts={
                row.evidence_code: "\n".join([row.evidence_title, row.evidence_summary or "", *(str(pattern.get("template", "")) for pattern in (row.condensed_patterns_json or []))]) for row in self.evidence_rows
            },
            evidence_codes_with_query=frozenset(row.evidence_code for row in self.evidence_rows if row.query_text), knowledge_text=knowledge_text,
            maximum_command_characters=self.settings.suggested_fix_maximum_command_characters, maximum_parameters_per_command=self.settings.suggested_fix_maximum_parameters_per_command,
            clean_markdown=lambda text: self._clean_ai_text(text, valid_codes), clean_line=lambda text: sanitize_ai_line(text, maximum_characters=300),
            services={
                service.service_name: ServiceFacts(service.service_type, self.resource_group_by_service_id.get(service.service_id), service.aks_namespace_filter)
                for service in self.all_services
            },
        )

    def _evidence_facts(self, codes: list[str] | None = None) -> list[EvidenceFacts]:
        """What the rules need to know about the evidence rows behind ``codes`` (every persisted row when ``codes`` is None)."""
        return [
            EvidenceFacts(row.evidence_code, row.check_outcome, row.signal_strength, row.baseline_comparison)
            for row in self.evidence_rows if codes is None or row.evidence_code in codes
        ]

    # ── Stage 5: synthesis ─────────────────────────────────────────────────────
    async def synthesis_node(self, state: InvestigationState) -> dict[str, Any]:
        hypotheses = sorted(state.get("hypotheses", []), key=lambda hypothesis: PERSPECTIVES.index(hypothesis["analysis_perspective"]))
        if not hypotheses or self.evidence_only:
            self._enter_evidence_only_mode("no_hypothesis_produced", InvestigationStage.SYNTHESIS)
            return {"evidence_only": True}
        investigation = self.investigation
        await self._update_progress("synthesis", "Comparing the three hypotheses and writing the root cause analysis", 74)
        runbook_codes = {match.reference_code: match for match in self.runbook_matches}
        hypotheses_text = "\n\n".join(
            f"### {hypothesis['analysis_perspective'].capitalize()} (confidence {hypothesis['confidence_score']:.2f}, state {hypothesis['hypothesis_state']}{self._guard_note(hypothesis)})\n{hypothesis['hypothesis_title']}\n{hypothesis['hypothesis_statement_markdown']}\nReasoning: {hypothesis['reasoning_markdown']}\n"
            f"Supporting: {', '.join(hypothesis['supporting_evidence_codes']) or 'none'}; contradicting: {', '.join(hypothesis['contradicting_evidence_codes']) or 'none'}\nFix summary: {hypothesis['proposed_fix']['summary']}\n"
            + "\n".join(f"step {number} ({step['purpose'].replace('_', ' ')}, {step['risk_level']}): {step['title']}" for number, step in enumerate(hypothesis["proposed_fix"]["steps"], start=1))
            for hypothesis in hypotheses
        )
        service_names_by_id = {service.service_id: service.service_name for service in self.all_services}
        sections = [
            PromptSection("Service catalogue", self._describe_services(self.services)),
            PromptSection("What Keigan could not check", self.coverage.render_for_prompt()),
            PromptSection("Hypotheses from the three analysts", hypotheses_text, is_untrusted=True, source_label="analyst hypotheses"),
            PromptSection("Evidence index", EvidenceService.render_evidence_markdown(self.evidence_rows, service_names_by_id), is_untrusted=True, source_label="telemetry evidence", maximum_characters=60_000),
            PromptSection("Known issues (runbooks)", "\n\n".join(f"[{code}] {match.runbook_title}\n{match.runbook_steps_markdown}" for code, match in runbook_codes.items()) or "No matching runbooks.", is_untrusted=True, source_label="runbooks"),
            self._knowledge_section(),
            *self._operating_notes_sections(),
            PromptSection("Task", "Decide the outcome and the leading perspective, and write the root cause analysis."),
        ]
        synthesis_was_available = True
        try:
            synthesis: RcaSynthesisResult = await self._ask("rca_synthesis", sections, RcaSynthesisResult, maximum_plan_steps=self.settings.suggested_fix_plan_maximum_steps)
        except (TokenBudgetExceededException, LlmUnavailableException, KeiganException) as failure:
            logger.warning("Synthesis failed (%s); using the strongest hypothesis", failure)
            synthesis_was_available = False
            best_hypothesis = max(hypotheses, key=lambda hypothesis: hypothesis["confidence_score"])
            self.recorder.record_decision(
                InvestigationDecisionKind.SYNTHESIS_FALLBACK, {"failureCode": self._unavailable_reason(failure) if isinstance(failure, TokenBudgetExceededException) else type(failure).__name__, "strongestPerspective": best_hypothesis["analysis_perspective"]},
            )
            synthesis = RcaSynthesisResult(
                leading_perspective=best_hypothesis["analysis_perspective"], leading_perspective_reason="Synthesis was unavailable; the highest-confidence hypothesis is shown.",
                investigation_outcome=InvestigationOutcome.INCONCLUSIVE, outcome_reason_markdown="The synthesis was unavailable, so the outcome follows the highest-confidence hypothesis.", overall_confidence_score=best_hypothesis["confidence_score"],
                executive_summary=best_hypothesis["hypothesis_title"], what_went_wrong_markdown=best_hypothesis["hypothesis_statement_markdown"], why_it_happened_markdown=best_hypothesis["reasoning_markdown"],
                fix_overview_markdown=best_hypothesis["proposed_fix"]["summary"], recommended_fix_steps=[], open_questions=[],
            )
        clean = lambda markdown_text: self._clean_synthesis_text(markdown_text, runbook_codes)  # noqa: E731
        strongest_lead = next((hypothesis for hypothesis in hypotheses if hypothesis["analysis_perspective"] == synthesis.leading_perspective), max(hypotheses, key=lambda hypothesis: hypothesis["confidence_score"]))
        outcome_decision = decide_outcome(
            InvestigationOutcome(synthesis.investigation_outcome) if synthesis_was_available else None, leading_state=strongest_lead["hypothesis_state"],
            evidence=self._evidence_facts(), synthesis_was_available=synthesis_was_available,
        )
        leading = None if outcome_decision.final == InvestigationOutcome.CAUSE_NOT_VISIBLE else strongest_lead  # nothing visible changed: no explanation is shown as the lead
        maximum_confidence = max(hypothesis["confidence_score"] for hypothesis in hypotheses)
        investigation.overall_confidence_score = round(min(synthesis.overall_confidence_score, maximum_confidence + 0.05), 2)
        if synthesis_was_available:
            self.recorder.add_adjustments("rca_synthesis", synthesis_adjustments(
                raw_texts=[synthesis.outcome_reason_markdown, synthesis.leading_perspective_reason, synthesis.executive_summary, synthesis.what_went_wrong_markdown, synthesis.why_it_happened_markdown, synthesis.fix_overview_markdown],
                valid_codes=self._valid_citation_codes() | set(runbook_codes), confidence_from=synthesis.overall_confidence_score, confidence_to=investigation.overall_confidence_score, outcome_decision=outcome_decision,
            ))
        investigation.investigation_outcome, investigation.proposed_investigation_outcome = outcome_decision.final, outcome_decision.proposed
        investigation.outcome_guard_code = outcome_decision.guard
        investigation.outcome_reason_markdown = clean(synthesis.outcome_reason_markdown)
        investigation.leading_perspective_reason_markdown = clean(synthesis.leading_perspective_reason)
        investigation.executive_summary = clean(synthesis.executive_summary)
        investigation.what_went_wrong_markdown = clean(synthesis.what_went_wrong_markdown)
        investigation.why_it_happened_markdown = clean(synthesis.why_it_happened_markdown)
        fix_overview = clean(synthesis.fix_overview_markdown)
        fix_plan = build_fix_plan(
            fix_overview, [(reference.perspective, reference.step_number) for reference in synthesis.recommended_fix_steps], hypotheses, strongest_lead["analysis_perspective"],
            self.settings.suggested_fix_plan_maximum_steps,
        )
        investigation.fix_plan_json = fix_plan
        investigation.how_to_fix_markdown = render_fix_plan_markdown(fix_overview, resolve_plan_steps(fix_plan, hypotheses), self.settings.suggested_fix_default_shell_dialect.value)
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
                hypothesis_state=hypothesis["hypothesis_state"], proposed_hypothesis_state=hypothesis["proposed_hypothesis_state"], state_guard_code=hypothesis["state_guard_code"],
                state_reason_markdown=hypothesis["state_reason_markdown"],
            )
            self.session.add(row)
            self.hypothesis_rows.append(row)
        await self.session.flush()
        investigation.leading_hypothesis_id = next((row.hypothesis_id for row in self.hypothesis_rows if row.is_leading_hypothesis), None)
        for row in self.hypothesis_rows:
            self.recorder.link_hypothesis(f"hypothesis_{row.analysis_perspective}", row.hypothesis_id)
        await self.coverage.persist_new(self.session, investigation.investigation_id)  # the perspectives that produced nothing
        self._add_timeline_event(
            "rca_completed", f"Root cause analysis ready: {outcome_decision.final.value.replace('_', ' ')} (confidence {int((investigation.overall_confidence_score or 0) * 100)}%)", investigation.executive_summary,
        )
        await self._update_progress("synthesis", "Root cause analysis written; mapping the blast radius", 86)
        return {}

    @staticmethod
    def _guard_note(hypothesis: dict[str, Any]) -> str:
        """The synthesis is told when Keigan's rules changed an analyst's state, so it does not repeat a claim the rules refused."""
        guard = hypothesis["state_guard_code"]
        return f", the analyst said {hypothesis['proposed_hypothesis_state']} but a rule lowered it ({guard})" if guard else ""

    @staticmethod
    def _flag_high_risk_commands(markdown_text: str) -> str:
        """The synthesis's fenced commands pass the same checks as a hypothesis's steps: a block with an unsafe command is replaced by a note saying why; a risky or secret-printing one is marked."""
        maximum_characters = get_settings().suggested_fix_maximum_command_characters

        def annotate(block_match: re.Match[str]) -> str:
            block_text = block_match.group(1)
            command_lines = [line.strip() for line in block_text.splitlines() if line.strip() and not line.strip().startswith(("#", "//"))]
            for command_line in command_lines:
                reason = check_suggested_command(command_line, None, maximum_characters)
                if reason is not None:
                    return f"> **Command not shown.** Keigan withheld it ({reason.value.replace('_', ' ')}). The step stays; look up the values and write the command yourself.\n"
            warnings = [f"\n> **Prints secrets.** This command shows secrets on the screen.\n" for line in command_lines if command_warnings(line)][:1]
            is_high_risk = classify_command_risk(block_text) == RiskLevel.HIGH
            return block_match.group(0) + ("\n> **High risk.** Confirm with your change process before running this command.\n" if is_high_risk else "") + "".join(warnings)

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
            slo_summaries = [summary for summary in all_slos if summary.get("serviceId") in impacted_ids or summary.get("status") in (SloHealthStatus.AT_RISK, SloHealthStatus.BREACHED)][:10]
        except Exception as slo_error:  # noqa: BLE001 — the blast radius is still built, without SLOs
            logger.warning("Impacted SLOs for application %s could not be read: %s", self.application.application_id, slo_error)
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
    def _outcome_details(self, duration_milliseconds: int) -> dict[str, Any]:
        investigation = self.investigation
        return {
            "status": investigation.investigation_status, "outcome": investigation.investigation_outcome, "proposedOutcome": investigation.proposed_investigation_outcome,
            "outcomeGuard": investigation.outcome_guard_code, "leadingHypothesisId": investigation.leading_hypothesis_id, "overallConfidence": investigation.overall_confidence_score,
            "hypotheses": [
                {"hypothesisId": row.hypothesis_id, "perspective": row.analysis_perspective, "state": row.hypothesis_state, "proposedState": row.proposed_hypothesis_state,
                 "stateGuard": row.state_guard_code, "confidence": row.confidence_score}
                for row in self.hypothesis_rows
            ],
            "coverageGapCount": len(self.coverage.entries), "durationMilliseconds": duration_milliseconds,
        }

    async def _record_conclusion(self, evidence_only: bool) -> None:
        """The outcome step of the trace and the durable audit row (kept 400 days, longer than the trace itself)."""
        investigation = self.investigation
        duration_milliseconds = int(((investigation.completed_at or utc_now()) - (investigation.started_at or investigation.created_at)).total_seconds() * 1000)
        details = self._outcome_details(duration_milliseconds)
        self.recorder.record_outcome(details)
        await AuditService(self.session).record(
            investigation.requested_by_user_principal_name or "system:worker", "investigation.concluded", target_entity_type="investigation", target_entity_id=investigation.investigation_id,
            application_id=investigation.application_id,
            action_details={
                "status": details["status"], "outcome": details["outcome"], "proposedOutcome": details["proposedOutcome"], "outcomeGuard": details["outcomeGuard"],
                "hypothesisStates": {item["perspective"]: item["state"] for item in details["hypotheses"]}, "modelNames": sorted(investigation.model_names_json or []),
                "promptVersions": dict(self.recorder.prompt_versions), "traceStepCount": self.recorder.step_count, "inputTokenCount": investigation.total_input_token_count,
                "outputTokenCount": investigation.total_output_token_count, "coverageGapCount": details["coverageGapCount"],
            },
        )

    async def _complete(self, evidence_only: bool) -> None:
        investigation = self.investigation
        await self.coverage.persist_new(self.session, investigation.investigation_id)  # gaps found after the last stage that stored them (an evidence-only run)
        investigation.investigation_status = InvestigationStatus.COMPLETED_EVIDENCE_ONLY if evidence_only or self.evidence_only else InvestigationStatus.COMPLETED
        investigation.progress_percent, investigation.current_stage_name, investigation.completed_at = 100, InvestigationStage.COMPLETED, utc_now()
        model_names = set(self.ai_caller.model_names)
        if self.ai_caller.uses_estimated_tokens:
            investigation.total_input_token_count, investigation.total_output_token_count = self.ai_caller.estimated_input_tokens, self.ai_caller.estimated_output_tokens
        else:
            await self.ai_caller.gateway.flush_pending_usage_records()  # the last attempts are written after a delay; the totals must include them
            token_rows = (await self.session.execute(select(LlmUsageRecord.input_token_count, LlmUsageRecord.output_token_count, LlmUsageRecord.model_name).where(LlmUsageRecord.investigation_id == investigation.investigation_id))).all()
            investigation.total_input_token_count = sum(row.input_token_count for row in token_rows)
            investigation.total_output_token_count = sum(row.output_token_count for row in token_rows)
            model_names |= {row.model_name for row in token_rows}
        investigation.model_names_json = sorted(model_names)
        await self._record_conclusion(evidence_only)
        if self.incident and self.incident.incident_status in (IncidentStatus.NEW, IncidentStatus.INVESTIGATING) and investigation.investigation_status == InvestigationStatus.COMPLETED:
            self.incident.incident_status = IncidentStatus.IDENTIFIED
        message = "Investigation complete" + (" (evidence only: AI was unavailable)" if investigation.investigation_status == InvestigationStatus.COMPLETED_EVIDENCE_ONLY else "")
        investigation.stage_messages_json = [*(investigation.stage_messages_json or []), {"at": utc_now().isoformat(), "stage": "completed", "message": message}]
        await self.session.commit()

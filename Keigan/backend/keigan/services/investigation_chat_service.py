"""Grounded Q&A about one investigation.

Real provider: a LangGraph ReAct agent with three read-only tools (evidence lookup, knowledge search, safe log query,
at most six tool calls). Mock provider: a deterministic answer assembled from the investigation record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.llm_gateway import LlmUsageContext, ModelTier, PromptSection, estimate_token_count
from keigan.ai.prompt_safety import find_citation_codes, remove_invalid_citations, spotlight
from keigan.config import application_context
from keigan.entities.all_entities import (
    Application, Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, MonitoredService, Runbook,
)
from keigan.exceptions.keigan_exceptions import KeiganException, NotFoundException
from keigan.services.chat_data_query_service import ChatDataQueryService
from keigan.services.knowledge_service import KnowledgeService
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.text_utils import truncate_text
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
MAXIMUM_TOOL_CALLS = 6


@dataclass
class InvestigationContext:
    investigation: Investigation
    application: Application
    context_markdown: str
    evidence_by_code: dict[str, InvestigationEvidence]
    hypotheses: list[InvestigationHypothesis] = field(default_factory=list)
    timeline: list[InvestigationTimelineEvent] = field(default_factory=list)
    runbook_titles: dict[str, str] = field(default_factory=dict)


class InvestigationChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.gateway = application_context.llm_gateway()

    async def answer(self, investigation_id: str, question_text: str, requested_by: str | None, conversation_history: list[dict[str, str]] | None) -> tuple[str, list[dict[str, Any]], int, int]:
        context = await self._load_context(investigation_id)
        masked_question = PiiMasker().mask_text(question_text)
        input_tokens = estimate_token_count(context.context_markdown) + estimate_token_count(masked_question)
        usage_context = LlmUsageContext(application_id=context.application.application_id, investigation_id=investigation_id, requested_by_user_principal_name=requested_by)
        answer_text: str | None = None
        if not self.gateway.is_mock:
            try:
                answer_text = await self._run_agent(context, masked_question, conversation_history or [], usage_context, requested_by or "system:chat")
            except KeiganException:
                raise
            except Exception as agent_error:  # noqa: BLE001 — fall back to a plain grounded answer instead of failing the chat
                logger.warning("Investigation chat agent failed, using plain answer: %s", agent_error)
                answer_text = await self._plain_answer(context, masked_question, conversation_history or [], usage_context)
        if answer_text is None:
            answer_text = self._deterministic_answer(context, masked_question)
        valid_codes = set(context.evidence_by_code) | {f"R{index + 1}" for index in range(len(context.runbook_titles))}
        answer_text = remove_invalid_citations(answer_text, valid_codes)
        citations = [
            {"kind": "evidence", "title": context.evidence_by_code[code].evidence_title, "reference": code} for code in sorted(find_citation_codes(answer_text)) if code in context.evidence_by_code
        ]
        return answer_text, citations, input_tokens, estimate_token_count(answer_text)

    # ── Context ───────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _load_context(self, investigation_id: str) -> InvestigationContext:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("That investigation no longer exists.")
        application = await self.session.get(Application, investigation.application_id)
        incident = await self.session.get(Incident, investigation.incident_id) if investigation.incident_id else None
        evidence = list((await self.session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation_id))).all())
        evidence.sort(key=lambda item: (len(item.evidence_code), item.evidence_code))
        hypotheses = list((await self.session.scalars(
            select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation_id).order_by(InvestigationHypothesis.display_order)
        )).all())
        timeline = list((await self.session.scalars(
            select(InvestigationTimelineEvent).where(InvestigationTimelineEvent.investigation_id == investigation_id).order_by(InvestigationTimelineEvent.event_occurred_at.desc()).limit(15)
        )).all())
        runbook_ids = investigation.matched_runbook_ids_json or []
        runbooks = list((await self.session.scalars(select(Runbook).where(Runbook.runbook_id.in_(runbook_ids)))).all()) if runbook_ids else []
        runbook_titles = {f"R{index + 1}": runbook.runbook_title for index, runbook in enumerate(runbooks)}

        lines = [f"# Investigation for {application.application_name}" + (f" — incident {incident.external_incident_number}: {incident.incident_title}" if incident else "")]
        lines += [f"Status: {investigation.investigation_status}; confidence {investigation.overall_confidence_score}",
                  f"Window: {investigation.investigation_window_start} to {investigation.investigation_window_end}",
                  "## Executive summary", investigation.executive_summary or "(none yet)",
                  "## What went wrong", investigation.what_went_wrong_markdown or "(none)",
                  "## Why it happened", investigation.why_it_happened_markdown or "(none)",
                  "## How to fix", investigation.how_to_fix_markdown or "(none)", "## Hypotheses"]
        lines += [
            f"- {'LEADING ' if hypothesis.is_leading_hypothesis else ''}[{hypothesis.analysis_perspective}] {hypothesis.hypothesis_title} (confidence {hypothesis.confidence_score:.2f}; supports {hypothesis.supporting_evidence_codes_json}; contradicts {hypothesis.contradicting_evidence_codes_json})"
            for hypothesis in hypotheses
        ]
        lines.append("## Evidence index")
        lines += [f"- [{item.evidence_code}] {item.evidence_category} / {item.evidence_title}: {truncate_text(item.evidence_summary or '', 300)} (signal {item.signal_strength}, {item.matched_record_count} matching records)" for item in evidence]
        lines.append("## Timeline (newest first)")
        lines += [f"- {event.event_occurred_at:%Y-%m-%d %H:%M} {event.event_title}" for event in timeline]
        lines.append("## Matched runbooks")
        lines += [f"- [{code}] {title}" for code, title in runbook_titles.items()]
        try:
            topology = await KnowledgeService(self.session).get_current_topology_graph(application.application_id)
            node_names = [str(node.get("label") or node.get("name") or node.get("id")) for node in (topology or {}).get("nodes", [])][:40]
            if node_names:
                lines += ["## Topology nodes", ", ".join(node_names)]
        except Exception as topology_error:  # noqa: BLE001 — topology is optional context
            logger.info("Topology unavailable for investigation chat: %s", topology_error)
        return InvestigationContext(investigation, application, "\n".join(lines), {item.evidence_code: item for item in evidence}, hypotheses, timeline, runbook_titles)

    # ── Real provider paths ───────────────────────────────────────────────────────────────────────────────────────────
    def _system_prompt(self, application_name: str) -> str:
        return application_context.prompt_library().render("investigation_chat", application_name=application_name)

    async def _plain_answer(self, context: InvestigationContext, question: str, history: list[dict[str, str]], usage_context: LlmUsageContext) -> str:
        result = await self.gateway.generate_text(
            feature_name="investigation_chat", model_tier=ModelTier.DEEP, system_prompt=self._system_prompt(context.application.application_name),
            prompt_sections=[
                PromptSection("Investigation context", context.context_markdown, is_untrusted=True, source_label=f"investigation:{context.investigation.investigation_id}"),
                PromptSection("Conversation so far", "\n".join(f"{turn['role']}: {truncate_text(turn['content'], 600)}" for turn in history[-8:]) or "(none)", is_untrusted=True, source_label="chat:history"),
                PromptSection("Question", question, is_untrusted=True, source_label="chat:user-question"),
            ],
            usage_context=usage_context,
        )
        return result.text

    async def _run_agent(self, context: InvestigationContext, question: str, history: list[dict[str, str]], usage_context: LlmUsageContext, requested_by: str) -> str:
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.tools import StructuredTool
        from langgraph.prebuilt import create_react_agent

        application_id = context.application.application_id
        tool_call_count = 0

        def within_budget() -> bool:
            nonlocal tool_call_count
            tool_call_count += 1
            return tool_call_count <= MAXIMUM_TOOL_CALLS

        async def get_evidence(code: str) -> str:
            if not within_budget():
                return "Tool budget used up; answer with what you have."
            item = context.evidence_by_code.get(code.strip().upper())
            if item is None:
                return f"No evidence with code {code}. Known codes: {', '.join(context.evidence_by_code)}"
            return spotlight(f"{item.evidence_title}\n{item.evidence_summary}\nPatterns: {item.condensed_patterns_json}\nQuery: {item.query_text}", f"evidence:{item.evidence_code}")

        async def search_knowledge(query: str) -> str:
            if not within_budget():
                return "Tool budget used up; answer with what you have."
            grounding = await KnowledgeService(self.session).build_grounding_context(application_id, query, token_budget=2500)
            return spotlight(grounding.knowledge_markdown or "No matching knowledge found.", "knowledge:search")

        async def run_log_query(service_name: str, question: str, lookback_minutes: int = 60) -> str:  # noqa: A002 — tool argument name shown to the model
            if not within_budget():
                return "Tool budget used up; answer with what you have."
            service = await self.session.scalar(select(MonitoredService).where(MonitoredService.application_id == application_id, MonitoredService.service_name == service_name))
            if service is None:
                return f"No service named {service_name} in this application."
            end = utc_now()
            try:
                outcome = await ChatDataQueryService(self.session).run(
                    service=service, question_text=question, wants_failures=True, wants_pattern=False, time_range_start=end - timedelta(minutes=min(max(lookback_minutes, 5), 1440)),
                    time_range_end=end, requested_by=requested_by, usage_context=usage_context,
                )
            except KeiganException as query_error:
                return f"The query could not run: {query_error}"
            return spotlight(f"Query: {outcome.query_text}\nRows: {outcome.row_count}\nTotal: {outcome.total}\nSample: {outcome.rows[:10]}", f"query:{service_name}")

        tools = [
            StructuredTool.from_function(coroutine=get_evidence, name="get_evidence", description="Return one evidence item by code, for example E3."),
            StructuredTool.from_function(coroutine=search_knowledge, name="search_knowledge", description="Search this application's knowledge base (runbooks, architecture, documents)."),
            StructuredTool.from_function(coroutine=run_log_query, name="run_log_query", description="Run a read-only log query for one service of this application over the last N minutes."),
        ]
        agent = create_react_agent(self.gateway.chat_model(ModelTier.DEEP), tools, prompt=f"{self._system_prompt(context.application.application_name)}")
        messages: list[Any] = [
            HumanMessage(content=spotlight(context.context_markdown, f"investigation:{context.investigation.investigation_id}")),
            *[(HumanMessage if turn["role"] == "user" else AIMessage)(content=truncate_text(turn["content"], 800)) for turn in history[-6:]],
            HumanMessage(content=spotlight(question, "chat:user-question")),
        ]
        result = await agent.ainvoke({"messages": messages}, {"recursion_limit": 2 * MAXIMUM_TOOL_CALLS + 3})
        final_messages = result["messages"]
        input_tokens = sum((getattr(message, "usage_metadata", None) or {}).get("input_tokens", 0) for message in final_messages)
        output_tokens = sum((getattr(message, "usage_metadata", None) or {}).get("output_tokens", 0) for message in final_messages)
        await self.gateway.record_external_usage(feature_name="investigation_chat", model_tier=ModelTier.DEEP, input_token_count=input_tokens, output_token_count=output_tokens, usage_context=usage_context)
        content = final_messages[-1].content
        return content if isinstance(content, str) else " ".join(part.get("text", "") for part in content if isinstance(part, dict))

    # ── Mock provider ─────────────────────────────────────────────────────────────────────────────────────────────────
    def _deterministic_answer(self, context: InvestigationContext, question: str) -> str:
        investigation, lowered = context.investigation, question.lower()
        leading = next((hypothesis for hypothesis in context.hypotheses if hypothesis.is_leading_hypothesis), context.hypotheses[0] if context.hypotheses else None)

        def cite(codes: list[str] | None) -> str:
            return " ".join(f"[{code}]" for code in (codes or [])[:3] if code in context.evidence_by_code)

        if any(word in lowered for word in ("database", "sql", "why not", "rule out", "ruled out")):
            others = [hypothesis for hypothesis in context.hypotheses if not hypothesis.is_leading_hypothesis]
            database = next((hypothesis for hypothesis in others if "database" in hypothesis.hypothesis_title.lower() or "sql" in hypothesis.hypothesis_title.lower()), others[0] if others else None)
            if database is None or leading is None:
                return "The investigation did not record a competing hypothesis for that, so I can't say why it was ruled out."
            return (f"The leading explanation is \"{leading.hypothesis_title}\" ({leading.confidence_score:.0%} confidence) {cite(leading.supporting_evidence_codes_json)}. "
                    f"\"{database.hypothesis_title}\" scored lower at {database.confidence_score:.0%}; evidence against it: {cite(database.contradicting_evidence_codes_json) or 'no direct contradicting evidence was recorded'}.")
        if any(word in lowered for word in ("changed", "change", "last hour", "recent", "deploy")):
            change_evidence = [item for item in context.evidence_by_code.values() if item.evidence_category == "change_event"]
            if change_evidence:
                change_lines = [f"- [{item.evidence_code}] {item.evidence_title}: {truncate_text(item.evidence_summary or '', 220)}" for item in change_evidence[:4]]
                return "These changes landed in or just before the incident window (from the Azure activity log):\n" + "\n".join(change_lines)
            change_events = [event for event in context.timeline if event.event_type in ("deployment", "configuration_change") or event.event_source not in ("keigan",)]
            if not change_events:
                return "No deployments or configuration changes were recorded around this incident, which points away from a change-related cause."
            return "Recorded events around the incident:\n" + "\n".join(f"- {event.event_occurred_at:%H:%M} {event.event_title}" for event in change_events[:6])
        if any(word in lowered for word in ("executive", "status update", "stakeholder", "management")):
            return f"**Status update.** {investigation.executive_summary or 'The investigation is still in progress.'} " + (f"Next step: {truncate_text(investigation.how_to_fix_markdown or '', 240)}" if investigation.how_to_fix_markdown else "")
        if any(word in lowered for word in ("new engineer", "explain", "simple", "beginner")):
            return (f"In plain terms: {investigation.what_went_wrong_markdown or investigation.executive_summary or 'the investigation has not produced a summary yet.'}\n\n"
                    f"Why it happened: {investigation.why_it_happened_markdown or 'not yet established.'}")
        if any(word in lowered for word in ("fix", "resolve", "mitigate", "runbook", "next step")):
            return (investigation.how_to_fix_markdown or "No fix has been proposed yet.") + ("\n\nRelated runbooks: " + ", ".join(f"[{code}] {title}" for code, title in context.runbook_titles.items()) if context.runbook_titles else "")
        if "evidence" in lowered:
            return "Evidence collected:\n" + "\n".join(f"- [{code}] {item.evidence_title}" for code, item in list(context.evidence_by_code.items())[:8])
        summary = investigation.executive_summary or "The investigation is still running."
        return f"{summary} {cite(leading.supporting_evidence_codes_json) if leading else ''}".strip()

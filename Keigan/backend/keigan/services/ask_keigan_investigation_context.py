"""The digest of one investigation that the investigation scope of Ask Keigan puts in front of the model, and the sources it may cite (spec 23, 4.4.2).

The digest is a markdown summary (executive summary, hypotheses, evidence index, newest timeline events, matched runbooks, topology node names). It is
sent to the model as untrusted data, so the model can answer common questions without a tool call and knows which ``E#`` and ``R#`` codes exist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.entities.all_entities import (
    Application, Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, Runbook,
)
from keigan.services.ask_keigan_run_state import AnswerCitation
from keigan.services.knowledge_service import KnowledgeService
from keigan.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)
TOPOLOGY_UNREADABLE_LINE = "(the application map could not be read just now; the get_topology tool may still be able to)"


@dataclass(frozen=True)
class InvestigationContext:
    application: Application
    digest_markdown: str
    evidence_citations: dict[str, AnswerCitation]
    runbook_citations: dict[str, AnswerCitation]


async def load_investigation_context(session: AsyncSession, investigation: Investigation) -> InvestigationContext:
    settings = get_settings()
    application = await session.get(Application, investigation.application_id)
    if application is None:
        raise LookupError(f"Investigation {investigation.investigation_id} belongs to an application that does not exist.")
    incident = await session.get(Incident, investigation.incident_id) if investigation.incident_id else None
    evidence = list((await session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation.investigation_id))).all())
    evidence.sort(key=lambda item: (len(item.evidence_code), item.evidence_code))
    hypotheses = list((await session.scalars(
        select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation.investigation_id).order_by(InvestigationHypothesis.display_order)
    )).all())
    timeline = list((await session.scalars(
        select(InvestigationTimelineEvent).where(InvestigationTimelineEvent.investigation_id == investigation.investigation_id)
        .order_by(InvestigationTimelineEvent.event_occurred_at.desc()).limit(settings.ask_keigan_digest_timeline_events)
    )).all())
    runbook_ids = investigation.matched_runbook_ids
    runbooks = list((await session.scalars(select(Runbook).where(Runbook.runbook_id.in_(runbook_ids)))).all()) if runbook_ids else []
    runbook_citations = {
        f"R{index + 1}": AnswerCitation(code=f"R{index + 1}", title=runbook.runbook_title, runbook_id=runbook.runbook_id) for index, runbook in enumerate(runbooks)
    }
    evidence_citations = {item.evidence_code: AnswerCitation(code=item.evidence_code, title=item.evidence_title, evidence_code=item.evidence_code) for item in evidence}

    lines = [f"# Investigation for {application.application_name}" + (f" — incident {incident.external_incident_number}: {incident.incident_title}" if incident else "")]
    lines += [
        f"Status: {investigation.investigation_status}; outcome {investigation.investigation_outcome or 'not recorded'}; confidence {investigation.overall_confidence_score}",
        f"Window: {investigation.investigation_window_start} to {investigation.investigation_window_end}",
        "## Executive summary", investigation.executive_summary or "(none yet)",
        "## What went wrong", investigation.what_went_wrong_markdown or "(none)",
        "## Why it happened", investigation.why_it_happened_markdown or "(none)",
        "## How to fix", investigation.how_to_fix_markdown or "(none)", "## Hypotheses",
    ]
    lines += [
        f"- {'LEADING ' if hypothesis.is_leading_hypothesis else ''}[{hypothesis.analysis_perspective}] {hypothesis.hypothesis_title} "
        f"(state {hypothesis.hypothesis_state or 'not recorded'}; confidence {hypothesis.confidence_score:.2f}; supports {hypothesis.supporting_evidence_codes_json}; contradicts {hypothesis.contradicting_evidence_codes_json})"
        for hypothesis in hypotheses
    ]
    lines.append("## Evidence index")
    lines += [
        f"- [{item.evidence_code}] {item.evidence_category} / {item.evidence_title}: {truncate_text(item.evidence_summary or '', settings.ask_keigan_digest_evidence_summary_characters)} "
        f"(signal {item.signal_strength}, {item.matched_record_count} matching records)"
        for item in evidence
    ]
    lines.append("## Timeline (newest first)")
    lines += [f"- {event.event_occurred_at:%Y-%m-%d %H:%M} {event.event_title}" for event in timeline]
    lines.append("## Matched runbooks")
    lines += [f"- [{code}] {citation.title}" for code, citation in runbook_citations.items()]
    lines += await _topology_lines(session, application.application_id)
    return InvestigationContext(application, "\n".join(lines), evidence_citations, runbook_citations)


async def _topology_lines(session: AsyncSession, application_id: str) -> list[str]:
    """The topology names are optional context: when the map cannot be read (the database failed) the digest says so, so the model does not take its absence for "no topology",
    and the failure is logged with the application. Anything else that goes wrong is a bug and is not hidden here."""
    try:
        topology = await KnowledgeService(session).get_current_topology_graph(application_id)
    except SQLAlchemyError:
        logger.warning("The topology of application %s could not be read for the Ask Keigan investigation digest.", application_id, exc_info=True)
        return ["## Topology nodes", TOPOLOGY_UNREADABLE_LINE]
    node_names = [str(node.get("label") or node.get("name") or node.get("id")) for node in (topology or {}).get("nodes", [])][:get_settings().ask_keigan_digest_topology_nodes]
    return ["## Topology nodes", ", ".join(node_names)] if node_names else []

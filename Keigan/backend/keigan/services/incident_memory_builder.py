"""Builds the memory of one investigated incident (spec 34, 4.2 and 4.5): the masked, shortened account of what happened, and the facts another incident can share.

The two functions at the top choose the texts and are pure. ``IncidentMemoryBuilder.refresh_entry`` is the handler of the job ``refresh_incident_memory_entry``: it loads one investigation,
builds its entry and keys (one live entry per investigation, replaced in place), and settles which entry stands for the incident when it was investigated more than once (decision M7).
``load_investigation_facts`` is shared with the retriever, so the current investigation and a past one are described the same way.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import Settings, get_settings
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.application_entities import MonitoredService
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, PostmortemReport
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryKey
from keigan.entities.status_values import (
    EvidenceCheckOutcome, IncidentMemoryCauseSource, IncidentMemoryEntryStatus, IncidentMemoryFixSource, InvestigationOutcome, InvestigationStatus, PostmortemStatus, RiskLevel,
)
from keigan.services.incident_memory_keys import MemoryFacts, alert_rule_fact, build_match_keys, change_operation_of, dependency_target_of
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.text_utils import term_frequencies, truncate_text
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue

REFRESH_JOB_TYPE = "refresh_incident_memory_entry"  # must stay a key of JOB_HANDLER_REFERENCES (a test checks it)
CHANGE_EVIDENCE_CATEGORY = "change_event"  # the category evidence collection gives the Activity Log changes
RESOLUTION_EVENT_TYPE = "incident_resolved"
UNTITLED_INVESTIGATION = "Investigation without an incident"
MAXIMUM_TITLE_CHARACTERS = 500
SIGNAL_LEVELS = (RiskLevel.HIGH, RiskLevel.MEDIUM)  # only a medium or high signal says something about the cause


async def enqueue_memory_refresh(session: AsyncSession, investigation_id: str) -> None:
    """Asks for the entry of one investigation to be rebuilt; a second request while one is queued merges with it."""
    await JobQueue(session).enqueue(REFRESH_JOB_TYPE, {"investigation_id": investigation_id}, deduplication_key=f"incident_memory:{investigation_id}", priority_number=80)


async def enqueue_memory_refresh_for_incident(session: AsyncSession, incident_id: str) -> None:
    """The latest completed investigation of an incident: what a resolution or an approved postmortem changes the memory of."""
    investigation_id = await session.scalar(
        select(Investigation.investigation_id)
        .where(Investigation.incident_id == incident_id, Investigation.investigation_status == InvestigationStatus.COMPLETED).order_by(Investigation.created_at.desc()).limit(1)
    )
    if investigation_id:
        await enqueue_memory_refresh(session, investigation_id)


@dataclass(frozen=True)
class ChosenText:
    text: str | None
    source: str


def choose_cause(*, postmortem_root_cause: str | None, analysis_text: str | None, outcome: str | None) -> ChosenText:
    """A person's words first: the root cause of an approved postmortem, else Keigan's own analysis, and that only when the investigation found a cause (decision M6)."""
    if (postmortem_root_cause or "").strip():
        return ChosenText(postmortem_root_cause.strip(), IncidentMemoryCauseSource.POSTMORTEM)
    found_a_cause = outcome in (None, InvestigationOutcome.CAUSE_IDENTIFIED)  # an older investigation has no outcome and is trusted as before
    if found_a_cause and (analysis_text or "").strip():
        return ChosenText(analysis_text.strip(), IncidentMemoryCauseSource.INVESTIGATION)
    return ChosenText(None, IncidentMemoryCauseSource.NONE)


def choose_fix(*, resolution_note: str | None, plan_overview: str | None, hypothesis_fix_summary: str | None) -> ChosenText:
    """What fixed it: the note of the person who resolved the incident, else the investigation's recommended plan, else the leading hypothesis's fix."""
    for text, source in (
        (resolution_note, IncidentMemoryFixSource.RESOLUTION_NOTE), (plan_overview, IncidentMemoryFixSource.FIX_PLAN), (hypothesis_fix_summary, IncidentMemoryFixSource.HYPOTHESIS_FIX),
    ):
        if (text or "").strip():
            return ChosenText(text.strip(), source)
    return ChosenText(None, IncidentMemoryFixSource.NONE)


@dataclass(frozen=True)
class InvestigationFacts:
    """What is known about one investigation, before masking: the shareable facts, the words, and where it sits."""

    application_id: str
    incident_id: str | None
    title: str
    wording: str  # title, description, summary and symptoms: the words a later incident is compared with
    occurred_at: datetime
    service_ids: list[str]
    facts: MemoryFacts


@dataclass(frozen=True)
class EvidenceFacts:
    error_templates: list[str]
    change_operations: list[str]
    dependency_targets: list[str]


def _evidence_facts(evidence_rows: Sequence[InvestigationEvidence]) -> EvidenceFacts:
    """Only rows with a medium or high signal, no rule-outs and no suspected prompt injection say anything about the cause. A change row's patterns are changes, not errors."""
    templates: list[str] = []
    operations: list[str] = []
    targets: list[str] = []
    for row in evidence_rows:
        if row.signal_strength not in SIGNAL_LEVELS or row.possible_prompt_injection or row.check_outcome == EvidenceCheckOutcome.NO_SIGNAL:
            continue
        for pattern in (item for item in (row.condensed_patterns_json or []) if isinstance(item, dict)):
            if row.evidence_category == CHANGE_EVIDENCE_CATEGORY:
                operation = change_operation_of(pattern)
                if operation:
                    operations.append(operation)
                continue
            template = str(pattern.get("template", ""))
            templates.append(template)
            target = dependency_target_of(template)
            if target:
                targets.append(target)
    return EvidenceFacts(templates, list(dict.fromkeys(operations)), list(dict.fromkeys(targets)))


async def _alert_rules(session: AsyncSession, investigation_id: str) -> list[tuple[str, str]]:
    """The rules of the alerts that were grouped into this investigation."""
    rules = (await session.execute(
        select(Alert.rule_identifier, Alert.rule_name).where(Alert.alert_group_id.in_(select(AlertGroup.alert_group_id).where(AlertGroup.investigation_id == investigation_id)))
    )).all()
    return list(dict.fromkeys(fact for fact in (alert_rule_fact(identifier, name) for identifier, name in rules) if fact))


async def load_investigation_facts(session: AsyncSession, investigation: Investigation) -> InvestigationFacts:
    incident = await session.get(Incident, investigation.incident_id) if investigation.incident_id else None
    triage = investigation.triage_result_json or {}
    service_ids = list(dict.fromkeys([*investigation.investigated_service_ids, *(incident.affected_service_ids if incident else [])]))
    services = list((await session.scalars(select(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))).all()) if service_ids else []
    evidence_rows = list((await session.scalars(select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == investigation.investigation_id))).all())
    title = (incident.incident_title if incident else None) or str(triage.get("incident_summary") or "").strip() or UNTITLED_INVESTIGATION
    wording = "\n".join(
        part for part in (title, incident.incident_description if incident else None, str(triage.get("incident_summary") or ""), "\n".join(str(symptom) for symptom in triage.get("key_symptoms") or [])) if part
    )
    occurred_at = (incident.opened_at if incident else None) or investigation.investigation_window_start or investigation.created_at
    found = _evidence_facts(evidence_rows)
    facts = MemoryFacts(
        services={service.service_id: service.service_name for service in services}, resource_identifiers=[service.external_resource_identifier or "" for service in services],
        error_templates=found.error_templates, incident_category=(incident.incident_category if incident else None) or triage.get("incident_category"),
        alert_rules=await _alert_rules(session, investigation.investigation_id), change_operations=found.change_operations, dependency_targets=found.dependency_targets,
    )
    return InvestigationFacts(investigation.application_id, investigation.incident_id, truncate_text(title, MAXIMUM_TITLE_CHARACTERS), wording, occurred_at, service_ids, facts)


class IncidentMemoryBuilder:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings: Settings = get_settings()

    async def refresh_entry(self, investigation_id: str) -> dict[str, str]:
        """The job: (re)build the entry of one completed investigation. An investigation that is gone, still running or evidence-only has none to build."""
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            return {"status": "missing"}
        if investigation.investigation_status != InvestigationStatus.COMPLETED:
            return {"status": "skipped"}
        known = await load_investigation_facts(self.session, investigation)
        masker = PiiMasker()
        cause = await self._cause(investigation)
        fix = await self._fix(investigation, known.incident_id)
        maximum = self.settings.incident_memory_text_maximum_characters
        title_text = masker.mask_text(known.title)
        cause_text = truncate_text(masker.mask_text(cause.text), maximum) if cause.text else None
        fix_text = truncate_text(masker.mask_text(fix.text), maximum) if fix.text else None
        search_terms = term_frequencies("\n".join(part for part in (masker.mask_text(known.wording), cause_text, fix_text) if part))
        entry = await self.session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == investigation_id))
        if entry is None:
            entry = IncidentMemoryEntry(application_id=known.application_id, investigation_id=investigation_id)
            self.session.add(entry)
        entry.incident_id, entry.occurred_at, entry.incident_title_text = known.incident_id, known.occurred_at, title_text
        entry.cause_text, entry.cause_source, entry.fix_text, entry.fix_source = cause_text, cause.source, fix_text, fix.source
        entry.search_terms_json, entry.service_ids_json, entry.built_at = search_terms, known.service_ids, utc_now()
        if entry.entry_status != IncidentMemoryEntryStatus.HIDDEN:
            entry.entry_status = IncidentMemoryEntryStatus.ACTIVE
        await self.session.flush()
        await self.session.execute(delete(IncidentMemoryKey).where(IncidentMemoryKey.incident_memory_entry_id == entry.incident_memory_entry_id))
        for key in build_match_keys(known.facts):
            self.session.add(IncidentMemoryKey(incident_memory_entry_id=entry.incident_memory_entry_id, key_kind=key.kind, key_value_hash=key.value_hash, key_display_text=masker.mask_text(key.display_text)))
        await self.session.flush()
        if known.incident_id:
            await self.settle_incident(known.incident_id)
        return {"status": "built", "entryId": entry.incident_memory_entry_id}

    async def settle_incident(self, incident_id: str) -> None:
        """One live entry per incident (decision M7): the latest completed investigation with a verdict, else the latest completed one. The others are superseded; a hidden entry stays hidden."""
        rows = (await self.session.execute(
            select(IncidentMemoryEntry, Investigation).join(Investigation, Investigation.investigation_id == IncidentMemoryEntry.investigation_id)
            .where(IncidentMemoryEntry.incident_id == incident_id)
        )).all()
        if not rows:
            return
        newest_first = sorted(rows, key=lambda row: row.Investigation.completed_at or row.Investigation.created_at, reverse=True)
        winner = next((row for row in newest_first if row.Investigation.user_feedback_verdict), newest_first[0])
        for row in rows:
            if row.IncidentMemoryEntry.entry_status == IncidentMemoryEntryStatus.HIDDEN:
                continue
            row.IncidentMemoryEntry.entry_status = IncidentMemoryEntryStatus.ACTIVE if row is winner else IncidentMemoryEntryStatus.SUPERSEDED
        await self.session.flush()

    async def _cause(self, investigation: Investigation) -> ChosenText:
        root_cause: str | None = None
        if investigation.incident_id:
            postmortem = await self.session.scalar(
                select(PostmortemReport).where(PostmortemReport.incident_id == investigation.incident_id, PostmortemReport.report_status == PostmortemStatus.FINAL).order_by(PostmortemReport.finalized_at.desc())
            )
            sections: dict[str, Any] = (postmortem.report_sections_json if postmortem else None) or {}
            root_cause = str(sections.get("root_cause") or "") or None
        return choose_cause(
            postmortem_root_cause=root_cause, analysis_text=investigation.why_it_happened_markdown or investigation.executive_summary, outcome=investigation.investigation_outcome,
        )

    async def _fix(self, investigation: Investigation, incident_id: str | None) -> ChosenText:
        note: str | None = None
        if incident_id:
            note = await self.session.scalar(
                select(InvestigationTimelineEvent.event_details_markdown)
                .where(InvestigationTimelineEvent.incident_id == incident_id, InvestigationTimelineEvent.event_type == RESOLUTION_EVENT_TYPE, InvestigationTimelineEvent.event_details_markdown.is_not(None))
                .order_by(InvestigationTimelineEvent.event_occurred_at.desc()).limit(1)
            )
        leading = await self.session.scalar(
            select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation.investigation_id, InvestigationHypothesis.is_leading_hypothesis.is_(True))
        )
        fix_summary = str(((leading.proposed_fix_json if leading else None) or {}).get("summary") or "") or None
        return choose_fix(resolution_note=note, plan_overview=(investigation.fix_plan_json or {}).get("overview_markdown"), hypothesis_fix_summary=fix_summary)

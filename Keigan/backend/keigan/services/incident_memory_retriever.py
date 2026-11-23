"""Finds the remembered incidents that look like the current one (spec 34, 4.4): candidates from the database, then the pure scoring.

Behind a small protocol so another way of finding candidates (a vector index) can be added without touching the service that asks. The caller passes the applications it may read;
nothing outside them is ever loaded.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import Settings
from keigan.entities.application_entities import MonitoredService
from keigan.entities.incident_entities import Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryKey
from keigan.entities.status_values import IncidentMemoryEntryStatus
from keigan.services.incident_memory_builder import InvestigationFacts
from keigan.services.incident_memory_keys import build_match_keys
from keigan.services.incident_memory_scoring import CurrentIncident, KeyRef, MemoryCandidate, ScoredMatch, score_matches, similarity_config
from keigan.utils.text_utils import tokenize_for_search
from keigan.utils.time_utils import utc_now


@dataclass(frozen=True)
class CurrentInvestigation:
    investigation_id: str
    facts: InvestigationFacts


@dataclass(frozen=True)
class RetrievedMatch:
    match: ScoredMatch
    entry: IncidentMemoryEntry
    verdict: str | None  # the admin's verdict on the past investigation, as it stands now


class SimilarIncidentRetriever(Protocol):
    async def find(self, current: CurrentInvestigation, allowed_application_ids: Collection[str]) -> list[RetrievedMatch]: ...


class StructuredKeywordRetriever:
    """Shared facts (hashed keys) first, then wording inside the same application."""

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    async def find(self, current: CurrentInvestigation, allowed_application_ids: Collection[str], *, today: datetime | None = None) -> list[RetrievedMatch]:
        if not allowed_application_ids:
            return []
        facts = current.facts
        keys = build_match_keys(facts.facts)
        terms = tuple(dict.fromkeys(tokenize_for_search(facts.wording)))
        entries = await self._candidate_entries(current, allowed_application_ids, keys)
        if not entries:
            return []
        candidates = await self._candidates(entries)
        config = similarity_config(
            minimum_score=self.settings.incident_memory_minimum_score, stale_after_days=self.settings.incident_memory_stale_after_days, maximum_shown=self.settings.incident_memory_maximum_shown,
        )
        scored = score_matches(CurrentIncident(facts.application_id, keys, terms), candidates, config, today or utc_now())
        by_id = {entry.incident_memory_entry_id: entry for entry in entries}
        verdicts = {candidate.entry_id: candidate.verdict for candidate in candidates}
        return [RetrievedMatch(match, by_id[match.entry_id], verdicts[match.entry_id]) for match in scored]

    async def _candidate_entries(self, current: CurrentInvestigation, allowed_application_ids: Collection[str], keys: list[KeyRef]) -> list[IncidentMemoryEntry]:
        facts = current.facts
        base = (
            select(IncidentMemoryEntry)
            .where(
                IncidentMemoryEntry.application_id.in_(list(allowed_application_ids)), IncidentMemoryEntry.entry_status == IncidentMemoryEntryStatus.ACTIVE,
                IncidentMemoryEntry.occurred_at < facts.occurred_at, IncidentMemoryEntry.investigation_id != current.investigation_id,
            )
        )
        if facts.incident_id:
            base = base.where((IncidentMemoryEntry.incident_id.is_(None)) | (IncidentMemoryEntry.incident_id != facts.incident_id))
        found: dict[str, IncidentMemoryEntry] = {}
        if keys:
            sharing = select(IncidentMemoryKey.incident_memory_entry_id).where(IncidentMemoryKey.key_value_hash.in_([key.value_hash for key in keys]))
            for entry in (await self.session.scalars(base.where(IncidentMemoryEntry.incident_memory_entry_id.in_(sharing)))).all():
                found[entry.incident_memory_entry_id] = entry
        recent_same_application = base.where(IncidentMemoryEntry.application_id == facts.application_id).order_by(IncidentMemoryEntry.occurred_at.desc()).limit(self.settings.incident_memory_keyword_candidate_limit)
        for entry in (await self.session.scalars(recent_same_application)).all():
            found.setdefault(entry.incident_memory_entry_id, entry)
        return list(found.values())

    async def _candidates(self, entries: list[IncidentMemoryEntry]) -> list[MemoryCandidate]:
        entry_ids = [entry.incident_memory_entry_id for entry in entries]
        keys_by_entry: dict[str, list[KeyRef]] = {}
        for key in (await self.session.scalars(select(IncidentMemoryKey).where(IncidentMemoryKey.incident_memory_entry_id.in_(entry_ids)))).all():
            keys_by_entry.setdefault(key.incident_memory_entry_id, []).append(KeyRef(key.key_kind, key.key_value_hash, key.key_display_text))
        verdicts = dict((await self.session.execute(select(Investigation.investigation_id, Investigation.user_feedback_verdict).where(Investigation.investigation_id.in_([entry.investigation_id for entry in entries])))).all())
        every_service_id = {service_id for entry in entries for service_id in entry.service_ids_json or []}
        existing = set((await self.session.scalars(select(MonitoredService.service_id).where(MonitoredService.service_id.in_(every_service_id)))).all()) if every_service_id else set()
        return [
            MemoryCandidate(
                entry.incident_memory_entry_id, entry.application_id, verdicts.get(entry.investigation_id), entry.occurred_at, keys_by_entry.get(entry.incident_memory_entry_id, []),
                frozenset((entry.search_terms_json or {}).keys()), not entry.service_ids_json or any(service_id in existing for service_id in entry.service_ids_json),
            )
            for entry in entries
        ]

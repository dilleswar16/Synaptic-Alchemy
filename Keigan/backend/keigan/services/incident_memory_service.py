"""What a person sees and does with the memory of past incidents (spec 34, 4.7): the matches for an investigation, "was this relevant?", and hiding an entry.

Matches are worked out as the person asking, from the applications they may read; an entry they cannot read is the same as one that does not exist (decision M8), so every unreadable
or unknown entry answers "not found" and never "forbidden".
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import Settings, get_settings
from keigan.dtos.incident_memory_dtos import MatchReasonDto, MemoryApplicationDto, SimilarIncidentDto, SimilarIncidentsResponse
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryRelevanceFeedback
from keigan.entities.status_values import IncidentMemoryCauseSource, IncidentMemoryEntryStatus, IncidentMemoryRelevanceVerdict, InvestigationFeedbackVerdict, InvestigationStatus
from keigan.exceptions.keigan_exceptions import NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.incident_memory_builder import IncidentMemoryBuilder, load_investigation_facts
from keigan.services.incident_memory_retriever import CurrentInvestigation, RetrievedMatch, SimilarIncidentRetriever, StructuredKeywordRetriever
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now

NOT_FOUND_TEXT = "The past incident was not found."
AVAILABLE_STATUSES = (InvestigationStatus.COMPLETED, InvestigationStatus.COMPLETED_EVIDENCE_ONLY)  # a running investigation has no evidence to match with yet


class IncidentMemoryService:
    def __init__(self, session: AsyncSession, retriever: SimilarIncidentRetriever | None = None):
        self.session = session
        self.settings: Settings = get_settings()
        self.authorization = AuthorizationService(session)
        self.retriever: SimilarIncidentRetriever = retriever or StructuredKeywordRetriever(session, self.settings)

    # ── Reading ────────────────────────────────────────────────────────────────
    async def similar_incidents(self, current_user: CurrentUser, investigation_id: str) -> SimilarIncidentsResponse:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("The investigation was not found.")
        await self.authorization.ensure_application_reader(current_user, investigation.application_id)
        if investigation.investigation_status not in AVAILABLE_STATUSES:
            return SimilarIncidentsResponse(items=[], is_available=False)
        readable = await self.authorization.readable_application_ids(current_user)
        current = CurrentInvestigation(investigation_id, await load_investigation_facts(self.session, investigation))
        matches = await self.retriever.find(current, readable)
        return SimilarIncidentsResponse(items=await self._dtos(current_user, investigation, matches), is_available=True)

    async def _dtos(self, current_user: CurrentUser, investigation: Investigation, matches: list[RetrievedMatch]) -> list[SimilarIncidentDto]:
        if not matches:
            return []
        entries = [match.entry for match in matches]
        applications = {row.application_id: row for row in (await self.session.scalars(select(Application).where(Application.application_id.in_({entry.application_id for entry in entries})))).all()}
        incident_ids = {entry.incident_id for entry in entries if entry.incident_id}
        incident_numbers = dict((await self.session.execute(select(Incident.incident_id, Incident.external_incident_number).where(Incident.incident_id.in_(incident_ids)))).all()) if incident_ids else {}
        mine = dict((await self.session.execute(
            select(IncidentMemoryRelevanceFeedback.incident_memory_entry_id, IncidentMemoryRelevanceFeedback.relevance_verdict).where(
                IncidentMemoryRelevanceFeedback.investigation_id == investigation.investigation_id, IncidentMemoryRelevanceFeedback.user_principal_name == current_user.user_principal_name,
            )
        )).all())
        administered = await self.authorization.editable_application_ids(current_user)
        items: list[SimilarIncidentDto] = []
        for match in matches:
            entry = match.entry
            application = applications[entry.application_id]
            was_marked_incorrect = match.verdict == InvestigationFeedbackVerdict.INCORRECT and entry.cause_source == IncidentMemoryCauseSource.INVESTIGATION
            items.append(SimilarIncidentDto(
                memory_entry_id=entry.incident_memory_entry_id, application=MemoryApplicationDto(application_id=application.application_id, application_name=application.application_name),
                is_same_application=entry.application_id == investigation.application_id, incident_id=entry.incident_id, incident_number=incident_numbers.get(entry.incident_id),
                incident_title=entry.incident_title_text, investigation_id=entry.investigation_id, occurred_at=entry.occurred_at, age_days=match.match.age_days, verdict=match.verdict,
                cause_text=None if was_marked_incorrect else entry.cause_text, cause_source=entry.cause_source, fix_text=entry.fix_text, fix_source=entry.fix_source,
                match_reasons=[MatchReasonDto(key_kind=reason.kind, display_text=reason.display_text) for reason in match.match.reasons], is_stale=match.match.is_stale,
                stale_reasons=list(match.match.stale_reasons), my_relevance_verdict=mine.get(entry.incident_memory_entry_id), can_hide=entry.application_id in administered,
            ))
        return items

    # ── Saying whether a suggestion helped ─────────────────────────────────────
    async def set_relevance(self, current_user: CurrentUser, investigation_id: str, memory_entry_id: str, verdict: IncidentMemoryRelevanceVerdict) -> None:
        investigation, entry = await self._readable_pair(current_user, investigation_id, memory_entry_id)
        row = await self.session.scalar(
            select(IncidentMemoryRelevanceFeedback).where(
                IncidentMemoryRelevanceFeedback.investigation_id == investigation.investigation_id, IncidentMemoryRelevanceFeedback.incident_memory_entry_id == entry.incident_memory_entry_id,
                IncidentMemoryRelevanceFeedback.user_principal_name == current_user.user_principal_name,
            )
        )
        if row is None:
            self.session.add(IncidentMemoryRelevanceFeedback(
                investigation_id=investigation.investigation_id, incident_memory_entry_id=entry.incident_memory_entry_id, user_principal_name=current_user.user_principal_name,
                relevance_verdict=verdict, recorded_at=utc_now(),
            ))
        else:
            row.relevance_verdict, row.recorded_at = verdict, utc_now()
        await self.session.flush()

    async def clear_relevance(self, current_user: CurrentUser, investigation_id: str, memory_entry_id: str) -> None:
        investigation, entry = await self._readable_pair(current_user, investigation_id, memory_entry_id)
        await self.session.execute(delete(IncidentMemoryRelevanceFeedback).where(
            IncidentMemoryRelevanceFeedback.investigation_id == investigation.investigation_id, IncidentMemoryRelevanceFeedback.incident_memory_entry_id == entry.incident_memory_entry_id,
            IncidentMemoryRelevanceFeedback.user_principal_name == current_user.user_principal_name,
        ))

    async def _readable_pair(self, current_user: CurrentUser, investigation_id: str, memory_entry_id: str) -> tuple[Investigation, IncidentMemoryEntry]:
        investigation = await self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise NotFoundException("The investigation was not found.")
        await self.authorization.ensure_application_reader(current_user, investigation.application_id)
        return investigation, await self._readable_entry(current_user, memory_entry_id)

    async def _readable_entry(self, current_user: CurrentUser, memory_entry_id: str) -> IncidentMemoryEntry:
        entry = await self.session.get(IncidentMemoryEntry, memory_entry_id)
        if entry is None or not await self.authorization.can_read_application(current_user, entry.application_id):
            raise NotFoundException(NOT_FOUND_TEXT)  # never "forbidden": that would say the entry exists (decision M8)
        return entry

    # ── Hiding ─────────────────────────────────────────────────────────────────
    async def hide(self, current_user: CurrentUser, memory_entry_id: str, reason: str) -> None:
        """An admin of the entry's application stops it being suggested, to anyone. The reason is masked and kept with the entry."""
        entry = await self._readable_entry(current_user, memory_entry_id)
        await self.authorization.ensure_application_admin(current_user, entry.application_id)
        entry.entry_status, entry.hidden_by_user_principal_name, entry.hidden_at = IncidentMemoryEntryStatus.HIDDEN, current_user.user_principal_name, utc_now()
        entry.hide_reason_text = PiiMasker().mask_text(reason.strip())[:500]
        await self.session.flush()
        await AuditService(self.session).record(
            current_user, "incident_memory.hide", target_entity_type="incident_memory_entry", target_entity_id=entry.incident_memory_entry_id, application_id=entry.application_id,
            action_details={"reasonLength": len(reason.strip())},
        )

    async def unhide(self, current_user: CurrentUser, memory_entry_id: str) -> None:
        entry = await self._readable_entry(current_user, memory_entry_id)
        await self.authorization.ensure_application_admin(current_user, entry.application_id)
        entry.entry_status = IncidentMemoryEntryStatus.ACTIVE
        entry.hidden_by_user_principal_name, entry.hidden_at, entry.hide_reason_text = None, None, None
        await self.session.flush()
        if entry.incident_id:
            await IncidentMemoryBuilder(self.session).settle_incident(entry.incident_id)  # it may have been replaced by a newer investigation of the incident while hidden
        await AuditService(self.session).record(
            current_user, "incident_memory.unhide", target_entity_type="incident_memory_entry", target_entity_id=entry.incident_memory_entry_id, application_id=entry.application_id, action_details={},
        )

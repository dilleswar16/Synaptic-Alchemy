"""Runbooks: known issues and the team's documented response, searchable by symptoms."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.knowledge_dtos import RunbookCreateRequest, RunbookResponse, RunbookUpdateRequest
from keigan.entities.application_entities import MonitoredService
from keigan.entities.knowledge_entities import KnowledgeDocument, Runbook
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.utils.text_utils import term_frequencies


class RunbookService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.runbook_repository = BaseRepository(session, Runbook)
        self.audit_service = AuditService(session)

    async def list_runbooks(self, application_id: str) -> list[RunbookResponse]:
        runbooks = await self.runbook_repository.find_all(Runbook.application_id == application_id, order_by=Runbook.runbook_title)
        service_names = await self._service_names(application_id)
        return [self._to_response(runbook, service_names) for runbook in runbooks]

    async def get_runbook(self, application_id: str, runbook_id: str) -> RunbookResponse:
        return self._to_response(await self._get_runbook(application_id, runbook_id), await self._service_names(application_id))

    async def create_runbook(self, current_user: CurrentUser, application_id: str, request: RunbookCreateRequest) -> RunbookResponse:
        await self._validate_references(application_id, request.applies_to_service_ids, request.knowledge_document_id)
        runbook = Runbook(
            application_id=application_id,
            runbook_title=request.runbook_title.strip(),
            trigger_symptoms_text=request.trigger_symptoms_text,
            runbook_steps_markdown=request.runbook_steps_markdown,
            source_url=request.source_url,
            applies_to_service_ids_json=request.applies_to_service_ids,
            knowledge_document_id=request.knowledge_document_id,
            created_by_user_principal_name=current_user.user_principal_name,
            updated_by_user_principal_name=current_user.user_principal_name,
        )
        self._refresh_search_terms(runbook)
        await self.runbook_repository.add(runbook)
        await self.audit_service.record(
            current_user, "runbook.create", target_entity_type="runbook", target_entity_id=runbook.runbook_id, application_id=application_id,
            action_details={"runbookTitle": runbook.runbook_title},
        )
        return self._to_response(runbook, await self._service_names(application_id))

    async def update_runbook(self, current_user: CurrentUser, application_id: str, runbook_id: str, request: RunbookUpdateRequest) -> RunbookResponse:
        runbook = await self._get_runbook(application_id, runbook_id)
        changes = request.model_dump(exclude_unset=True)
        await self._validate_references(application_id, changes.get("applies_to_service_ids") or [], changes.get("knowledge_document_id"))
        for field_name, field_value in changes.items():
            if field_name == "applies_to_service_ids":
                runbook.applies_to_service_ids_json = field_value or []
            elif field_value is not None or field_name in ("trigger_symptoms_text", "runbook_steps_markdown", "source_url", "knowledge_document_id"):
                setattr(runbook, field_name, field_value)
        self._refresh_search_terms(runbook)
        runbook.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "runbook.update", target_entity_type="runbook", target_entity_id=runbook_id, application_id=application_id,
            action_details={"changedFields": sorted(changes.keys())},
        )
        return self._to_response(runbook, await self._service_names(application_id))

    async def delete_runbook(self, current_user: CurrentUser, application_id: str, runbook_id: str) -> None:
        runbook = await self._get_runbook(application_id, runbook_id)
        await self.audit_service.record(
            current_user, "runbook.delete", target_entity_type="runbook", target_entity_id=runbook_id, application_id=application_id,
            action_details={"runbookTitle": runbook.runbook_title},
        )
        await self.runbook_repository.delete(runbook)

    # ── Helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _refresh_search_terms(runbook: Runbook) -> None:
        """Titles and symptoms carry the most weight in matching, so they are repeated before the steps."""
        runbook.search_terms_json = term_frequencies(f"{runbook.runbook_title} {runbook.runbook_title} {runbook.trigger_symptoms_text or ''} {runbook.trigger_symptoms_text or ''} {runbook.runbook_steps_markdown or ''}")

    async def _validate_references(self, application_id: str, service_ids: list[str], knowledge_document_id: str | None) -> None:
        if service_ids:
            known_ids = set((await self.session.scalars(select(MonitoredService.service_id).where(MonitoredService.application_id == application_id, MonitoredService.service_id.in_(service_ids)))).all())
            unknown_ids = set(service_ids) - known_ids
            if unknown_ids:
                raise BusinessValidationException("A selected service is not part of this application.", field_errors=[{"field": "appliesToServiceIds", "message": "Unknown service."}])
        if knowledge_document_id:
            document = await self.session.get(KnowledgeDocument, knowledge_document_id)
            if document is None or document.application_id != application_id:
                raise BusinessValidationException("The linked document is not part of this application.", field_errors=[{"field": "knowledgeDocumentId", "message": "Unknown document."}])

    async def _get_runbook(self, application_id: str, runbook_id: str) -> Runbook:
        runbook = await self.runbook_repository.get_required(runbook_id, "runbook")
        if runbook.application_id != application_id:
            raise NotFoundException("The runbook was not found.")
        return runbook

    async def _service_names(self, application_id: str) -> dict[str, str]:
        return dict((await self.session.execute(select(MonitoredService.service_id, MonitoredService.service_name).where(MonitoredService.application_id == application_id))).all())

    @staticmethod
    def _to_response(runbook: Runbook, service_names: dict[str, str]) -> RunbookResponse:
        service_ids = runbook.applies_to_service_ids_json or []
        return RunbookResponse(
            runbook_id=runbook.runbook_id,
            application_id=runbook.application_id,
            runbook_title=runbook.runbook_title,
            trigger_symptoms_text=runbook.trigger_symptoms_text,
            runbook_steps_markdown=runbook.runbook_steps_markdown,
            source_url=runbook.source_url,
            applies_to_service_ids=service_ids,
            applies_to_service_names=[service_names[service_id] for service_id in service_ids if service_id in service_names],
            knowledge_document_id=runbook.knowledge_document_id,
            times_referenced_count=runbook.times_referenced_count or 0,
            last_referenced_at=runbook.last_referenced_at,
            updated_at=runbook.updated_at,
            created_by_user_principal_name=runbook.created_by_user_principal_name,
        )

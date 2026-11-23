"""Similar past incident endpoints (spec 34, 4.7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from keigan.config.database_config import provide
from keigan.dtos.incident_memory_dtos import HideMemoryRequest, RelevanceRequest, SimilarIncidentsResponse
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.incident_memory_service import IncidentMemoryService

router = APIRouter(prefix="/api", tags=["Similar incidents"])


@router.get("/investigations/{investigation_id}/similar-incidents", response_model=SimilarIncidentsResponse, response_model_by_alias=True)
async def get_similar_incidents(
    investigation_id: str, current_user: CurrentUser = Depends(get_current_user), memory_service: IncidentMemoryService = Depends(provide(IncidentMemoryService)),
) -> SimilarIncidentsResponse:
    return await memory_service.similar_incidents(current_user, investigation_id)


@router.put("/investigations/{investigation_id}/similar-incidents/{memory_entry_id}/relevance", status_code=204, response_class=Response)
async def set_relevance(
    investigation_id: str, memory_entry_id: str, request: RelevanceRequest, current_user: CurrentUser = Depends(get_current_user),
    memory_service: IncidentMemoryService = Depends(provide(IncidentMemoryService)),
) -> Response:
    await memory_service.set_relevance(current_user, investigation_id, memory_entry_id, request.verdict)
    return Response(status_code=204)


@router.delete("/investigations/{investigation_id}/similar-incidents/{memory_entry_id}/relevance", status_code=204, response_class=Response)
async def clear_relevance(
    investigation_id: str, memory_entry_id: str, current_user: CurrentUser = Depends(get_current_user), memory_service: IncidentMemoryService = Depends(provide(IncidentMemoryService)),
) -> Response:
    await memory_service.clear_relevance(current_user, investigation_id, memory_entry_id)
    return Response(status_code=204)


@router.post("/incident-memory/{memory_entry_id}/hide", status_code=204, response_class=Response)
async def hide_memory_entry(
    memory_entry_id: str, request: HideMemoryRequest, current_user: CurrentUser = Depends(get_current_user), memory_service: IncidentMemoryService = Depends(provide(IncidentMemoryService)),
) -> Response:
    await memory_service.hide(current_user, memory_entry_id, request.reason)
    return Response(status_code=204)


@router.post("/incident-memory/{memory_entry_id}/unhide", status_code=204, response_class=Response)
async def unhide_memory_entry(
    memory_entry_id: str, current_user: CurrentUser = Depends(get_current_user), memory_service: IncidentMemoryService = Depends(provide(IncidentMemoryService)),
) -> Response:
    await memory_service.unhide(current_user, memory_entry_id)
    return Response(status_code=204)

"""Incident room, incident detail, resolution and postmortem endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import JobAcceptedResponse, PagedResult
from keigan.dtos.incident_dtos import IncidentDetailDto, IncidentSummaryDto, PostmortemDto, PostmortemUpdateRequest, ResolveIncidentRequest
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.communication_service import CommunicationService
from keigan.services.incident_service import IncidentService

router = APIRouter(prefix="/api", tags=["Incidents"])


def split_values(comma_separated_text: str | None) -> list[str] | None:
    values = [value.strip() for value in (comma_separated_text or "").split(",") if value.strip()]
    return values or None


@router.get("/incidents", response_model=PagedResult[IncidentSummaryDto], response_model_by_alias=True)
async def list_incidents(
    application_ids: str | None = Query(default=None, alias="applicationIds"),
    priorities: str | None = Query(default=None),
    statuses: str | None = Query(default=None),
    sources: str | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    search: str | None = Query(default=None, max_length=200),
    only_mine: bool = Query(default=False, alias="onlyMine"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    incident_service: IncidentService = Depends(provide(IncidentService)),
) -> PagedResult[IncidentSummaryDto]:
    return await incident_service.list_incidents(
        current_user, application_ids=split_values(application_ids), priorities=split_values(priorities), statuses=split_values(statuses), sources=split_values(sources),
        from_time=from_time, to_time=to_time, search=search, only_mine=only_mine, page=page, page_size=page_size,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetailDto, response_model_by_alias=True)
async def get_incident(incident_id: str, current_user: CurrentUser = Depends(get_current_user), incident_service: IncidentService = Depends(provide(IncidentService))) -> IncidentDetailDto:
    return await incident_service.get_incident(current_user, incident_id)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentDetailDto, response_model_by_alias=True)
async def resolve_incident(
    incident_id: str, request: ResolveIncidentRequest, current_user: CurrentUser = Depends(get_current_user), incident_service: IncidentService = Depends(provide(IncidentService))
) -> IncidentDetailDto:
    return await incident_service.resolve_incident(current_user, incident_id, request)


@router.get("/incidents/{incident_id}/postmortem", response_model=PostmortemDto | None, response_model_by_alias=True)
async def get_postmortem(incident_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> PostmortemDto | None:
    return await communication_service.get_postmortem(current_user, incident_id)


@router.post("/incidents/{incident_id}/postmortem/generate", response_model=JobAcceptedResponse, response_model_by_alias=True, status_code=202)
async def generate_postmortem(
    incident_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))
) -> JobAcceptedResponse:
    return await communication_service.start_postmortem(current_user, incident_id, "user_button")


@router.patch("/postmortems/{postmortem_id}", response_model=PostmortemDto, response_model_by_alias=True)
async def update_postmortem(
    postmortem_id: str, request: PostmortemUpdateRequest, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))
) -> PostmortemDto:
    return await communication_service.update_postmortem(current_user, postmortem_id, request)


@router.post("/postmortems/{postmortem_id}/finalize", response_model=PostmortemDto, response_model_by_alias=True)
async def finalize_postmortem(postmortem_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> PostmortemDto:
    return await communication_service.finalize_postmortem(current_user, postmortem_id)


@router.post("/postmortems/{postmortem_id}/send")
async def send_postmortem(postmortem_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> Any:
    return await communication_service.send_postmortem(current_user, postmortem_id)

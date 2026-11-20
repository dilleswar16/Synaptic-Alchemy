"""Investigation, timeline, evidence and communication endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.controllers.incident_controller import split_values
from keigan.dtos.common_dtos import JobAcceptedResponse, PagedResult
from keigan.dtos.incident_dtos import CommunicationDto, CommunicationSendResult, CommunicationUpdateRequest, GenerateCommunicationsRequest
from keigan.dtos.investigation_dtos import (
    EvidenceDto, InvestigationDetailDto, InvestigationFeedbackRequest, InvestigationProgressDto, InvestigationSummaryDto, StartInvestigationRequest, TimelineEventDto,
)
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.communication_service import CommunicationService
from keigan.services.investigation_service import InvestigationService

router = APIRouter(prefix="/api", tags=["Investigations"])


@router.post("/investigations", response_model=JobAcceptedResponse, response_model_by_alias=True, status_code=202)
async def start_investigation(
    request: StartInvestigationRequest, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))
) -> JobAcceptedResponse:
    return await investigation_service.start_manual_investigation(current_user, request)


@router.get("/investigations", response_model=PagedResult[InvestigationSummaryDto], response_model_by_alias=True)
async def list_investigations(
    application_ids: str | None = Query(default=None, alias="applicationIds"),
    statuses: str | None = Query(default=None),
    incident_id: str | None = Query(default=None, alias="incidentId"),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    current_user: CurrentUser = Depends(get_current_user),
    investigation_service: InvestigationService = Depends(provide(InvestigationService)),
) -> PagedResult[InvestigationSummaryDto]:
    return await investigation_service.list_investigations(
        current_user, application_ids=split_values(application_ids), statuses=split_values(statuses), incident_id=incident_id, from_time=from_time, to_time=to_time, page=page, page_size=page_size
    )


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetailDto, response_model_by_alias=True)
async def get_investigation(investigation_id: str, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))) -> InvestigationDetailDto:
    return await investigation_service.get_investigation_detail(current_user, investigation_id)


@router.get("/investigations/{investigation_id}/progress", response_model=InvestigationProgressDto, response_model_by_alias=True)
async def get_progress(investigation_id: str, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))) -> InvestigationProgressDto:
    return await investigation_service.get_progress(current_user, investigation_id)


@router.post("/investigations/{investigation_id}/rerun", response_model=JobAcceptedResponse, response_model_by_alias=True, status_code=202)
async def rerun_investigation(investigation_id: str, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))) -> JobAcceptedResponse:
    return await investigation_service.rerun(current_user, investigation_id)


@router.post("/investigations/{investigation_id}/feedback", response_model=InvestigationSummaryDto, response_model_by_alias=True)
async def submit_feedback(
    investigation_id: str, request: InvestigationFeedbackRequest, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))
) -> InvestigationSummaryDto:
    return await investigation_service.submit_feedback(current_user, investigation_id, request)


@router.get("/investigations/{investigation_id}/timeline", response_model=list[TimelineEventDto], response_model_by_alias=True)
async def get_timeline(investigation_id: str, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))) -> list[TimelineEventDto]:
    return await investigation_service.get_timeline(current_user, investigation_id)


@router.get("/investigations/{investigation_id}/evidence/{evidence_code}", response_model=EvidenceDto, response_model_by_alias=True)
async def get_evidence(
    investigation_id: str, evidence_code: str, current_user: CurrentUser = Depends(get_current_user), investigation_service: InvestigationService = Depends(provide(InvestigationService))
) -> EvidenceDto:
    return await investigation_service.get_evidence_detail(current_user, investigation_id, evidence_code)


@router.get("/investigations/{investigation_id}/communications", response_model=list[CommunicationDto], response_model_by_alias=True)
async def list_communications(investigation_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> list[CommunicationDto]:
    return await communication_service.list_communications(current_user, investigation_id)


@router.post("/investigations/{investigation_id}/communications/generate", response_model=JobAcceptedResponse, response_model_by_alias=True, status_code=202)
async def generate_communications(
    investigation_id: str, request: GenerateCommunicationsRequest, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))
) -> JobAcceptedResponse:
    return await communication_service.start_generation_job(current_user, investigation_id, request)


@router.patch("/communications/{communication_id}", response_model=CommunicationDto, response_model_by_alias=True)
async def update_communication(
    communication_id: str, request: CommunicationUpdateRequest, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))
) -> CommunicationDto:
    return await communication_service.update_communication(current_user, communication_id, request)


@router.post("/communications/{communication_id}/approve", response_model=CommunicationDto, response_model_by_alias=True)
async def approve_communication(communication_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> CommunicationDto:
    return await communication_service.approve_communication(current_user, communication_id)


@router.post("/communications/{communication_id}/send", response_model=CommunicationSendResult, response_model_by_alias=True)
async def send_communication(communication_id: str, current_user: CurrentUser = Depends(get_current_user), communication_service: CommunicationService = Depends(provide(CommunicationService))) -> CommunicationSendResult:
    return await communication_service.send_communication(current_user, communication_id)

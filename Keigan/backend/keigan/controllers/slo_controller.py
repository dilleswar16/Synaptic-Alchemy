"""SLO endpoints: proposals, SLIs, SLOs, dashboard, series and ecosystem heatmap."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.slo_dtos import (
    AcceptProposalsRequest, AcceptProposalsResponse, EcosystemHeatmapResponse, SliCreateRequest, SliResponse, SliUpdateRequest, SloCreateRequest, SloProposalsResponse, SloResponse, SloSeriesResponse,
    SloSummaryResponse, SloUpdateRequest,
)
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader
from keigan.services.sli_proposal_service import SliProposalService
from keigan.services.slo_service import SloService

router = APIRouter(prefix="/api", tags=["SLOs"])


@router.post("/applications/{application_id}/slo-proposals/measure", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def measure_slo_proposals(application_id: str, _: CurrentUser = Depends(require_application_admin), service: SliProposalService = Depends(provide(SliProposalService))) -> JobAcceptedResponse:
    return JobAcceptedResponse(job_id=await service.request_measurement(application_id))


@router.get("/applications/{application_id}/slo-proposals", response_model=SloProposalsResponse)
async def get_slo_proposals(application_id: str, _: CurrentUser = Depends(require_application_reader), service: SliProposalService = Depends(provide(SliProposalService))) -> SloProposalsResponse:
    return await service.get_proposals(application_id)


@router.post("/applications/{application_id}/slo-proposals/accept", response_model=AcceptProposalsResponse)
async def accept_slo_proposals(application_id: str, request: AcceptProposalsRequest, current_user: CurrentUser = Depends(require_application_admin), service: SliProposalService = Depends(provide(SliProposalService))) -> AcceptProposalsResponse:
    response, _ = await service.accept(current_user, application_id, request)
    return response


@router.get("/applications/{application_id}/slis", response_model=list[SliResponse])
async def list_slis(application_id: str, _: CurrentUser = Depends(require_application_reader), service: SloService = Depends(provide(SloService))) -> list[SliResponse]:
    return await service.list_slis(application_id)


@router.post("/applications/{application_id}/slis", response_model=SliResponse, status_code=status.HTTP_201_CREATED)
async def create_sli(application_id: str, request: SliCreateRequest, current_user: CurrentUser = Depends(require_application_admin), service: SloService = Depends(provide(SloService))) -> SliResponse:
    return await service.create_sli(current_user, application_id, request)


@router.patch("/slis/{sli_id}", response_model=SliResponse)
async def update_sli(sli_id: str, request: SliUpdateRequest, current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> SliResponse:
    return await service.update_sli(current_user, sli_id, request)


@router.delete("/slis/{sli_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sli(sli_id: str, current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> Response:
    await service.delete_sli(current_user, sli_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/slos", response_model=list[SloResponse])
async def list_slos(application_id: str, _: CurrentUser = Depends(require_application_reader), service: SloService = Depends(provide(SloService))) -> list[SloResponse]:
    return await service.list_slos(application_id)


@router.post("/applications/{application_id}/slos", response_model=SloResponse, status_code=status.HTTP_201_CREATED)
async def create_slo(application_id: str, request: SloCreateRequest, current_user: CurrentUser = Depends(require_application_admin), service: SloService = Depends(provide(SloService))) -> SloResponse:
    return await service.create_slo(current_user, application_id, request)


@router.patch("/slos/{slo_id}", response_model=SloResponse)
async def update_slo(slo_id: str, request: SloUpdateRequest, current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> SloResponse:
    return await service.update_slo(current_user, slo_id, request)


@router.delete("/slos/{slo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slo(slo_id: str, current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> Response:
    await service.delete_slo(current_user, slo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/slo-dashboard", response_model=list[SloSummaryResponse])
async def get_slo_dashboard(application_ids: str | None = Query(None, alias="applicationIds"), current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> list[SloSummaryResponse]:
    return await service.get_dashboard(current_user, [value for value in application_ids.split(",") if value] if application_ids else None)


@router.get("/slos/{slo_id}/series", response_model=SloSeriesResponse)
async def get_slo_series(
    slo_id: str, period_start: datetime | None = Query(None, alias="from"), period_end: datetime | None = Query(None, alias="to"), resolution: int = 60,
    current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService)),
) -> SloSeriesResponse:
    """``resolution`` is the bucket size in minutes (5, 60, 1440)."""
    return await service.get_series(current_user, slo_id, period_start, period_end, resolution)


@router.get("/slo-ecosystem-heatmap", response_model=EcosystemHeatmapResponse)
async def get_ecosystem_heatmap(days: int = 30, current_user: CurrentUser = Depends(get_current_user), service: SloService = Depends(provide(SloService))) -> EcosystemHeatmapResponse:
    return await service.get_ecosystem_heatmap(current_user, days)

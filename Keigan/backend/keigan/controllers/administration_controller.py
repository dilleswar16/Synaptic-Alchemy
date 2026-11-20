"""Administration endpoints (Keigan administrators only)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from keigan.config.database_config import provide
from keigan.dtos.administration_dtos import (
    AdministrationSettingsResponse, AuditEventResponse, ConnectionTestOutcome, JobResponse, JobStatsResponse, SimulationScenarioResponse, TriggerScenarioRequest, UsageResponse,
)
from keigan.dtos.common_dtos import PagedResult
from keigan.security.current_user import CurrentUser, require_keigan_admin
from keigan.services.administration_service import AdministrationService

router = APIRouter(prefix="/api/administration", tags=["Administration"])


@router.get("/settings", response_model=AdministrationSettingsResponse)
async def get_settings(_: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService))) -> AdministrationSettingsResponse:
    return await service.get_settings()


@router.post("/connection-tests/{integration}", response_model=ConnectionTestOutcome)
async def test_connection(integration: str, current_user: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService))) -> ConnectionTestOutcome:
    return await service.test_connection(current_user, integration)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    period_start: datetime | None = Query(default=None, alias="from"), period_end: datetime | None = Query(default=None, alias="to"), group_by: str = Query(default="day", alias="groupBy"),
    _: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService)),
) -> UsageResponse:
    return await service.get_usage(period_start, period_end, group_by)


@router.get("/audit-events", response_model=PagedResult[AuditEventResponse])
async def list_audit_events(
    actor: str | None = None, action: str | None = None, application_id: str | None = Query(default=None, alias="applicationId"), period_start: datetime | None = Query(default=None, alias="from"),
    period_end: datetime | None = Query(default=None, alias="to"), page: int = 1, page_size: int = Query(default=50, alias="pageSize"),
    _: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService)),
) -> PagedResult[AuditEventResponse]:
    return await service.list_audit_events(actor=actor, action=action, application_id=application_id, period_start=period_start, period_end=period_end, page=page, page_size=page_size)


@router.get("/jobs", response_model=JobStatsResponse)
async def get_jobs(_: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService))) -> JobStatsResponse:
    return await service.get_job_stats()


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(job_id: str, current_user: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService))) -> JobResponse:
    return await service.retry_job(current_user, job_id)


@router.get("/simulation/scenarios", response_model=list[SimulationScenarioResponse])
async def list_simulation_scenarios(_: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService))) -> list[SimulationScenarioResponse]:
    return service.list_simulation_scenarios()


@router.post("/simulation/scenarios/{scenario_key}")
async def trigger_simulation_scenario(
    scenario_key: str, request: TriggerScenarioRequest, current_user: CurrentUser = Depends(require_keigan_admin), service: AdministrationService = Depends(provide(AdministrationService)),
) -> dict[str, Any]:
    return await service.trigger_simulation_scenario(current_user, scenario_key, request.application_id)

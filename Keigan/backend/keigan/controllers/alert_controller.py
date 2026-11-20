"""Alerts: noise policy, maintenance windows, mute rules, funnel, alert groups, feedback and the weekly noise report."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response, status

from keigan.config.database_config import provide
from keigan.dtos.alert_dtos import (
    AlertGroupDetailResponse, AlertGroupFeedbackRequest, AlertGroupSummaryResponse, CreateIncidentResponse, FunnelResponse, MaintenanceWindowRequest, MaintenanceWindowResponse,
    MaintenanceWindowUpdateRequest, MuteRuleRequest, MuteRuleResponse, MuteRuleUpdateRequest, NoisePolicyResponse, NoisePolicyUpdateRequest, NoisePreviewRequest, NoiseReportResponse,
)
from keigan.dtos.common_dtos import PagedResult
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader
from keigan.services.alert_service import AlertService

router = APIRouter(prefix="/api", tags=["Alerts"])


def _split(values: str | None) -> list[str] | None:
    return [value for value in values.split(",") if value] if values else None


@router.get("/applications/{application_id}/noise-policy", response_model=NoisePolicyResponse)
async def get_noise_policy(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertService = Depends(provide(AlertService))) -> NoisePolicyResponse:
    return await service.get_policy(application_id)


@router.put("/applications/{application_id}/noise-policy", response_model=NoisePolicyResponse)
async def update_noise_policy(application_id: str, request: NoisePolicyUpdateRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> NoisePolicyResponse:
    return await service.update_policy(current_user, application_id, request)


@router.post("/applications/{application_id}/noise-policy/preview", response_model=FunnelResponse)
async def preview_noise_policy(application_id: str, request: NoisePreviewRequest, _: CurrentUser = Depends(require_application_reader), service: AlertService = Depends(provide(AlertService))) -> FunnelResponse:
    return await service.preview_policy(application_id, request.policy_settings, request.days)


@router.get("/applications/{application_id}/maintenance-windows", response_model=list[MaintenanceWindowResponse])
async def list_maintenance_windows(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertService = Depends(provide(AlertService))) -> list[MaintenanceWindowResponse]:
    return await service.list_maintenance_windows(application_id)


@router.post("/applications/{application_id}/maintenance-windows", response_model=MaintenanceWindowResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance_window(application_id: str, request: MaintenanceWindowRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> MaintenanceWindowResponse:
    return await service.create_maintenance_window(current_user, application_id, request)


@router.patch("/applications/{application_id}/maintenance-windows/{window_id}", response_model=MaintenanceWindowResponse)
async def update_maintenance_window(application_id: str, window_id: str, request: MaintenanceWindowUpdateRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> MaintenanceWindowResponse:
    return await service.update_maintenance_window(current_user, application_id, window_id, request)


@router.delete("/applications/{application_id}/maintenance-windows/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_window(application_id: str, window_id: str, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> Response:
    await service.delete_maintenance_window(current_user, application_id, window_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/mute-rules", response_model=list[MuteRuleResponse])
async def list_mute_rules(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertService = Depends(provide(AlertService))) -> list[MuteRuleResponse]:
    return await service.list_mute_rules(application_id)


@router.post("/applications/{application_id}/mute-rules", response_model=MuteRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_mute_rule(application_id: str, request: MuteRuleRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> MuteRuleResponse:
    return await service.create_mute_rule(current_user, application_id, request)


@router.patch("/applications/{application_id}/mute-rules/{mute_rule_id}", response_model=MuteRuleResponse)
async def update_mute_rule(application_id: str, mute_rule_id: str, request: MuteRuleUpdateRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> MuteRuleResponse:
    return await service.update_mute_rule(current_user, application_id, mute_rule_id, request)


@router.delete("/applications/{application_id}/mute-rules/{mute_rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mute_rule(application_id: str, mute_rule_id: str, current_user: CurrentUser = Depends(require_application_admin), service: AlertService = Depends(provide(AlertService))) -> Response:
    await service.delete_mute_rule(current_user, application_id, mute_rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/noise-report", response_model=NoiseReportResponse)
async def get_noise_report(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertService = Depends(provide(AlertService))) -> NoiseReportResponse:
    return await service.get_noise_report(application_id)


@router.get("/alerts/funnel", response_model=FunnelResponse)
async def get_alert_funnel(
    application_ids: str | None = Query(None, alias="applicationIds"), period_start: datetime | None = Query(None, alias="from"), period_end: datetime | None = Query(None, alias="to"),
    current_user: CurrentUser = Depends(get_current_user), service: AlertService = Depends(provide(AlertService)),
) -> FunnelResponse:
    return await service.funnel_for_user(current_user, _split(application_ids), period_start, period_end)


@router.get("/alert-groups", response_model=PagedResult[AlertGroupSummaryResponse])
async def list_alert_groups(
    application_ids: str | None = Query(None, alias="applicationIds"), statuses: str | None = None, period_start: datetime | None = Query(None, alias="from"), period_end: datetime | None = Query(None, alias="to"),
    minimum_score: float | None = Query(None, alias="minimumScore"), page: int = 1, page_size: int = Query(50, alias="pageSize"), current_user: CurrentUser = Depends(get_current_user), service: AlertService = Depends(provide(AlertService)),
) -> PagedResult[AlertGroupSummaryResponse]:
    return await service.list_groups(current_user, _split(application_ids), _split(statuses), period_start, period_end, minimum_score, page, page_size)


@router.get("/alert-groups/{alert_group_id}", response_model=AlertGroupDetailResponse)
async def get_alert_group(alert_group_id: str, current_user: CurrentUser = Depends(get_current_user), service: AlertService = Depends(provide(AlertService))) -> AlertGroupDetailResponse:
    return await service.get_group(current_user, alert_group_id)


@router.post("/alert-groups/{alert_group_id}/feedback", response_model=AlertGroupSummaryResponse)
async def give_alert_group_feedback(alert_group_id: str, request: AlertGroupFeedbackRequest, current_user: CurrentUser = Depends(get_current_user), service: AlertService = Depends(provide(AlertService))) -> AlertGroupSummaryResponse:
    return await service.record_feedback(current_user, alert_group_id, request)


@router.post("/alert-groups/{alert_group_id}/create-servicenow-incident", response_model=CreateIncidentResponse)
async def create_servicenow_incident(alert_group_id: str, current_user: CurrentUser = Depends(get_current_user), service: AlertService = Depends(provide(AlertService))) -> CreateIncidentResponse:
    incident_id = await service.create_servicenow_incident(current_user, alert_group_id)
    return CreateIncidentResponse(incident_id=incident_id, alert_group_id=alert_group_id)

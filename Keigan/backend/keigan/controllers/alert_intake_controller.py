"""Alert intake (public webhook) and alert source management."""

from fastapi import APIRouter, Depends, Request, Response, status

from keigan.config.database_config import provide
from keigan.dtos.alert_dtos import (
    AlertSourceCreatedResponse, AlertSourceCreateRequest, AlertSourceResponse, AlertSourceUpdateRequest, AzureAlertRulesResponse, MappingPreviewRequest, MappingPreviewResponse,
    RecentAlertEventResponse, SecretRotationResponse, SetupInstructionsResponse, TestAlertResponse,
)
from keigan.security.current_user import CurrentUser, require_application_admin, require_application_reader
from keigan.services.alert_source_service import AlertSourceService

router = APIRouter(prefix="/api", tags=["Alert intake"])


@router.post("/alerts/in/{alert_source_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_alert(alert_source_id: str, request: Request, token: str | None = None, alert_source_service: AlertSourceService = Depends(provide(AlertSourceService))) -> dict[str, str]:
    """PUBLIC webhook. Token in X-Keigan-Token or ?token=; optional X-Keigan-Signature (HMAC-SHA256 of the body). Stores the raw event and answers 202."""
    body_bytes = await request.body()
    event_id = await alert_source_service.receive(
        alert_source_id, body_bytes, request.headers.get("x-keigan-token") or token, request.headers.get("x-keigan-signature"), request.client.host if request.client else "unknown"
    )
    return {"alertEventId": event_id, "status": "accepted"}


@router.get("/applications/{application_id}/alert-sources", response_model=list[AlertSourceResponse])
async def list_alert_sources(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertSourceService = Depends(provide(AlertSourceService))) -> list[AlertSourceResponse]:
    return await service.list_sources(application_id)


@router.post("/applications/{application_id}/alert-sources", response_model=AlertSourceCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_source(application_id: str, request: AlertSourceCreateRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> AlertSourceCreatedResponse:
    return await service.create_source(current_user, application_id, request)


@router.post("/applications/{application_id}/alert-sources/mapping-preview", response_model=MappingPreviewResponse)
async def preview_alert_mapping(application_id: str, request: MappingPreviewRequest, _: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> MappingPreviewResponse:
    return await service.preview_mapping(application_id, request)


@router.patch("/applications/{application_id}/alert-sources/{alert_source_id}", response_model=AlertSourceResponse)
async def update_alert_source(application_id: str, alert_source_id: str, request: AlertSourceUpdateRequest, current_user: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> AlertSourceResponse:
    return await service.update_source(current_user, application_id, alert_source_id, request)


@router.delete("/applications/{application_id}/alert-sources/{alert_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_source(application_id: str, alert_source_id: str, current_user: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> Response:
    await service.delete_source(current_user, application_id, alert_source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/applications/{application_id}/alert-sources/{alert_source_id}/rotate-secret", response_model=SecretRotationResponse)
async def rotate_alert_source_secret(application_id: str, alert_source_id: str, current_user: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> SecretRotationResponse:
    return await service.rotate_secret(current_user, application_id, alert_source_id)


@router.post("/applications/{application_id}/alert-sources/{alert_source_id}/test", response_model=TestAlertResponse, status_code=status.HTTP_202_ACCEPTED)
async def send_test_alert(application_id: str, alert_source_id: str, current_user: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> TestAlertResponse:
    return await service.send_test_alert(current_user, application_id, alert_source_id)


@router.get("/applications/{application_id}/alert-sources/{alert_source_id}/recent-events", response_model=list[RecentAlertEventResponse])
async def list_recent_alert_events(application_id: str, alert_source_id: str, limit: int = 15, _: CurrentUser = Depends(require_application_reader), service: AlertSourceService = Depends(provide(AlertSourceService))) -> list[RecentAlertEventResponse]:
    return await service.recent_events(application_id, alert_source_id, limit)


@router.get("/applications/{application_id}/alert-sources/{alert_source_id}/setup-instructions", response_model=SetupInstructionsResponse)
async def get_setup_instructions(application_id: str, alert_source_id: str, _: CurrentUser = Depends(require_application_admin), service: AlertSourceService = Depends(provide(AlertSourceService))) -> SetupInstructionsResponse:
    return await service.get_setup_instructions(application_id, alert_source_id)


@router.get("/applications/{application_id}/azure-alert-rules", response_model=AzureAlertRulesResponse)
async def get_azure_alert_rules(application_id: str, _: CurrentUser = Depends(require_application_reader), service: AlertSourceService = Depends(provide(AlertSourceService))) -> AzureAlertRulesResponse:
    return await service.discover_azure_rules(application_id)

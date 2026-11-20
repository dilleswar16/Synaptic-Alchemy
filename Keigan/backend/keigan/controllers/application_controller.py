"""Applications endpoints: list, create / request, detail, readiness, go live, pause, resume, access and platform identity."""

from fastapi import APIRouter, Depends, Response, status

from keigan.config.database_config import provide
from keigan.dtos.application_dtos import (
    AccessResponse,
    AccessUpdateRequest,
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationSummaryResponse,
    ApplicationUpdateRequest,
    AccessVerificationResponse,
    PlatformIdentityResponse,
    ReadinessResponse,
)
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader
from keigan.services.application_service import ApplicationService

router = APIRouter(prefix="/api", tags=["Applications"])


@router.get("/applications", response_model=list[ApplicationSummaryResponse], response_model_by_alias=True)
async def list_applications(
    current_user: CurrentUser = Depends(get_current_user), application_service: ApplicationService = Depends(provide(ApplicationService))
) -> list[ApplicationSummaryResponse]:
    return await application_service.list_applications(current_user)


@router.post("/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    request: ApplicationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    """Keigan admins create a draft application; everyone else files an onboarding request (status ``requested``)."""
    return await application_service.create_application(current_user, request)


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_reader),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    return await application_service.get_application(current_user, application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    request: ApplicationUpdateRequest,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    return await application_service.update_application(current_user, application_id, request)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> Response:
    await application_service.delete_application(current_user, application_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/readiness", response_model=ReadinessResponse)
async def get_readiness(
    application_id: str,
    _current_user: CurrentUser = Depends(require_application_reader),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ReadinessResponse:
    return await application_service.get_readiness(application_id)


@router.post("/applications/{application_id}/go-live", response_model=ApplicationResponse)
async def go_live(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    return await application_service.go_live(current_user, application_id)


@router.post("/applications/{application_id}/pause", response_model=ApplicationResponse)
async def pause_application(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    return await application_service.pause_application(current_user, application_id)


@router.post("/applications/{application_id}/resume", response_model=ApplicationResponse)
async def resume_application(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> ApplicationResponse:
    return await application_service.resume_application(current_user, application_id)


@router.get("/applications/{application_id}/access", response_model=AccessResponse)
async def get_access(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_reader),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> AccessResponse:
    return await application_service.get_access(current_user, application_id)


@router.patch("/applications/{application_id}/access", response_model=AccessResponse)
async def update_access(
    application_id: str,
    request: AccessUpdateRequest,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> AccessResponse:
    return await application_service.update_access(current_user, application_id, request)


@router.post("/applications/{application_id}/access/verify", response_model=AccessVerificationResponse)
async def verify_access_groups(
    application_id: str,
    current_user: CurrentUser = Depends(require_application_admin),
    application_service: ApplicationService = Depends(provide(ApplicationService)),
) -> AccessVerificationResponse:
    return await application_service.verify_access_groups(current_user, application_id)


@router.get("/platform/identity", response_model=PlatformIdentityResponse)
async def get_platform_identity(
    _current_user: CurrentUser = Depends(get_current_user), application_service: ApplicationService = Depends(provide(ApplicationService))
) -> PlatformIdentityResponse:
    return await application_service.get_platform_identity()

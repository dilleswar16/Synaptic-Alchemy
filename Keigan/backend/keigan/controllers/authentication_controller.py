"""Sign-in (local mode), the current user's profile and roles, and preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from keigan.config.database_config import provide
from keigan.dtos.authentication_dtos import (
    ApplicationRoleResponse,
    CurrentUserResponse,
    LocalSignInRequest,
    LocalSignInResponse,
    LocalUserResponse,
    UpdatePreferencesRequest,
)
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.security.security_middleware import rate_limiter
from keigan.services.authentication_service import AuthenticationService
from keigan.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


async def build_current_user_response(
    current_user: CurrentUser, authorization_service: AuthorizationService, authentication_service: AuthenticationService
) -> CurrentUserResponse:
    application_roles = await authorization_service.application_roles(current_user)
    user_profile = await authentication_service.get_or_create_profile(current_user)
    return CurrentUserResponse(
        user_principal_name=current_user.user_principal_name,
        display_name=current_user.display_name,
        email=current_user.email_address,
        is_keigan_admin=current_user.is_keigan_admin,
        application_roles=[
            ApplicationRoleResponse(
                application_id=role.application_id,
                application_code=role.application_code,
                application_name=role.application_name,
                role=role.role,
                lifecycle_status=role.lifecycle_status,
            )
            for role in sorted(application_roles.values(), key=lambda role: role.application_name)
        ],
        preferred_locale=user_profile.preferred_locale or current_user.preferred_locale,
        preferred_theme=user_profile.preferred_theme,
    )


@router.get("/local-users", response_model=list[LocalUserResponse])
async def list_local_users() -> list[LocalUserResponse]:
    return [
        LocalUserResponse(
            user_principal_name=local_user.user_principal_name,
            display_name=local_user.display_name,
            email_address=local_user.email_address,
            role_description=local_user.role_description,
            group_names=list(local_user.group_names),
        )
        for local_user in AuthenticationService.list_local_users()
    ]


@router.post("/local-sign-in", response_model=LocalSignInResponse)
async def sign_in_local_user(
    sign_in_request: LocalSignInRequest,
    request: Request,
    authentication_service: AuthenticationService = Depends(provide(AuthenticationService)),
    authorization_service: AuthorizationService = Depends(provide(AuthorizationService)),
) -> LocalSignInResponse:
    rate_limiter.check(f"local-sign-in:{request.client.host if request.client else 'unknown'}", 30)
    access_token, expires_at, current_user = await authentication_service.sign_in_local_user(sign_in_request.user_principal_name)
    return LocalSignInResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=await build_current_user_response(current_user, authorization_service, authentication_service),
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    authentication_service: AuthenticationService = Depends(provide(AuthenticationService)),
    authorization_service: AuthorizationService = Depends(provide(AuthorizationService)),
) -> CurrentUserResponse:
    await authentication_service.record_sign_in(current_user)
    return await build_current_user_response(current_user, authorization_service, authentication_service)


@router.patch("/me/preferences", response_model=CurrentUserResponse)
async def update_my_preferences(
    preferences_request: UpdatePreferencesRequest,
    current_user: CurrentUser = Depends(get_current_user),
    authentication_service: AuthenticationService = Depends(provide(AuthenticationService)),
    authorization_service: AuthorizationService = Depends(provide(AuthorizationService)),
) -> CurrentUserResponse:
    await authentication_service.update_preferences(current_user, preferences_request.preferred_locale, preferences_request.preferred_theme)
    return await build_current_user_response(current_user, authorization_service, authentication_service)

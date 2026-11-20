"""Authentication and public configuration DTOs."""

from __future__ import annotations

from datetime import datetime

from keigan.dtos.common_dtos import ApiModel


class EntraClientConfiguration(ApiModel):
    tenant_id: str
    spa_client_id: str
    api_scope: str
    authority: str


class ClientConfigurationResponse(ApiModel):
    auth_mode: str
    entra: EntraClientConfiguration | None
    environment_name: str
    supported_locales: list[str]
    default_locale: str
    feature_flags: dict[str, bool]
    product_version: str


class LocalUserResponse(ApiModel):
    user_principal_name: str
    display_name: str
    email_address: str
    role_description: str
    group_names: list[str]


class LocalSignInRequest(ApiModel):
    user_principal_name: str


class ApplicationRoleResponse(ApiModel):
    application_id: str
    application_code: str
    application_name: str
    role: str
    lifecycle_status: str


class CurrentUserResponse(ApiModel):
    user_principal_name: str
    display_name: str
    email: str | None
    is_keigan_admin: bool
    application_roles: list[ApplicationRoleResponse]
    preferred_locale: str | None
    preferred_theme: str | None


class LocalSignInResponse(ApiModel):
    access_token: str
    expires_at: datetime
    user: CurrentUserResponse


class UpdatePreferencesRequest(ApiModel):
    preferred_locale: str | None = None
    preferred_theme: str | None = None


class HealthResponse(ApiModel):
    status: str
    database_reachable: bool | None = None
    worker_heartbeat_age_seconds: float | None = None

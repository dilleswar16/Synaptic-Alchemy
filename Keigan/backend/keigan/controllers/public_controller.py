"""Unauthenticated endpoints: client configuration for the SPA and health probes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ai_safety_settings import get_ai_safety_settings
from keigan.config.database_config import DatabaseSession
from keigan.config.settings import AuthenticationMode, EmailMode, get_settings
from keigan.dtos.authentication_dtos import ClientConfigurationResponse, EntraClientConfiguration, HealthResponse
from keigan.entities.platform_entities import PlatformSetting
from keigan.workers.job_queue import WORKER_HEARTBEAT_SETTING_KEY

router = APIRouter(prefix="/api/public", tags=["Public"])

SUPPORTED_LOCALES = ["en", "ja", "zh-CN", "es", "es-MX", "nl", "fr"]


@router.get("/client-configuration", response_model=ClientConfigurationResponse)
async def get_client_configuration() -> ClientConfigurationResponse:
    settings = get_settings()
    entra_configuration = None
    if settings.auth_mode == AuthenticationMode.ENTRA:
        entra_configuration = EntraClientConfiguration(
            tenant_id=settings.entra_tenant_id,
            spa_client_id=settings.entra_spa_client_id,
            api_scope=settings.entra_api_scope or f"api://{settings.entra_api_client_id}/{settings.entra_delegated_scope_name}",
            authority=f"https://login.microsoftonline.com/{settings.entra_tenant_id}",
        )
    return ClientConfigurationResponse(
        auth_mode=str(settings.auth_mode),
        entra=entra_configuration,
        environment_name=str(settings.environment),
        supported_locales=SUPPORTED_LOCALES,
        default_locale="en",
        feature_flags={
            "simulationControls": settings.is_local_environment,
            "teamsSimulated": str(settings.teams_mode) == "simulated",
            "emailSimulated": settings.email_mode == EmailMode.SIMULATED,
            "llmMock": str(settings.llm_provider) == "mock",
        },
        product_version=settings.product_version,
        allowed_link_hosts=sorted(get_ai_safety_settings().allowed_link_hosts),
    )


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readiness", response_model=HealthResponse)
async def get_readiness(session: AsyncSession = DatabaseSession) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    heartbeat_setting = await session.get(PlatformSetting, WORKER_HEARTBEAT_SETTING_KEY)
    heartbeat_age_seconds = None
    if heartbeat_setting and heartbeat_setting.setting_value_json:
        heartbeat_at = datetime.fromisoformat(heartbeat_setting.setting_value_json["heartbeatAt"])
        heartbeat_age_seconds = round((datetime.now(UTC) - heartbeat_at).total_seconds(), 1)
    return HealthResponse(status="ready", database_reachable=True, worker_heartbeat_age_seconds=heartbeat_age_seconds)

"""keigan/services/service_catalog_service.py: a service may only point at the application's own Azure resources (V2), probes follow the outbound URL policy (V16), no secret-name pointers (V22)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.dtos.onboarding_dtos import LogSourceInput, ServiceCreateRequest, ServiceUpdateRequest
from keigan.entities.application_entities import MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.service_catalog_service import ServiceCatalogService
from support.telemetry_scope import (
    FOREIGN_WORKSPACE_CUSTOMER_ID,
    FOREIGN_WORKSPACE_RESOURCE_ID,
    OWN_AKS_RESOURCE_ID,
    OWN_APPLICATION_INSIGHTS_RESOURCE_ID,
    OWN_RESOURCE_GROUP,
    OWN_SUBSCRIPTION_ID,
    OWN_WORKSPACE_CUSTOMER_ID,
    OWN_WORKSPACE_RESOURCE_ID,
    SHARED_WORKSPACE_CUSTOMER_ID,
    SHARED_WORKSPACE_RESOURCE_ID,
    ScopedApplication,
    create_log_tool_connection,
    create_scoped_application,
)

pytestmark = pytest.mark.usefixtures("seed_context")

APPLICATION_ADMIN = CurrentUser(
    user_principal_name="requester@example.com", display_name="Requester", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False
)


async def add_service(application: ScopedApplication, **overrides: object) -> str:
    async with open_session() as session:
        request = ServiceCreateRequest(service_name="polaris-api", service_type="aks", component_id=application.component_id, **overrides)
        return (await ServiceCatalogService(session).add_service(APPLICATION_ADMIN, application.application_id, request)).service_id


async def field_errors_of(application: ScopedApplication, service_id: str, source: LogSourceInput) -> list[dict[str, str]]:
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await ServiceCatalogService(session).replace_log_sources(APPLICATION_ADMIN, application.application_id, service_id, [source])
    return rejection.value.extra["fieldErrors"]


# ── V2: log sources ────────────────────────────────────────────────────────────
async def test_log_source_pointing_at_another_teams_workspace_is_rejected_with_field_errors() -> None:
    application = await create_scoped_application(lifecycle_status="requested")
    service_id = await add_service(application)
    errors = await field_errors_of(application, service_id, LogSourceInput(
        source_kind="log_analytics", log_analytics_workspace_resource_id=FOREIGN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=FOREIGN_WORKSPACE_CUSTOMER_ID,
    ))
    assert [error["field"] for error in errors] == ["logAnalyticsWorkspaceResourceId", "logAnalyticsWorkspaceCustomerId"]


async def test_own_workspace_with_another_teams_workspace_id_is_rejected() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    errors = await field_errors_of(application, service_id, LogSourceInput(
        source_kind="log_analytics", log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=FOREIGN_WORKSPACE_CUSTOMER_ID,
    ))
    assert [error["field"] for error in errors] == ["logAnalyticsWorkspaceCustomerId"]


async def test_log_source_pointing_at_the_applications_own_workspaces_is_saved() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    async with open_session() as session:
        saved_sources = await ServiceCatalogService(session).replace_log_sources(
            APPLICATION_ADMIN, application.application_id, service_id, [
                LogSourceInput(source_kind="log_analytics", log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=OWN_WORKSPACE_CUSTOMER_ID, is_primary_source=True),
                LogSourceInput(source_kind="application_insights", log_analytics_workspace_resource_id=OWN_APPLICATION_INSIGHTS_RESOURCE_ID),
                LogSourceInput(source_kind="log_analytics", log_analytics_workspace_resource_id=SHARED_WORKSPACE_RESOURCE_ID, log_analytics_workspace_customer_id=SHARED_WORKSPACE_CUSTOMER_ID),
            ],
        )
    assert len(saved_sources) == 3


async def test_log_source_cannot_be_saved_before_the_azure_resource_group_is_verified() -> None:
    application = await create_scoped_application(component_verification_status="not_checked")
    service_id = await add_service(application)
    errors = await field_errors_of(application, service_id, LogSourceInput(source_kind="log_analytics", log_analytics_workspace_resource_id=OWN_WORKSPACE_RESOURCE_ID))
    assert [error["field"] for error in errors] == ["logAnalyticsWorkspaceResourceId"]


async def test_log_tool_source_with_another_applications_connection_is_rejected() -> None:
    application = await create_scoped_application()
    other_application = await create_scoped_application()
    service_id = await add_service(application)
    foreign_connection_id = await create_log_tool_connection(other_application.application_id)
    errors = await field_errors_of(application, service_id, LogSourceInput(source_kind="log_tool", log_tool_connection_id=foreign_connection_id))
    assert errors == [{"field": "logToolConnectionId", "message": "Choose a log tool connection of this application."}]


# ── V2: service resources ──────────────────────────────────────────────────────
async def test_service_pointing_at_a_resource_group_of_another_team_is_rejected() -> None:
    application = await create_scoped_application()
    foreign_resource_id = OWN_AKS_RESOURCE_ID.replace(OWN_RESOURCE_GROUP, "rg-other-team")
    async with open_session() as session:
        with pytest.raises(BusinessValidationException) as rejection:
            await ServiceCatalogService(session).add_service(
                APPLICATION_ADMIN, application.application_id,
                ServiceCreateRequest(service_name="stolen", service_type="aks", component_id=application.component_id, external_resource_identifier=foreign_resource_id),
            )
    assert [error["field"] for error in rejection.value.extra["fieldErrors"]] == ["externalResourceIdentifier"]


async def test_service_pointing_at_a_resource_in_the_verified_resource_group_is_saved() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application, external_resource_identifier=OWN_AKS_RESOURCE_ID)
    async with open_session() as session:
        assert (await session.get(MonitoredService, service_id)).external_resource_identifier == OWN_AKS_RESOURCE_ID


async def test_application_insights_resource_of_another_team_cannot_be_set_on_a_service() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    foreign_application_insights = OWN_APPLICATION_INSIGHTS_RESOURCE_ID.replace(OWN_SUBSCRIPTION_ID, "cccccccc-0000-0000-0000-000000000003")
    async with open_session() as session:
        service_catalog = ServiceCatalogService(session)
        with pytest.raises(BusinessValidationException) as rejection:
            await service_catalog.update_service(
                APPLICATION_ADMIN, application.application_id, service_id, ServiceUpdateRequest(application_insights_resource_id=foreign_application_insights)
            )
        assert [error["field"] for error in rejection.value.extra["fieldErrors"]] == ["applicationInsightsResourceId"]
        await service_catalog.update_service(
            APPLICATION_ADMIN, application.application_id, service_id, ServiceUpdateRequest(application_insights_resource_id=OWN_APPLICATION_INSIGHTS_RESOURCE_ID)
        )


# ── V16: probe URLs ────────────────────────────────────────────────────────────
async def test_synthetic_probe_to_a_private_address_is_rejected() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    errors = await field_errors_of(application, service_id, LogSourceInput(source_kind="synthetic_probe", query_scope={"probe_url": "https://169.254.169.254/latest/meta-data"}))
    assert errors == [{"field": "queryScope.probe_url", "message": "This address points at a private or internal network, which Keigan does not call."}]


async def test_synthetic_probe_to_a_public_https_address_is_saved() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    async with open_session() as session:
        await ServiceCatalogService(session).replace_log_sources(
            APPLICATION_ADMIN, application.application_id, service_id, [LogSourceInput(source_kind="synthetic_probe", query_scope={"probe_url": "https://status.vendor.example/health"})]
        )
        assert len((await session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id == service_id))).all()) == 1


# ── V22: no secret-name pointers ───────────────────────────────────────────────
async def test_repository_credential_secret_name_cannot_be_set_through_the_request() -> None:
    application = await create_scoped_application()
    service_id = await add_service(application)
    async with open_session() as session:
        await ServiceCatalogService(session).update_service(
            APPLICATION_ADMIN, application.application_id, service_id,
            ServiceUpdateRequest.model_validate({"repositoryCredentialSecretName": "servicenow-credential", "repositoryProvider": "azure_devops"}),
        )
        service = await session.get(MonitoredService, service_id)
        assert (service.repository_provider, service.repository_credential_secret_name) == ("azure_devops", None)

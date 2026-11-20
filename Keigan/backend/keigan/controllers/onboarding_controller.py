"""Onboarding endpoints: components, discovery, services, log sources, dependencies, log tools, integrations, record links, ServiceNow groups."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.onboarding_dtos import (
    ComponentCreateRequest,
    ComponentResponse,
    ComponentUpdateRequest,
    ConnectionTestResponse,
    DiagnosticSettingCommandResponse,
    DiscoveredResourceResponse,
    IntegrationResponse,
    IntegrationUpdateRequest,
    LogSourceInput,
    LogSourceResponse,
    LogSourceTestResponse,
    LogToolConnectionCreateRequest,
    LogToolConnectionResponse,
    LogToolConnectionUpdateRequest,
    RecordLinkCreateRequest,
    RecordLinkResponse,
    RoleCommandsResponse,
    ServiceBulkUpdateRequest,
    ServiceCreateRequest,
    ServiceDependenciesUpdateRequest,
    ServiceDependencyResponse,
    ServiceNowGroupResponse,
    ServiceNowGroupSearchResult,
    ServiceNowGroupsUpdateRequest,
    ServiceResponse,
    ServiceUpdateRequest,
)
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.security.current_user import CurrentUser, get_current_user, require_application_admin, require_application_reader
from keigan.services.authorization_service import AuthorizationService
from keigan.services.integration_settings_service import IntegrationSettingsService
from keigan.services.onboarding_service import OnboardingService
from keigan.services.service_catalog_service import ServiceCatalogService

router = APIRouter(prefix="/api", tags=["Onboarding"])
APPLICATION_PATH = "/applications/{application_id}"

OnboardingDependency = Depends(provide(OnboardingService))
CatalogDependency = Depends(provide(ServiceCatalogService))
SettingsDependency = Depends(provide(IntegrationSettingsService))
ReaderDependency = Depends(require_application_reader)
AdminDependency = Depends(require_application_admin)


# ── Components ─────────────────────────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/components", response_model=list[ComponentResponse])
async def list_components(application_id: str, _user: CurrentUser = ReaderDependency, onboarding_service: OnboardingService = OnboardingDependency) -> list[ComponentResponse]:
    return await onboarding_service.list_components(application_id)


@router.post(f"{APPLICATION_PATH}/components", response_model=ComponentResponse, status_code=status.HTTP_201_CREATED)
async def add_component(
    application_id: str, request: ComponentCreateRequest, current_user: CurrentUser = AdminDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> ComponentResponse:
    return await onboarding_service.add_component(current_user, application_id, request)


@router.get(f"{APPLICATION_PATH}/components/{{component_id}}", response_model=ComponentResponse)
async def get_component(
    application_id: str, component_id: str, _user: CurrentUser = ReaderDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> ComponentResponse:
    return await onboarding_service.get_component(application_id, component_id)


@router.patch(f"{APPLICATION_PATH}/components/{{component_id}}", response_model=ComponentResponse)
async def update_component(
    application_id: str, component_id: str, request: ComponentUpdateRequest, current_user: CurrentUser = AdminDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> ComponentResponse:
    return await onboarding_service.update_component(current_user, application_id, component_id, request)


@router.delete(f"{APPLICATION_PATH}/components/{{component_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component(
    application_id: str, component_id: str, current_user: CurrentUser = AdminDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> Response:
    await onboarding_service.delete_component(current_user, application_id, component_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(f"{APPLICATION_PATH}/components/{{component_id}}/verify", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def verify_component(
    application_id: str, component_id: str, current_user: CurrentUser = AdminDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> JobAcceptedResponse:
    return await onboarding_service.start_verification(current_user, application_id, component_id)


@router.post(f"{APPLICATION_PATH}/components/{{component_id}}/discover", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def discover_component(
    application_id: str, component_id: str, current_user: CurrentUser = AdminDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> JobAcceptedResponse:
    return await onboarding_service.start_discovery(current_user, application_id, component_id)


@router.get(f"{APPLICATION_PATH}/components/{{component_id}}/role-commands", response_model=RoleCommandsResponse)
async def get_role_commands(
    application_id: str, component_id: str, _user: CurrentUser = ReaderDependency, onboarding_service: OnboardingService = OnboardingDependency
) -> RoleCommandsResponse:
    return await onboarding_service.get_role_commands(application_id, component_id)


@router.get(f"{APPLICATION_PATH}/components/{{component_id}}/resources", response_model=list[DiscoveredResourceResponse])
async def list_discovered_resources(
    application_id: str,
    component_id: str,
    classification: str | None = Query(default=None),
    _user: CurrentUser = ReaderDependency,
    onboarding_service: OnboardingService = OnboardingDependency,
) -> list[DiscoveredResourceResponse]:
    return await onboarding_service.list_resources(application_id, component_id, classification)


# ── Services ───────────────────────────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/services", response_model=list[ServiceResponse])
async def list_services(application_id: str, _user: CurrentUser = ReaderDependency, catalog_service: ServiceCatalogService = CatalogDependency) -> list[ServiceResponse]:
    return await catalog_service.list_services(application_id)


@router.post(f"{APPLICATION_PATH}/services", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def add_service(
    application_id: str, request: ServiceCreateRequest, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> ServiceResponse:
    return await catalog_service.add_service(current_user, application_id, request)


@router.patch(f"{APPLICATION_PATH}/services/bulk", response_model=list[ServiceResponse])
async def bulk_update_services(
    application_id: str, request: ServiceBulkUpdateRequest, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> list[ServiceResponse]:
    return await catalog_service.bulk_update_services(current_user, application_id, request)


@router.patch(f"{APPLICATION_PATH}/services/{{service_id}}", response_model=ServiceResponse)
async def update_service(
    application_id: str, service_id: str, request: ServiceUpdateRequest, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> ServiceResponse:
    return await catalog_service.update_service(current_user, application_id, service_id, request)


@router.delete(f"{APPLICATION_PATH}/services/{{service_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    application_id: str, service_id: str, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> Response:
    await catalog_service.delete_service(current_user, application_id, service_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(f"{APPLICATION_PATH}/services/{{service_id}}/log-sources", response_model=list[LogSourceResponse])
async def list_log_sources(
    application_id: str, service_id: str, _user: CurrentUser = ReaderDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> list[LogSourceResponse]:
    return await catalog_service.list_log_sources(application_id, service_id)


@router.put(f"{APPLICATION_PATH}/services/{{service_id}}/log-sources", response_model=list[LogSourceResponse])
async def replace_log_sources(
    application_id: str, service_id: str, request: list[LogSourceInput], current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> list[LogSourceResponse]:
    return await catalog_service.replace_log_sources(current_user, application_id, service_id, request)


@router.post(f"{APPLICATION_PATH}/services/{{service_id}}/log-sources/{{log_source_id}}/test", response_model=LogSourceTestResponse)
async def test_log_source(
    application_id: str, service_id: str, log_source_id: str, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> LogSourceTestResponse:
    return await catalog_service.test_log_source(current_user, application_id, service_id, log_source_id)


@router.get(f"{APPLICATION_PATH}/services/{{service_id}}/diagnostic-setting-command", response_model=DiagnosticSettingCommandResponse)
async def get_diagnostic_setting_command(
    application_id: str, service_id: str, _user: CurrentUser = ReaderDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> DiagnosticSettingCommandResponse:
    return await catalog_service.get_diagnostic_setting_command(application_id, service_id)


@router.get(f"{APPLICATION_PATH}/service-dependencies", response_model=list[ServiceDependencyResponse])
async def list_service_dependencies(
    application_id: str, _user: CurrentUser = ReaderDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> list[ServiceDependencyResponse]:
    return await catalog_service.list_dependencies(application_id)


@router.put(f"{APPLICATION_PATH}/service-dependencies", response_model=list[ServiceDependencyResponse])
async def replace_service_dependencies(
    application_id: str, request: ServiceDependenciesUpdateRequest, current_user: CurrentUser = AdminDependency, catalog_service: ServiceCatalogService = CatalogDependency
) -> list[ServiceDependencyResponse]:
    return await catalog_service.replace_dependencies(current_user, application_id, request)


# ── Log tool connections ───────────────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/log-tool-connections", response_model=list[LogToolConnectionResponse])
async def list_log_tool_connections(
    application_id: str, _user: CurrentUser = ReaderDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> list[LogToolConnectionResponse]:
    return await settings_service.list_log_tool_connections(application_id)


@router.post(f"{APPLICATION_PATH}/log-tool-connections", response_model=LogToolConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_log_tool_connection(
    application_id: str, request: LogToolConnectionCreateRequest, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> LogToolConnectionResponse:
    return await settings_service.create_log_tool_connection(current_user, application_id, request)


@router.patch(f"{APPLICATION_PATH}/log-tool-connections/{{connection_id}}", response_model=LogToolConnectionResponse)
async def update_log_tool_connection(
    application_id: str, connection_id: str, request: LogToolConnectionUpdateRequest, current_user: CurrentUser = AdminDependency,
    settings_service: IntegrationSettingsService = SettingsDependency,
) -> LogToolConnectionResponse:
    return await settings_service.update_log_tool_connection(current_user, application_id, connection_id, request)


@router.delete(f"{APPLICATION_PATH}/log-tool-connections/{{connection_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log_tool_connection(
    application_id: str, connection_id: str, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> Response:
    await settings_service.delete_log_tool_connection(current_user, application_id, connection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(f"{APPLICATION_PATH}/log-tool-connections/{{connection_id}}/test", response_model=ConnectionTestResponse)
async def test_log_tool_connection(
    application_id: str, connection_id: str, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> ConnectionTestResponse:
    return await settings_service.test_log_tool_connection(current_user, application_id, connection_id)


# ── Integrations and record links ──────────────────────────────────────────────
@router.get("/integrations/field-schemas")
async def get_integration_field_schemas(_user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return IntegrationSettingsService.get_field_schemas()


@router.get(f"{APPLICATION_PATH}/integrations", response_model=list[IntegrationResponse])
async def list_integrations(application_id: str, _user: CurrentUser = ReaderDependency, settings_service: IntegrationSettingsService = SettingsDependency) -> list[IntegrationResponse]:
    return await settings_service.list_integrations(application_id)


@router.get(f"{APPLICATION_PATH}/integrations/{{integration_kind}}", response_model=IntegrationResponse)
async def get_integration(
    application_id: str, integration_kind: str, _user: CurrentUser = ReaderDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> IntegrationResponse:
    return await settings_service.get_integration(application_id, integration_kind)


@router.put(f"{APPLICATION_PATH}/integrations/{{integration_kind}}", response_model=IntegrationResponse)
async def save_integration(
    application_id: str, integration_kind: str, request: IntegrationUpdateRequest, current_user: CurrentUser = AdminDependency,
    settings_service: IntegrationSettingsService = SettingsDependency,
) -> IntegrationResponse:
    return await settings_service.save_integration(current_user, application_id, integration_kind, request)


@router.get(f"{APPLICATION_PATH}/record-links", response_model=list[RecordLinkResponse])
async def list_record_links(application_id: str, _user: CurrentUser = ReaderDependency, settings_service: IntegrationSettingsService = SettingsDependency) -> list[RecordLinkResponse]:
    return await settings_service.list_record_links(application_id)


@router.post(f"{APPLICATION_PATH}/record-links", response_model=RecordLinkResponse, status_code=status.HTTP_201_CREATED)
async def add_record_link(
    application_id: str, request: RecordLinkCreateRequest, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> RecordLinkResponse:
    return await settings_service.add_record_link(current_user, application_id, request)


@router.delete(f"{APPLICATION_PATH}/record-links/{{record_link_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record_link(
    application_id: str, record_link_id: str, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> Response:
    await settings_service.delete_record_link(current_user, application_id, record_link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── ServiceNow assignment groups ───────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/servicenow-groups", response_model=list[ServiceNowGroupResponse])
async def list_servicenow_groups(
    application_id: str, _user: CurrentUser = ReaderDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> list[ServiceNowGroupResponse]:
    return await settings_service.list_servicenow_groups(application_id)


@router.put(f"{APPLICATION_PATH}/servicenow-groups", response_model=list[ServiceNowGroupResponse])
async def replace_servicenow_groups(
    application_id: str, request: ServiceNowGroupsUpdateRequest, current_user: CurrentUser = AdminDependency, settings_service: IntegrationSettingsService = SettingsDependency
) -> list[ServiceNowGroupResponse]:
    return await settings_service.replace_servicenow_groups(current_user, application_id, request.group_names)


@router.get("/servicenow/groups/search", response_model=list[ServiceNowGroupSearchResult])
async def search_servicenow_groups(
    query: str = Query(default="", max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
    settings_service: IntegrationSettingsService = SettingsDependency,
) -> list[ServiceNowGroupSearchResult]:
    if not current_user.is_keigan_admin and not await AuthorizationService(settings_service.session).editable_application_ids(current_user):
        raise ForbiddenException("Only application admins can search ServiceNow groups.")
    return await settings_service.search_servicenow_groups(query)

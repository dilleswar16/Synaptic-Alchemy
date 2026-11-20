"""Services of an application: table rows, manual services, bulk changes, log sources and their read test, dependencies."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.dtos.onboarding_dtos import (
    DiagnosticSettingCommandResponse,
    LogSourceInput,
    LogSourceResponse,
    LogSourceTestResponse,
    ServiceBulkUpdateRequest,
    ServiceCreateRequest,
    ServiceDependenciesUpdateRequest,
    ServiceDependencyResponse,
    ServiceResponse,
    ServiceUpdateRequest,
)
from keigan.entities.application_entities import (
    ApplicationComponent,
    DiscoveredResource,
    LogToolConnection,
    MonitoredService,
    ServiceDependency,
    ServiceLogSource,
)
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.integrations.telemetry_gateway import TelemetryTarget
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.component_discovery_service import load_resource_catalog
from keigan.utils.time_utils import utc_now

NON_AZURE_SERVICE_TYPES = {"network_appliance", "mainframe_subsystem", "batch_job_stream", "saas_service"}


class ServiceCatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.service_repository = BaseRepository(session, MonitoredService)
        self.audit_service = AuditService(session)

    # ── Services ───────────────────────────────────────────────────────────────
    async def list_services(self, application_id: str) -> list[ServiceResponse]:
        services = await self.service_repository.find_all(MonitoredService.application_id == application_id, order_by=MonitoredService.service_name)
        return await self._to_responses(application_id, services)

    async def add_service(self, current_user: CurrentUser, application_id: str, request: ServiceCreateRequest) -> ServiceResponse:
        valid_service_types = {rule["service_type"] for rule in load_resource_catalog().get("monitored_types", [])} | NON_AZURE_SERVICE_TYPES
        if request.service_type not in valid_service_types:
            raise BusinessValidationException("The service type is not known.", field_errors=[{"field": "serviceType", "message": f"Use one of {', '.join(sorted(valid_service_types))}."}])
        if request.component_id:
            component = await self.session.get(ApplicationComponent, request.component_id)
            if component is None or component.application_id != application_id:
                raise NotFoundException("The component was not found.")
        service = MonitoredService(
            application_id=application_id,
            component_id=request.component_id,
            service_name=request.service_name.strip(),
            service_type=request.service_type,
            external_resource_identifier=request.external_resource_identifier,
            environment_name=request.environment_name,
            criticality_tier=request.criticality_tier,
            aks_namespace_filter=request.aks_namespace_filter,
            service_description=request.service_description,
            created_by_user_principal_name=current_user.user_principal_name,
            updated_by_user_principal_name=current_user.user_principal_name,
        )
        await self.service_repository.add(service)
        await self.audit_service.record(
            current_user, "service.add", target_entity_type="monitored_service", target_entity_id=service.service_id, application_id=application_id,
            action_details={"serviceName": service.service_name, "serviceType": service.service_type},
        )
        return (await self._to_responses(application_id, [service]))[0]

    async def update_service(self, current_user: CurrentUser, application_id: str, service_id: str, request: ServiceUpdateRequest) -> ServiceResponse:
        service = await self._get_service(application_id, service_id)
        changes = request.model_dump(exclude_unset=True)
        credential_secret_name = changes.pop("repository_credential_secret_name", None)
        for field_name, field_value in changes.items():
            setattr(service, field_name, field_value)
        if credential_secret_name is not None:
            service.repository_credential_secret_name = credential_secret_name or None
        service.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "service.update", target_entity_type="monitored_service", target_entity_id=service_id, application_id=application_id,
            action_details={"changedFields": sorted(request.model_dump(exclude_unset=True).keys())},
        )
        return (await self._to_responses(application_id, [service]))[0]

    async def delete_service(self, current_user: CurrentUser, application_id: str, service_id: str) -> None:
        service = await self._get_service(application_id, service_id)
        await self.session.execute(delete(ServiceDependency).where((ServiceDependency.upstream_service_id == service_id) | (ServiceDependency.downstream_service_id == service_id)))
        await self.session.execute(delete(ServiceLogSource).where(ServiceLogSource.service_id == service_id))
        await self.audit_service.record(
            current_user, "service.delete", target_entity_type="monitored_service", target_entity_id=service_id, application_id=application_id,
            action_details={"serviceName": service.service_name},
        )
        await self.service_repository.delete(service)

    async def bulk_update_services(self, current_user: CurrentUser, application_id: str, request: ServiceBulkUpdateRequest) -> list[ServiceResponse]:
        services = await self.service_repository.find_all(MonitoredService.application_id == application_id, MonitoredService.service_id.in_(request.service_ids))
        if len(services) != len(set(request.service_ids)):
            raise NotFoundException("One or more services were not found in this application.")
        changes = request.changes
        for service in services:
            if changes.environment_name is not None:
                service.environment_name = changes.environment_name
            if changes.criticality_tier is not None:
                service.criticality_tier = changes.criticality_tier
            if changes.is_monitoring_enabled is not None:
                service.is_monitoring_enabled = changes.is_monitoring_enabled
            if changes.add_log_source is not None:
                await self._add_log_source_if_missing(application_id, service, changes.add_log_source)
            service.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "service.bulk_update", application_id=application_id,
            action_details={"serviceCount": len(services), "changes": request.changes.model_dump(exclude_unset=True, by_alias=True)},
        )
        return await self._to_responses(application_id, services)

    # ── Log sources ────────────────────────────────────────────────────────────
    async def list_log_sources(self, application_id: str, service_id: str) -> list[LogSourceResponse]:
        await self._get_service(application_id, service_id)
        return await self._log_source_responses([service_id])

    async def replace_log_sources(self, current_user: CurrentUser, application_id: str, service_id: str, desired_sources: list[LogSourceInput]) -> list[LogSourceResponse]:
        service = await self._get_service(application_id, service_id)
        if sum(1 for source in desired_sources if source.is_primary_source) > 1:
            raise BusinessValidationException("Only one log source can be the primary source.")
        existing_sources = list((await self.session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id == service_id))).all())
        existing_by_key = {self._source_key(source.source_kind, source.log_tool_connection_id, source.log_analytics_workspace_resource_id): source for source in existing_sources}
        kept_keys: set[tuple] = set()
        for desired_source in desired_sources:
            await self._validate_log_source(application_id, desired_source)
            key = self._source_key(desired_source.source_kind, desired_source.log_tool_connection_id, desired_source.log_analytics_workspace_resource_id)
            kept_keys.add(key)
            existing_source = existing_by_key.get(key)
            if existing_source is None:
                self.session.add(self._build_log_source(service_id, desired_source))
            else:
                existing_source.query_scope_json = desired_source.query_scope
                existing_source.is_primary_source = desired_source.is_primary_source
                existing_source.log_analytics_workspace_customer_id = desired_source.log_analytics_workspace_customer_id or existing_source.log_analytics_workspace_customer_id
        for key, existing_source in existing_by_key.items():
            if key not in kept_keys:
                await self.session.delete(existing_source)
        await self.session.flush()
        await self.audit_service.record(
            current_user, "service.log_sources_update", target_entity_type="monitored_service", target_entity_id=service.service_id, application_id=application_id,
            action_details={"sourceKinds": [source.source_kind for source in desired_sources]},
        )
        return await self._log_source_responses([service_id])

    async def test_log_source(self, current_user: CurrentUser, application_id: str, service_id: str, log_source_id: str) -> LogSourceTestResponse:
        service = await self._get_service(application_id, service_id)
        log_source = await self.session.get(ServiceLogSource, log_source_id)
        if log_source is None or log_source.service_id != service_id:
            raise NotFoundException("The log source was not found.")
        component = await self.session.get(ApplicationComponent, service.component_id) if service.component_id else None
        connection = await self.session.get(LogToolConnection, log_source.log_tool_connection_id) if log_source.log_tool_connection_id else None
        target = TelemetryTarget.from_entities(service, log_source, component, connection)
        test_result = await application_context.telemetry_gateway().test_log_source(target)
        log_source.last_read_test_status = "passed" if test_result.succeeded else "failed"
        log_source.last_read_test_at = utc_now()
        await self.audit_service.record(
            current_user, "service.log_source_test", target_entity_type="service_log_source", target_entity_id=log_source_id, application_id=application_id,
            action_details={"succeeded": test_result.succeeded},
        )
        return LogSourceTestResponse(service_log_source_id=log_source_id, succeeded=test_result.succeeded, message=test_result.message, newest_log_timestamp=test_result.newest_log_timestamp)

    async def get_diagnostic_setting_command(self, application_id: str, service_id: str) -> DiagnosticSettingCommandResponse:
        service = await self._get_service(application_id, service_id)
        discovered_resource = await self.session.get(DiscoveredResource, service.discovered_resource_id) if service.discovered_resource_id else None
        workspace_resource_id = await self.session.scalar(
            select(ServiceLogSource.log_analytics_workspace_resource_id)
            .join(MonitoredService, MonitoredService.service_id == ServiceLogSource.service_id)
            .where(MonitoredService.application_id == application_id, ServiceLogSource.log_analytics_workspace_resource_id.is_not(None), ServiceLogSource.source_kind == "log_analytics")
            .limit(1)
        ) or "<log-analytics-workspace-resource-id>"
        resource_id = service.external_resource_identifier or "<resource-id>"
        cli_command = (
            f'az monitor diagnostic-settings create --name keigan-logs --resource "{resource_id}" --workspace "{workspace_resource_id}" '
            "--logs '[{\"categoryGroup\":\"allLogs\",\"enabled\":true}]' --metrics '[{\"category\":\"AllMetrics\",\"enabled\":true}]'"
        )
        powershell_command = (
            f'$logs = New-AzDiagnosticSettingLogSettingsObject -CategoryGroup allLogs -Enabled $true\n'
            f'New-AzDiagnosticSetting -Name keigan-logs -ResourceId "{resource_id}" -WorkspaceId "{workspace_resource_id}" -Log $logs'
        )
        return DiagnosticSettingCommandResponse(
            has_diagnostic_setting=bool(discovered_resource and discovered_resource.has_diagnostic_setting),
            cli_command=cli_command,
            powershell_command=powershell_command,
            explanation="A diagnostic setting sends this resource's logs to a Log Analytics workspace so Keigan can read them. Metrics work without it.",
        )

    # ── Dependencies ───────────────────────────────────────────────────────────
    async def list_dependencies(self, application_id: str) -> list[ServiceDependencyResponse]:
        dependencies = await BaseRepository(self.session, ServiceDependency).find_all(ServiceDependency.application_id == application_id)
        return [ServiceDependencyResponse.model_validate(dependency) for dependency in dependencies]

    async def replace_dependencies(self, current_user: CurrentUser, application_id: str, request: ServiceDependenciesUpdateRequest) -> list[ServiceDependencyResponse]:
        application_service_ids = set((await self.session.scalars(select(MonitoredService.service_id).where(MonitoredService.application_id == application_id))).all())
        desired_pairs: dict[tuple[str, str], str] = {}
        for dependency in request.dependencies:
            if dependency.upstream_service_id == dependency.downstream_service_id:
                raise BusinessValidationException("A service cannot depend on itself.")
            if dependency.upstream_service_id not in application_service_ids or dependency.downstream_service_id not in application_service_ids:
                raise NotFoundException("A dependency refers to a service that is not in this application.")
            desired_pairs[(dependency.upstream_service_id, dependency.downstream_service_id)] = dependency.dependency_kind
        existing = list((await self.session.scalars(select(ServiceDependency).where(ServiceDependency.application_id == application_id))).all())
        existing_by_pair = {(dependency.upstream_service_id, dependency.downstream_service_id): dependency for dependency in existing}
        for pair, dependency in existing_by_pair.items():
            if pair not in desired_pairs and dependency.dependency_source == "user_declared":
                await self.session.delete(dependency)
        for pair, dependency_kind in desired_pairs.items():
            if pair in existing_by_pair:
                existing_by_pair[pair].dependency_kind = dependency_kind
            else:
                self.session.add(ServiceDependency(application_id=application_id, upstream_service_id=pair[0], downstream_service_id=pair[1], dependency_kind=dependency_kind))
        await self.session.flush()
        await self.audit_service.record(current_user, "service.dependencies_update", application_id=application_id, action_details={"dependencyCount": len(desired_pairs)})
        return await self.list_dependencies(application_id)

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _get_service(self, application_id: str, service_id: str) -> MonitoredService:
        service = await self.service_repository.get_required(service_id, "service")
        if service.application_id != application_id:
            raise NotFoundException("The service was not found.")
        return service

    @staticmethod
    def _source_key(source_kind: str, log_tool_connection_id: str | None, workspace_resource_id: str | None) -> tuple:
        return (source_kind, log_tool_connection_id, (workspace_resource_id or "").lower())

    @staticmethod
    def _build_log_source(service_id: str, source: LogSourceInput) -> ServiceLogSource:
        return ServiceLogSource(
            service_id=service_id,
            source_kind=source.source_kind,
            log_tool_connection_id=source.log_tool_connection_id,
            log_analytics_workspace_resource_id=source.log_analytics_workspace_resource_id,
            log_analytics_workspace_customer_id=source.log_analytics_workspace_customer_id,
            query_scope_json=source.query_scope,
            is_primary_source=source.is_primary_source,
            was_auto_detected=False,
        )

    async def _validate_log_source(self, application_id: str, source: LogSourceInput) -> None:
        if source.source_kind == "log_tool":
            connection = await self.session.get(LogToolConnection, source.log_tool_connection_id) if source.log_tool_connection_id else None
            if connection is None or connection.application_id != application_id:
                raise BusinessValidationException("Choose a log tool connection of this application.", field_errors=[{"field": "logToolConnectionId", "message": "Required for log tool sources."}])
        if source.source_kind == "log_analytics" and not source.log_analytics_workspace_resource_id:
            raise BusinessValidationException("Enter the workspace resource ID.", field_errors=[{"field": "logAnalyticsWorkspaceResourceId", "message": "Required."}])

    async def _add_log_source_if_missing(self, application_id: str, service: MonitoredService, source: LogSourceInput) -> None:
        await self._validate_log_source(application_id, source)
        key = self._source_key(source.source_kind, source.log_tool_connection_id, source.log_analytics_workspace_resource_id)
        existing_sources = await self.session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id == service.service_id))
        if not any(self._source_key(existing.source_kind, existing.log_tool_connection_id, existing.log_analytics_workspace_resource_id) == key for existing in existing_sources):
            self.session.add(self._build_log_source(service.service_id, source))

    async def _log_source_responses(self, service_ids: list[str]) -> list[LogSourceResponse]:
        rows = (
            await self.session.execute(
                select(ServiceLogSource, LogToolConnection.connection_name)
                .outerjoin(LogToolConnection, LogToolConnection.log_tool_connection_id == ServiceLogSource.log_tool_connection_id)
                .where(ServiceLogSource.service_id.in_(service_ids))
                .order_by(ServiceLogSource.is_primary_source.desc(), ServiceLogSource.created_at)
            )
        ).all()
        return [
            LogSourceResponse(
                service_log_source_id=source.service_log_source_id,
                service_id=source.service_id,
                source_kind=source.source_kind,
                log_tool_connection_id=source.log_tool_connection_id,
                log_tool_connection_name=connection_name,
                log_analytics_workspace_resource_id=source.log_analytics_workspace_resource_id,
                log_analytics_workspace_customer_id=source.log_analytics_workspace_customer_id,
                query_scope=source.query_scope_json,
                is_primary_source=source.is_primary_source,
                was_auto_detected=source.was_auto_detected,
                last_read_test_status=source.last_read_test_status,
                last_read_test_at=source.last_read_test_at,
            )
            for source, connection_name in rows
        ]

    async def _to_responses(self, application_id: str, services: list[MonitoredService]) -> list[ServiceResponse]:
        if not services:
            return []
        service_ids = [service.service_id for service in services]
        sources_by_service: dict[str, list[LogSourceResponse]] = defaultdict(list)
        for source_response in await self._log_source_responses(service_ids):
            sources_by_service[source_response.service_id].append(source_response)
        components = {
            component.component_id: component
            for component in await BaseRepository(self.session, ApplicationComponent).find_all(ApplicationComponent.application_id == application_id)
        }
        discovered_ids = [service.discovered_resource_id for service in services if service.discovered_resource_id]
        discovered_by_id = {
            resource.discovered_resource_id: resource
            for resource in (await self.session.scalars(select(DiscoveredResource).where(DiscoveredResource.discovered_resource_id.in_(discovered_ids)))).all()
        } if discovered_ids else {}
        dependencies_by_upstream: dict[str, list[str]] = defaultdict(list)
        for upstream_id, downstream_id in (
            await self.session.execute(select(ServiceDependency.upstream_service_id, ServiceDependency.downstream_service_id).where(ServiceDependency.upstream_service_id.in_(service_ids)))
        ).all():
            dependencies_by_upstream[upstream_id].append(downstream_id)
        responses: list[ServiceResponse] = []
        for service in services:
            component = components.get(service.component_id or "")
            discovered_resource = discovered_by_id.get(service.discovered_resource_id or "")
            metrics = service.available_metrics_json or []
            responses.append(
                ServiceResponse(
                    service_id=service.service_id,
                    application_id=service.application_id,
                    component_id=service.component_id,
                    component_name=component.component_name if component else None,
                    component_type=component.component_type if component else None,
                    discovered_resource_id=service.discovered_resource_id,
                    service_name=service.service_name,
                    service_type=service.service_type,
                    external_resource_identifier=service.external_resource_identifier,
                    environment_name=service.environment_name,
                    criticality_tier=service.criticality_tier,
                    is_monitoring_enabled=service.is_monitoring_enabled,
                    aks_namespace_filter=service.aks_namespace_filter,
                    application_insights_resource_id=service.application_insights_resource_id,
                    application_insights_role_name=service.application_insights_role_name,
                    available_metric_count=len(metrics),
                    available_metrics=metrics or None,
                    repository_provider=service.repository_provider,
                    repository_url=service.repository_url,
                    repository_default_branch=service.repository_default_branch,
                    repository_path=service.repository_path,
                    repository_credential_configured=bool(service.repository_credential_secret_name),
                    service_description=service.service_description,
                    log_sources=sources_by_service.get(service.service_id, []),
                    has_diagnostic_setting=discovered_resource.has_diagnostic_setting if discovered_resource else None,
                    no_longer_found_at=discovered_resource.no_longer_found_at if discovered_resource else None,
                    depends_on_service_ids=dependencies_by_upstream.get(service.service_id, []),
                    updated_at=service.updated_at,
                )
            )
        return responses


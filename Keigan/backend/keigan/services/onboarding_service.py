"""Onboarding: components (the four types), role commands, access verification, discovery and the resource explorer.

Services, log tools, integrations and ServiceNow groups live in ``ServiceCatalogService`` and ``IntegrationSettingsService``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import IntegrationMode, get_settings
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.onboarding_dtos import (
    ComponentCreateRequest,
    ComponentResponse,
    ComponentUpdateRequest,
    DiscoveredResourceResponse,
    RoleCommandsResponse,
)
from keigan.entities.application_entities import (
    ApplicationComponent,
    DiscoveredResource,
    MonitoredService,
    ServiceDependency,
    ServiceLogSource,
)
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ConflictException, IntegrationException, NotFoundException
from keigan.repositories.base_repository import BaseRepository
from keigan.security.current_user import CurrentUser
from keigan.services.audit_service import AuditService
from keigan.services.component_discovery_service import ComponentDiscoveryService, resource_type_display_name
from keigan.services.role_command_builder import RoleCommandBuilder
from keigan.utils.time_utils import utc_now
from keigan.workers.job_queue import JobQueue

GUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
SIMULATED_MISSING_ROLE_MARKER = "norole"  # a resource group whose name contains this fails the simulated Log Analytics check (demo of the "waiting" path)
PROBE_URL_KEY = "synthetic_probe_url"
HARDWARE_CATEGORIES = ("server", "network_switch", "router", "firewall", "load_balancer", "storage_array", "other")


class OnboardingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.component_repository = BaseRepository(session, ApplicationComponent)
        self.audit_service = AuditService(session)

    # ── Components ─────────────────────────────────────────────────────────────
    async def list_components(self, application_id: str) -> list[ComponentResponse]:
        components = await self.component_repository.find_all(ApplicationComponent.application_id == application_id, order_by=ApplicationComponent.created_at)
        service_counts = dict(
            (await self.session.execute(select(MonitoredService.component_id, func.count()).where(MonitoredService.application_id == application_id).group_by(MonitoredService.component_id))).all()
        )
        return [self._to_response(component, int(service_counts.get(component.component_id, 0))) for component in components]

    async def get_component(self, application_id: str, component_id: str) -> ComponentResponse:
        component = await self._get_component(application_id, component_id)
        service_count = int((await self.session.scalar(select(func.count()).select_from(MonitoredService).where(MonitoredService.component_id == component_id))) or 0)
        return self._to_response(component, service_count)

    async def add_component(self, current_user: CurrentUser, application_id: str, request: ComponentCreateRequest) -> ComponentResponse:
        component = ApplicationComponent(
            application_id=application_id,
            component_type=request.component_type,
            component_name=request.component_name.strip(),
            environment_name=request.environment_name,
            component_configuration_json=request.component_configuration or {},
            created_by_user_principal_name=current_user.user_principal_name,
            updated_by_user_principal_name=current_user.user_principal_name,
        )
        if request.component_type == "azure_resource_group":
            await self._prepare_azure_component(component, request)
        else:
            self._validate_non_azure_component(component, request)
            await self._ensure_probe_url_allowed(request.component_configuration)
            component.access_verification_status = "not_applicable"
            component.last_verified_at = utc_now()
        await self.component_repository.add(component)
        if request.component_type != "azure_resource_group":
            await self._create_services_for_non_azure_component(component)
        await self.audit_service.record(
            current_user, "component.add", target_entity_type="application_component", target_entity_id=component.component_id, application_id=application_id,
            action_details={"componentType": component.component_type, "componentName": component.component_name},
        )
        return self._to_response(component, 0)

    async def _prepare_azure_component(self, component: ApplicationComponent, request: ComponentCreateRequest) -> None:
        field_errors: list[dict[str, str]] = []
        subscription_id = (request.azure_subscription_id or "").strip()
        resource_group_name = (request.azure_resource_group_name or "").strip()
        keigan_tenant_id = (await application_context.azure_credential_provider().resolve_keigan_identity()).tenant_id or ""
        tenant_id = (request.azure_tenant_id or keigan_tenant_id).strip()
        if not GUID_PATTERN.match(subscription_id):
            field_errors.append({"field": "azureSubscriptionId", "message": "Enter the subscription ID as a GUID."})
        if not GUID_PATTERN.match(tenant_id):
            field_errors.append({"field": "azureTenantId", "message": "Enter the tenant ID as a GUID."})
        if not resource_group_name:
            field_errors.append({"field": "azureResourceGroupName", "message": "Enter the resource group name."})
        if field_errors:
            raise BusinessValidationException("The Azure scope is not valid.", field_errors=field_errors)
        duplicate_count = await self.component_repository.count(
            ApplicationComponent.application_id == component.application_id,
            ApplicationComponent.azure_subscription_id == subscription_id,
            func.lower(ApplicationComponent.azure_resource_group_name) == resource_group_name.lower(),
        )
        if duplicate_count:
            raise ConflictException("This resource group is already a component of the application.")
        component.azure_tenant_id = tenant_id
        component.azure_subscription_id = subscription_id
        component.azure_subscription_name = request.azure_subscription_name
        component.azure_resource_group_name = resource_group_name
        component.component_name = component.component_name or resource_group_name
        component.access_verification_status = "not_checked"

    @staticmethod
    async def _ensure_probe_url_allowed(component_configuration: dict[str, Any] | None) -> None:
        """Keigan calls the synthetic probe URL itself, so it must pass the outbound URL policy (V16)."""
        probe_url = (component_configuration or {}).get(PROBE_URL_KEY)
        if probe_url:
            await application_context.outbound_url_policy().ensure_allowed(str(probe_url), field_name=f"componentConfiguration.{PROBE_URL_KEY}")

    @staticmethod
    def _validate_non_azure_component(component: ApplicationComponent, request: ComponentCreateRequest) -> None:
        configuration = request.component_configuration or {}
        required_fields = {
            "hardware": ["device_category"],
            "mainframe": ["subsystems"],
            "saas_platform": ["vendor_name"],
        }[request.component_type]
        field_errors = [{"field": f"componentConfiguration.{field}", "message": "This field is required."} for field in required_fields if not configuration.get(field)]
        if request.component_type == "hardware" and configuration.get("device_category") not in (None, *HARDWARE_CATEGORIES):
            field_errors.append({"field": "componentConfiguration.device_category", "message": f"Use one of {', '.join(HARDWARE_CATEGORIES)}."})
        if field_errors:
            raise BusinessValidationException("Some component details are missing.", field_errors=field_errors)

    async def _create_services_for_non_azure_component(self, component: ApplicationComponent) -> None:
        """Hardware device, mainframe subsystems and SaaS product each become a monitored service so SLOs and incidents can point at them."""
        configuration = component.component_configuration_json or {}
        service_definitions: list[tuple[str, str]] = []
        if component.component_type == "hardware":
            service_definitions.append((component.component_name, "network_appliance"))
        elif component.component_type == "mainframe":
            for subsystem in configuration.get("subsystems") or []:
                subsystem_name = str(subsystem).strip()
                if subsystem_name:
                    service_definitions.append((f"{component.component_name}-{subsystem_name.lower()}", "batch_job_stream" if subsystem_name.lower() == "batch" else "mainframe_subsystem"))
        else:
            service_definitions.append((str(configuration.get("product_name") or component.component_name), "saas_service"))
        for service_name, service_type in service_definitions:
            service = MonitoredService(
                application_id=component.application_id,
                component_id=component.component_id,
                service_name=service_name,
                service_type=service_type,
                environment_name=component.environment_name,
                external_resource_identifier=configuration.get("hostname") or configuration.get("instance_url"),
                created_by_user_principal_name=component.created_by_user_principal_name,
            )
            self.session.add(service)
            await self.session.flush()
            probe_url = configuration.get(PROBE_URL_KEY)
            if component.component_type == "saas_platform" and probe_url:
                self.session.add(
                    ServiceLogSource(service_id=service.service_id, source_kind="synthetic_probe", query_scope_json={"probe_url": probe_url}, is_primary_source=True)
                )
            if configuration.get("status_page_url"):
                self.session.add(ServiceLogSource(service_id=service.service_id, source_kind="vendor_status_page", query_scope_json={"status_page_url": configuration["status_page_url"]}))
            if configuration.get("log_tool_connection_id"):
                self.session.add(
                    ServiceLogSource(
                        service_id=service.service_id,
                        source_kind="log_tool",
                        log_tool_connection_id=configuration["log_tool_connection_id"],
                        query_scope_json=configuration.get("query_scope") or {},
                        is_primary_source=True,
                    )
                )

    async def update_component(self, current_user: CurrentUser, application_id: str, component_id: str, request: ComponentUpdateRequest) -> ComponentResponse:
        component = await self._get_component(application_id, component_id)
        changes = request.model_dump(exclude_unset=True)
        if "component_configuration" in changes:
            await self._ensure_probe_url_allowed(changes["component_configuration"])
            component.component_configuration_json = {**(component.component_configuration_json or {}), **(changes.pop("component_configuration") or {})}
        for field_name, field_value in changes.items():
            if field_value is not None:
                setattr(component, field_name, field_value)
        component.updated_by_user_principal_name = current_user.user_principal_name
        await self.session.flush()
        await self.audit_service.record(
            current_user, "component.update", target_entity_type="application_component", target_entity_id=component_id, application_id=application_id,
            action_details={"changedFields": sorted(request.model_dump(exclude_unset=True).keys())},
        )
        return await self.get_component(application_id, component_id)

    async def delete_component(self, current_user: CurrentUser, application_id: str, component_id: str) -> None:
        component = await self._get_component(application_id, component_id)
        service_ids = list((await self.session.scalars(select(MonitoredService.service_id).where(MonitoredService.component_id == component_id))).all())
        if service_ids:
            await self.session.execute(delete(ServiceDependency).where(ServiceDependency.upstream_service_id.in_(service_ids) | ServiceDependency.downstream_service_id.in_(service_ids)))
            await self.session.execute(delete(ServiceLogSource).where(ServiceLogSource.service_id.in_(service_ids)))
            await self.session.execute(delete(MonitoredService).where(MonitoredService.service_id.in_(service_ids)))
        await self.session.execute(delete(DiscoveredResource).where(DiscoveredResource.component_id == component_id))
        await self.audit_service.record(
            current_user, "component.remove", target_entity_type="application_component", target_entity_id=component_id, application_id=application_id,
            action_details={"componentName": component.component_name, "servicesRemoved": len(service_ids)},
        )
        await self.component_repository.delete(component)

    # ── Role commands, resources ───────────────────────────────────────────────
    async def get_role_commands(self, application_id: str, component_id: str) -> RoleCommandsResponse:
        component = await self._get_component(application_id, component_id)
        if component.component_type != "azure_resource_group":
            raise BusinessValidationException("Role grants apply to Azure resource groups only.")
        keigan_identity = await application_context.azure_credential_provider().resolve_keigan_identity()
        return RoleCommandBuilder(self.settings, keigan_identity).build(component)

    async def list_resources(self, application_id: str, component_id: str, classification: str | None) -> list[DiscoveredResourceResponse]:
        await self._get_component(application_id, component_id)
        conditions = [DiscoveredResource.component_id == component_id]
        if classification:
            conditions.append(DiscoveredResource.monitoring_classification == classification)
        resources = await BaseRepository(self.session, DiscoveredResource).find_all(*conditions, order_by=[DiscoveredResource.resource_type, DiscoveredResource.resource_name])
        service_id_by_resource_id = dict(
            (await self.session.execute(select(MonitoredService.discovered_resource_id, MonitoredService.service_id).where(MonitoredService.component_id == component_id, MonitoredService.discovered_resource_id.is_not(None)))).all()
        )
        return [
            DiscoveredResourceResponse(
                discovered_resource_id=resource.discovered_resource_id,
                component_id=resource.component_id,
                azure_resource_id=resource.azure_resource_id,
                resource_name=resource.resource_name,
                resource_type=resource.resource_type,
                resource_type_display_name=resource_type_display_name(resource.resource_type),
                resource_kind=resource.resource_kind,
                location_name=resource.location_name,
                monitoring_classification=resource.monitoring_classification,
                has_diagnostic_setting=resource.has_diagnostic_setting,
                diagnostic_settings=resource.diagnostic_settings_json,
                last_seen_at=resource.last_seen_at,
                no_longer_found_at=resource.no_longer_found_at,
                service_id=service_id_by_resource_id.get(resource.discovered_resource_id),
            )
            for resource in resources
        ]

    # ── Starting jobs ──────────────────────────────────────────────────────────
    async def start_verification(self, current_user: CurrentUser, application_id: str, component_id: str) -> JobAcceptedResponse:
        component = await self._get_component(application_id, component_id)
        if component.component_type != "azure_resource_group":
            raise BusinessValidationException("Only Azure resource groups need access verification.")
        component.access_verification_status = "checking"
        await self.session.flush()
        job_id = await JobQueue(self.session).enqueue("verify_component_access", {"component_id": component_id}, deduplication_key=f"verify:{component_id}")
        await self.audit_service.record(current_user, "component.verify", target_entity_type="application_component", target_entity_id=component_id, application_id=application_id)
        return JobAcceptedResponse(job_id=job_id)

    async def start_discovery(self, current_user: CurrentUser, application_id: str, component_id: str) -> JobAcceptedResponse:
        component = await self._get_component(application_id, component_id)
        if component.component_type != "azure_resource_group":
            raise BusinessValidationException("Discovery applies to Azure resource groups only.")
        job_id = await JobQueue(self.session).enqueue("discover_component", {"component_id": component_id}, deduplication_key=f"discover:{component_id}")
        await self.audit_service.record(current_user, "component.discover", target_entity_type="application_component", target_entity_id=component_id, application_id=application_id)
        return JobAcceptedResponse(job_id=job_id)

    # ── Job handlers (see workers/job_handlers.py) ─────────────────────────────
    async def verify_component_access(self, component_id: str) -> dict[str, Any] | None:
        component = await self.component_repository.get_by_id(component_id)
        if component is None:
            return None
        is_simulated = self.settings.telemetry_mode == IntegrationMode.SIMULATED or bool((component.component_configuration_json or {}).get("simulated"))
        if is_simulated:
            check_results = self._simulated_access_checks(component)
        else:
            try:
                access_checks = await application_context.azure_client().verify_read_access(
                    component.azure_tenant_id, component.azure_subscription_id or "", component.azure_resource_group_name or ""
                )
                check_results = [
                    {"checkName": check.check_name, "passed": check.passed, "message": check.message, "missingRoleName": check.missing_role_name} for check in access_checks
                ]
            except IntegrationException as verification_error:
                component.access_verification_status = "failed"
                component.access_verification_details_json = [{"checkName": "list_resources", "passed": False, "message": verification_error.detail, "missingRoleName": "Reader"}]
                component.last_verified_at = utc_now()
                return {"status": "failed"}
        component.access_verification_details_json = check_results
        component.access_verification_status = "verified" if all(check["passed"] for check in check_results) else "missing_roles"
        component.last_verified_at = utc_now()
        if component.access_verification_status == "verified" and component.last_discovered_at is None:
            await JobQueue(self.session).enqueue("discover_component", {"component_id": component_id}, deduplication_key=f"discover:{component_id}")
        return {"status": component.access_verification_status, "passedChecks": sum(1 for check in check_results if check["passed"]), "totalChecks": len(check_results)}

    @staticmethod
    def _simulated_access_checks(component: ApplicationComponent) -> list[dict[str, Any]]:
        workspace_missing = SIMULATED_MISSING_ROLE_MARKER in (component.azure_resource_group_name or "").lower()
        return [
            {"checkName": "list_resources", "passed": True, "message": "Simulated: resources in the resource group are visible.", "missingRoleName": None},
            {"checkName": "read_activity_log", "passed": True, "message": "Simulated: the activity log is readable.", "missingRoleName": None},
            {"checkName": "read_metrics", "passed": True, "message": "Simulated: metrics are readable.", "missingRoleName": None},
            {
                "checkName": "query_workspace",
                "passed": not workspace_missing,
                "message": "Simulated: the Log Analytics workspace can be queried." if not workspace_missing else "Simulated: the identity cannot query the workspace yet.",
                "missingRoleName": None if not workspace_missing else "Log Analytics Reader",
            },
        ]

    async def discover_component(self, component_id: str) -> dict[str, Any] | None:
        component = await self.component_repository.get_by_id(component_id)
        if component is None:
            return None
        return await ComponentDiscoveryService(self.session).discover(component)

    # ── Helpers ────────────────────────────────────────────────────────────────
    async def _get_component(self, application_id: str, component_id: str) -> ApplicationComponent:
        component = await self.component_repository.get_required(component_id, "component")
        if component.application_id != application_id:
            raise NotFoundException("The component was not found.")
        return component

    def _to_response(self, component: ApplicationComponent, service_count: int) -> ComponentResponse:
        configuration = component.component_configuration_json or {}
        return ComponentResponse(
            component_id=component.component_id,
            application_id=component.application_id,
            component_type=component.component_type,
            component_name=component.component_name,
            environment_name=component.environment_name,
            azure_tenant_id=component.azure_tenant_id,
            azure_subscription_id=component.azure_subscription_id,
            azure_subscription_name=component.azure_subscription_name,
            azure_resource_group_name=component.azure_resource_group_name,
            component_configuration=configuration,
            access_verification_status=component.access_verification_status,
            access_verification_details=component.access_verification_details_json,
            last_verified_at=component.last_verified_at,
            last_discovered_at=component.last_discovered_at,
            discovery_summary=component.discovery_summary_json,
            service_count=service_count,
            is_simulated=self.settings.telemetry_mode == IntegrationMode.SIMULATED or bool(configuration.get("simulated")),
            updated_at=component.updated_at,
        )


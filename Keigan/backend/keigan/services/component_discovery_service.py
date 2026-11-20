"""Discovery of an Azure resource group: list, classify (catalog driven), cache diagnostics and metrics, create or update services.

Live mode reads Azure through ``AzureClient``; ``TELEMETRY_MODE=simulated`` (or a component marked simulated) uses a deterministic generator.
Re-discovery never deletes a service: resources that vanished are marked "no longer found".
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import RESOURCES_DIRECTORY, IntegrationMode, get_settings
from keigan.entities.application_entities import Application, ApplicationComponent, DiscoveredResource, MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.utils.time_utils import utc_now
from keigan.entities.status_values import CriticalityTier, ReadTestStatus

CATALOG_PATH = RESOURCES_DIRECTORY / "catalogs" / "monitored_resource_types.yaml"
MONITORED_SERVICE = "monitored_service"
TELEMETRY_SOURCE = "telemetry_source"
NOT_MONITORED = "not_monitored_type"
SERVICES_WITH_APPLICATION_INSIGHTS = ("aks", "app_service", "function_app")


@dataclass(frozen=True)
class ResourceClassification:
    classification: str
    service_type: str | None = None
    source_kind: str | None = None


@lru_cache(maxsize=1)
def load_resource_catalog() -> dict[str, Any]:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}


def classify_resource(arm_type: str, resource_kind: str | None, resource_name: str) -> ResourceClassification:
    catalog = load_resource_catalog()
    kind_tokens = {token.strip().lower() for token in (resource_kind or "").split(",") if token.strip()}
    for rule in catalog.get("monitored_types", []):
        if rule["arm_type"].lower() != arm_type.lower():
            continue
        if any(resource_name.lower().endswith(suffix.lower()) for suffix in rule.get("excluded_name_suffixes", [])):
            continue
        required_tokens = {token.lower() for token in rule.get("kind_tokens_any", [])}
        if required_tokens and not (required_tokens & kind_tokens):
            continue
        return ResourceClassification(MONITORED_SERVICE, service_type=rule["service_type"])
    for source in catalog.get("telemetry_sources", []):
        if source["arm_type"].lower() == arm_type.lower():
            return ResourceClassification(TELEMETRY_SOURCE, source_kind=source["source_kind"])
    return ResourceClassification(NOT_MONITORED)


def simulated_workspace_customer_id(workspace_resource_id: str) -> str:
    """The stable workspace id the simulator and the demo seed use for a workspace (there is no Azure to ask)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, workspace_resource_id.lower()))


def resource_type_display_name(arm_type: str) -> str:
    catalog = load_resource_catalog()
    for rule in catalog.get("monitored_types", []) + catalog.get("telemetry_sources", []):
        if rule["arm_type"].lower() == arm_type.lower():
            return rule["display_name"]
    for known_type, display_name in (catalog.get("resource_type_display_names") or {}).items():
        if known_type.lower() == arm_type.lower():
            return display_name
    return arm_type.rsplit("/", 1)[-1]


def metric_definitions_for(service_type: str) -> list[dict[str, Any]]:
    for rule in load_resource_catalog().get("monitored_types", []):
        if rule["service_type"] == service_type:
            return [
                {"name": name, "displayName": display_name, "unit": unit, "primaryAggregationType": aggregation, "supportedAggregationTypes": [aggregation]}
                for name, display_name, unit, aggregation in rule.get("metric_definitions", [])
            ]
    return []


def arm_type_for_existing_service(service_type: str, resource_identifier: str) -> str:
    """The catalog ARM type of a service; when several rules share the service type (Logic Apps) the one named in the resource id wins."""
    rules = [rule for rule in load_resource_catalog().get("monitored_types", []) if rule["service_type"] == service_type]
    matching_rule = next((rule for rule in rules if rule["arm_type"].lower() in resource_identifier.lower()), rules[0] if rules else None)
    return matching_rule["arm_type"] if matching_rule else "Microsoft.Resources/unknown"


@dataclass
class DiscoveryEntry:
    """A stored resource plus what this discovery run learned about it (not persisted as such)."""

    resource: DiscoveredResource
    service_type: str | None = None
    source_kind: str | None = None
    metric_definitions: list[dict[str, Any]] | None = None


class ComponentDiscoveryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ── Entry point ────────────────────────────────────────────────────────────
    async def discover(self, component: ApplicationComponent) -> dict[str, Any]:
        application = await self.session.get(Application, component.application_id)
        is_simulated = self.settings.telemetry_mode == IntegrationMode.SIMULATED or bool((component.component_configuration_json or {}).get("simulated"))
        existing_services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.component_id == component.component_id))).all())
        if is_simulated:
            resources = self._simulate_resources(component, application.application_code if application else "APP", existing_services)
        else:
            resources = await application_context.azure_client().list_resource_group_resources(
                component.azure_tenant_id, component.azure_subscription_id or "", component.azure_resource_group_name or ""
            )
        entries_by_resource_id = await self._upsert_discovered_resources(component, resources, is_simulated)
        service_summary = await self._create_or_update_services(component, entries_by_resource_id, existing_services)
        await self._link_telemetry_sources(component, entries_by_resource_id, is_simulated)
        summary = self._build_summary([entry.resource for entry in entries_by_resource_id.values()], service_summary)
        component.discovery_summary_json = summary
        component.last_discovered_at = utc_now()
        return summary

    # ── Discovered resources ───────────────────────────────────────────────────
    async def _upsert_discovered_resources(
        self, component: ApplicationComponent, resources: list[dict[str, Any]], is_simulated: bool
    ) -> dict[str, DiscoveryEntry]:
        existing_rows = list((await self.session.scalars(select(DiscoveredResource).where(DiscoveredResource.component_id == component.component_id))).all())
        existing_by_resource_id = {row.azure_resource_id.lower(): row for row in existing_rows}
        now = utc_now()
        seen_keys: set[str] = set()
        entries_by_resource_id: dict[str, DiscoveryEntry] = {}
        limiter = asyncio.Semaphore(6)

        async def read_diagnostics_and_metrics(resource: dict[str, Any], classification: ResourceClassification) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            if classification.classification != MONITORED_SERVICE:
                return [], []
            if is_simulated:
                return list(resource.get("simulatedDiagnosticSettings", [])), metric_definitions_for(classification.service_type or "")
            async with limiter:
                azure_client = application_context.azure_client()
                try:
                    diagnostic_settings = await azure_client.get_diagnostic_settings(component.azure_tenant_id, resource["id"])
                except IntegrationException:
                    diagnostic_settings = []
                try:
                    metric_definitions = await azure_client.get_metric_definitions(component.azure_tenant_id, resource["id"])
                except IntegrationException:
                    metric_definitions = []
                return diagnostic_settings, metric_definitions

        classifications = [classify_resource(resource["type"], resource.get("kind"), resource["name"]) for resource in resources]
        details = await asyncio.gather(*(read_diagnostics_and_metrics(resource, classification) for resource, classification in zip(resources, classifications, strict=True)))
        for resource, classification, (diagnostic_settings, metric_definitions) in zip(resources, classifications, details, strict=True):
            resource_key = resource["id"].lower()
            seen_keys.add(resource_key)
            row = existing_by_resource_id.get(resource_key)
            if row is None:
                row = DiscoveredResource(component_id=component.component_id, application_id=component.application_id, azure_resource_id=resource["id"], resource_name=resource["name"], resource_type=resource["type"])
                self.session.add(row)
            row.resource_name = resource["name"]
            row.resource_type = resource["type"]
            row.resource_kind = resource.get("kind")
            row.location_name = resource.get("location")
            row.resource_tags_json = resource.get("tags") or None
            row.monitoring_classification = classification.classification
            row.diagnostic_settings_json = [
                {"name": setting.get("name"), "workspaceId": (setting.get("properties") or setting).get("workspaceId"), "categories": [
                    category.get("category") or category.get("categoryGroup") for category in ((setting.get("properties") or setting).get("logs") or [])
                    if category.get("enabled", True)
                ]}
                for setting in diagnostic_settings
            ] if classification.classification == MONITORED_SERVICE else None
            row.has_diagnostic_setting = bool(diagnostic_settings)
            row.log_analytics_workspace_resource_ids_json = sorted(
                {str((setting.get("properties") or setting).get("workspaceId")) for setting in diagnostic_settings if (setting.get("properties") or setting).get("workspaceId")}
            ) or None
            row.last_seen_at = now
            row.no_longer_found_at = None
            entries_by_resource_id[resource_key] = DiscoveryEntry(row, classification.service_type, classification.source_kind, metric_definitions)
        for resource_key, row in existing_by_resource_id.items():
            if resource_key not in seen_keys and row.no_longer_found_at is None:
                row.no_longer_found_at = now
                entries_by_resource_id[resource_key] = DiscoveryEntry(row, classify_resource(row.resource_type, row.resource_kind, row.resource_name).service_type)
        await self.session.flush()
        return entries_by_resource_id

    # ── Services ───────────────────────────────────────────────────────────────
    async def _create_or_update_services(
        self, component: ApplicationComponent, entries_by_resource_id: dict[str, DiscoveryEntry], existing_services: list[MonitoredService]
    ) -> dict[str, int]:
        created_count = updated_count = 0
        services_by_resource_key = {service.external_resource_identifier.lower(): service for service in existing_services if service.external_resource_identifier}
        services_by_discovered_id = {service.discovered_resource_id: service for service in existing_services if service.discovered_resource_id}
        services_by_name_and_type = {(service.service_name.lower(), service.service_type): service for service in existing_services}
        for resource_key, entry in entries_by_resource_id.items():
            row, service_type = entry.resource, entry.service_type
            if row.monitoring_classification != MONITORED_SERVICE or not service_type or row.no_longer_found_at is not None:
                continue
            service_name = row.resource_name.rsplit("/", 1)[-1]
            service = services_by_discovered_id.get(row.discovered_resource_id) or services_by_resource_key.get(resource_key) or services_by_name_and_type.get((service_name.lower(), service_type))
            metric_definitions = entry.metric_definitions or None
            if service is None:
                service = MonitoredService(
                    application_id=component.application_id,
                    component_id=component.component_id,
                    service_name=service_name,
                    service_type=service_type,
                    environment_name=component.environment_name,
                    criticality_tier=CriticalityTier.TIER_2,
                    created_by_user_principal_name="system:discovery",
                )
                self.session.add(service)
                created_count += 1
            else:
                updated_count += 1
            service.discovered_resource_id = row.discovered_resource_id
            service.external_resource_identifier = service.external_resource_identifier or row.azure_resource_id
            if metric_definitions:
                service.available_metrics_json = metric_definitions
        await self.session.flush()
        return {"created": created_count, "updated": updated_count}

    async def _link_telemetry_sources(self, component: ApplicationComponent, entries_by_resource_id: dict[str, DiscoveryEntry], is_simulated: bool) -> None:
        """Auto-detect sources: metrics for every service, workspace from diagnostic settings, Application Insights when present."""
        live_entries = [entry for entry in entries_by_resource_id.values() if entry.resource.no_longer_found_at is None]
        live_rows = [entry.resource for entry in live_entries]
        application_insights = next((entry.resource for entry in live_entries if entry.source_kind == "application_insights"), None)
        workspace_row = next((entry.resource for entry in live_entries if entry.source_kind == "log_analytics_workspace"), None)
        services = list((await self.session.scalars(select(MonitoredService).where(MonitoredService.component_id == component.component_id))).all())
        diagnostics_by_discovered_id = {row.discovered_resource_id: row for row in live_rows}
        for service in services:
            existing_kinds = {
                (source.source_kind, source.log_analytics_workspace_resource_id)
                for source in await self.session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id == service.service_id))
            }
            existing_source_kinds = {kind for kind, _ in existing_kinds}
            discovered_row = diagnostics_by_discovered_id.get(service.discovered_resource_id or "")
            if "azure_monitor_metrics" not in existing_source_kinds:
                self._add_log_source(service, "azure_monitor_metrics", None, None, is_simulated)
            workspace_ids = list((discovered_row.log_analytics_workspace_resource_ids_json or []) if discovered_row else [])
            if not workspace_ids and is_simulated and discovered_row is not None and discovered_row.has_diagnostic_setting and workspace_row is not None:
                workspace_ids = [workspace_row.azure_resource_id]
            for workspace_resource_id in workspace_ids[:1]:
                if "log_analytics" not in existing_source_kinds:
                    customer_id = await self._workspace_customer_id(component, workspace_resource_id, is_simulated)
                    self._add_log_source(service, "log_analytics", workspace_resource_id, customer_id, is_simulated, is_primary=True)
            if application_insights is not None and service.service_type in SERVICES_WITH_APPLICATION_INSIGHTS:
                service.application_insights_resource_id = service.application_insights_resource_id or application_insights.azure_resource_id
                service.application_insights_role_name = service.application_insights_role_name or service.service_name
                if "application_insights" not in existing_source_kinds:
                    self._add_log_source(service, "application_insights", application_insights.azure_resource_id, None, is_simulated, is_primary=not workspace_ids)
        await self.session.flush()

    def _add_log_source(self, service: MonitoredService, source_kind: str, workspace_resource_id: str | None, customer_id: str | None, is_simulated: bool, is_primary: bool = False) -> None:
        self.session.add(
            ServiceLogSource(
                service_id=service.service_id,
                source_kind=source_kind,
                log_analytics_workspace_resource_id=workspace_resource_id,
                log_analytics_workspace_customer_id=customer_id,
                is_primary_source=is_primary,
                was_auto_detected=True,
                last_read_test_status=ReadTestStatus.PASSED if is_simulated else ReadTestStatus.NOT_TESTED,
                last_read_test_at=utc_now() if is_simulated else None,
            )
        )

    async def _workspace_customer_id(self, component: ApplicationComponent, workspace_resource_id: str, is_simulated: bool) -> str | None:
        if is_simulated:
            return simulated_workspace_customer_id(workspace_resource_id)
        try:
            return await application_context.azure_client().get_workspace_customer_id(component.azure_tenant_id, workspace_resource_id)
        except IntegrationException:
            return None

    # ── Summary ────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_summary(rows: list[DiscoveredResource], service_summary: dict[str, int]) -> dict[str, Any]:
        present_rows = [row for row in rows if row.no_longer_found_at is None]
        monitored_rows = [row for row in present_rows if row.monitoring_classification == MONITORED_SERVICE]
        by_type: dict[str, int] = {}
        for row in present_rows:
            by_type[row.resource_type] = by_type.get(row.resource_type, 0) + 1
        return {
            "resourcesFound": len(present_rows),
            "monitoredServices": len(monitored_rows),
            "telemetrySources": sum(1 for row in present_rows if row.monitoring_classification == TELEMETRY_SOURCE),
            "withoutDiagnosticSetting": sum(1 for row in monitored_rows if not row.has_diagnostic_setting),
            "noLongerFound": len(rows) - len(present_rows),
            "servicesCreated": service_summary["created"],
            "servicesUpdated": service_summary["updated"],
            "resourcesByType": by_type,
        }

    # ── Simulation ─────────────────────────────────────────────────────────────
    def _simulate_resources(self, component: ApplicationComponent, application_code: str, existing_services: list[MonitoredService]) -> list[dict[str, Any]]:
        subscription_id = component.azure_subscription_id or "00000000-0000-0000-0000-000000000000"
        resource_group = component.azure_resource_group_name or component.component_name
        prefix = application_code.lower()
        base = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers"
        location = "japaneast" if application_code.endswith("JP") else "australiaeast" if application_code.endswith("AU") else "eastus2"
        tags = {"application": application_code, "environment": component.environment_name}
        kind_by_service_type = {"function_app": "functionapp,linux", "app_service": "app,linux"}
        lacking_diagnostics = {"logic_app", "data_factory"}

        def monitored(resource_id: str, resource_type: str, name: str, service_type: str) -> dict[str, Any]:
            diagnostic_settings = [] if service_type in lacking_diagnostics else [
                {"name": "send-to-law", "properties": {"workspaceId": f"{base}/Microsoft.OperationalInsights/workspaces/law-{prefix}-prd", "logs": [{"categoryGroup": "allLogs", "enabled": True}]}}
            ]
            return {"id": resource_id, "name": name, "type": resource_type, "kind": kind_by_service_type.get(service_type), "location": location, "tags": tags, "simulatedDiagnosticSettings": diagnostic_settings}

        resources: list[dict[str, Any]] = []
        if existing_services:
            for service in existing_services:
                identifier = service.external_resource_identifier or ""
                if "/providers/" not in identifier:
                    continue
                resources.append(monitored(identifier, arm_type_for_existing_service(service.service_type, identifier), service.service_name, service.service_type))
        else:
            defaults = [
                ("Microsoft.ApiManagement/service", f"{prefix}-apim", "api_management"),
                ("Microsoft.ContainerService/managedClusters", f"{prefix}-aks-prd", "aks"),
                ("Microsoft.Web/sites", f"{prefix}-api-app", "app_service"),
                ("Microsoft.Web/sites", f"{prefix}-events-func", "function_app"),
                ("Microsoft.Logic/workflows", f"{prefix}-workflow", "logic_app"),
                ("Microsoft.DataFactory/factories", f"{prefix}-etl", "data_factory"),
                ("Microsoft.Sql/servers/databases", f"{prefix}-sqlsrv/{prefix}-db", "sql_database"),
            ]
            for arm_type, name, service_type in defaults:
                server_name, _, database_name = name.partition("/")
                resource_id = f"{base}/Microsoft.Sql/servers/{server_name}/databases/{database_name}" if database_name else f"{base}/{arm_type}/{name}"
                resources.append(monitored(resource_id, arm_type, name, service_type))
            resources.append({"id": f"{base}/Microsoft.Sql/servers/{prefix}-sqlsrv/databases/master", "name": f"{prefix}-sqlsrv/master", "type": "Microsoft.Sql/servers/databases", "location": location})
        extras = [
            ("Microsoft.Insights/components", f"appi-{prefix}-prd"),
            ("Microsoft.OperationalInsights/workspaces", f"law-{prefix}-prd"),
            ("Microsoft.Storage/storageAccounts", f"st{prefix}prd01"),
            ("Microsoft.KeyVault/vaults", f"kv-{prefix}-prd"),
            ("Microsoft.Network/networkSecurityGroups", f"nsg-{prefix}-aks"),
            ("Microsoft.ManagedIdentity/userAssignedIdentities", f"id-{prefix}-workload"),
            ("Microsoft.Web/serverFarms", f"asp-{prefix}-prd"),
        ]
        known_ids = {resource["id"].lower() for resource in resources}
        for arm_type, name in extras:
            resource_id = f"{base}/{arm_type}/{name}"
            if resource_id.lower() not in known_ids:
                resources.append({"id": resource_id, "name": name, "type": arm_type, "location": location, "tags": tags})
        return resources

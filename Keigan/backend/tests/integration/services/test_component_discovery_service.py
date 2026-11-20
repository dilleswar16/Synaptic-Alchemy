"""keigan/services/component_discovery_service.py: an Azure read that is refused is reported and logged, never turned into "nothing there"."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy import select

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.config.settings import IntegrationMode, get_settings
from keigan.entities.application_entities import ApplicationComponent, DiscoveredResource, MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.services.component_discovery_service import ComponentDiscoveryService
from support.telemetry_scope import OWN_AKS_RESOURCE_ID, SHARED_WORKSPACE_RESOURCE_ID, create_scoped_application

pytestmark = pytest.mark.usefixtures("seed_context")

AKS_RESOURCE = {"id": OWN_AKS_RESOURCE_ID, "name": "polaris-aks", "type": "Microsoft.ContainerService/managedClusters", "location": "eastus"}
DIAGNOSTIC_SETTING_TO_WORKSPACE = {"name": "to-law", "properties": {"workspaceId": SHARED_WORKSPACE_RESOURCE_ID, "logs": [{"category": "kube-audit", "enabled": True}]}}


class RefusingAzureClient:
    """Azure answers the resource list, then refuses the reads about each resource (the discovery identity lacks Reader on diagnostics)."""

    def __init__(self, *, diagnostics_refused: bool, metrics_refused: bool, workspace_lookup_refused: bool = False):
        self.diagnostics_refused = diagnostics_refused
        self.metrics_refused = metrics_refused
        self.workspace_lookup_refused = workspace_lookup_refused

    async def list_resource_group_resources(self, tenant_id: str | None, subscription_id: str, resource_group_name: str) -> list[dict[str, Any]]:
        return [AKS_RESOURCE]

    async def get_diagnostic_settings(self, tenant_id: str | None, resource_id: str) -> list[dict[str, Any]]:
        if self.diagnostics_refused:
            raise IntegrationException("Azure refused the request.", error_code="azure_forbidden")
        return [DIAGNOSTIC_SETTING_TO_WORKSPACE]

    async def get_metric_definitions(self, tenant_id: str | None, resource_id: str) -> list[dict[str, Any]]:
        if self.metrics_refused:
            raise IntegrationException("Azure refused the request.", error_code="azure_forbidden")
        return [{"name": "node_cpu_usage_percentage", "displayName": "CPU", "unit": "Percent", "primaryAggregationType": "Average", "supportedAggregationTypes": ["Average"]}]

    async def get_workspace_customer_id(self, tenant_id: str | None, workspace_resource_id: str) -> str | None:
        if self.workspace_lookup_refused:
            raise IntegrationException("Azure refused the request.", error_code="azure_forbidden")
        return "534d6995-681e-5dbf-b747-1c8ea917b67c"


async def _discover(monkeypatch: pytest.MonkeyPatch, azure_client: RefusingAzureClient) -> tuple[dict[str, Any], str]:
    monkeypatch.setattr(get_settings(), "telemetry_mode", IntegrationMode.LIVE)
    monkeypatch.setattr(application_context, "azure_client", lambda: azure_client)
    scoped = await create_scoped_application(is_simulated_component=False)
    async with open_session() as session:
        component = await session.get(ApplicationComponent, scoped.component_id)
        assert component is not None
        summary = await ComponentDiscoveryService(session).discover(component)
    return summary, scoped.component_id


async def test_refused_diagnostic_and_metric_reads_are_counted_in_the_summary_and_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="keigan.services.component_discovery_service"):
        summary, _ = await _discover(monkeypatch, RefusingAzureClient(diagnostics_refused=True, metrics_refused=True))
    assert summary["readFailures"] == {"diagnosticSettings": 1, "metricDefinitions": 1, "workspaceLookups": 0}
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert OWN_AKS_RESOURCE_ID in logged and "azure_forbidden" in logged


async def test_a_refused_diagnostic_read_is_not_reported_as_a_missing_diagnostic_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown is not the same as none: the screen must not tell the user to add a setting that may already exist."""
    summary, component_id = await _discover(monkeypatch, RefusingAzureClient(diagnostics_refused=True, metrics_refused=False))
    assert summary["withoutDiagnosticSetting"] == 0
    async with open_session() as session:
        resource = await session.scalar(select(DiscoveredResource).where(DiscoveredResource.component_id == component_id, DiscoveredResource.azure_resource_id == OWN_AKS_RESOURCE_ID))
    assert resource is not None and resource.log_analytics_workspace_resource_ids_json == [SHARED_WORKSPACE_RESOURCE_ID], "what was known before the refused read was overwritten"


async def test_a_clean_discovery_reports_no_read_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    summary, component_id = await _discover(monkeypatch, RefusingAzureClient(diagnostics_refused=False, metrics_refused=False))
    assert summary["readFailures"] == {"diagnosticSettings": 0, "metricDefinitions": 0, "workspaceLookups": 0}
    async with open_session() as session:
        service = await session.scalar(select(MonitoredService).where(MonitoredService.component_id == component_id))
    assert service is not None and service.available_metrics_json


async def test_a_refused_workspace_lookup_is_counted_and_the_log_source_is_still_created(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="keigan.services.component_discovery_service"):
        summary, component_id = await _discover(monkeypatch, RefusingAzureClient(diagnostics_refused=False, metrics_refused=False, workspace_lookup_refused=True))
    assert summary["readFailures"]["workspaceLookups"] == 1
    assert SHARED_WORKSPACE_RESOURCE_ID in " ".join(record.getMessage() for record in caplog.records)
    async with open_session() as session:
        log_source = await session.scalar(
            select(ServiceLogSource).join(MonitoredService, MonitoredService.service_id == ServiceLogSource.service_id).where(MonitoredService.component_id == component_id, ServiceLogSource.source_kind == "log_analytics")
        )
    assert log_source is not None and log_source.log_analytics_workspace_customer_id is None


def test_metric_definitions_of_an_unknown_service_type_is_an_empty_list_by_design() -> None:
    """The one legitimate empty answer: the catalog has no metrics for this type (a refused read is handled elsewhere)."""
    from keigan.services.component_discovery_service import metric_definitions_for

    assert metric_definitions_for("no_such_service_type") == []

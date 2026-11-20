"""One interface for reading telemetry, whatever the source.

Services describe *what* to read (a :class:`TelemetryTarget` built from a service + log source, and a
:class:`TelemetryQuery`); the gateway decides *how*: Log Analytics, Azure Monitor metrics, Elastic, Splunk, Datadog,
synthetic probes — or the :class:`TelemetrySimulator` when ``TELEMETRY_MODE=simulated`` or the component is marked
``{"simulated": true}`` (demo applications).

``TelemetryQuery.purpose_parameters["signal_kind"]`` tells the simulator what shape of data the query asks for:
``error_logs``, ``exceptions``, ``failed_requests``, ``failed_dependencies``, ``slow_requests``, ``kube_events``,
``pod_restarts``, ``batch_failures``, ``sli_counts``, ``count``, ``time_series``, ``generic``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from keigan.config.settings import IntegrationMode, Settings
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException, ReaderNotAvailableException
from keigan.integrations.log_tool_endpoints import log_tool_endpoint_urls
from keigan.utils.outbound_url_policy import OutboundUrlPolicy, OutboundUrlRejectedError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from keigan.entities.application_entities import ApplicationComponent, LogToolConnection, MonitoredService, ServiceLogSource
    from keigan.integrations.azure_client import AzureClient
    from keigan.integrations.log_tool_clients import LogToolClientFactory
    from keigan.integrations.simulation.telemetry_simulator import TelemetrySimulator
    from keigan.services.telemetry_access_policy import TelemetryAccessPolicy


@dataclass
class TelemetryQuery:
    query_language: str  # kql | elastic_dsl | esql | spl | datadog | metrics_api | probe
    query_text: str
    time_range_start: datetime
    time_range_end: datetime
    maximum_rows: int = 500
    query_purpose: str = "ad_hoc"  # template key from query_templates.yaml, or "ad_hoc"
    purpose_parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def signal_kind(self) -> str:
        return str(self.purpose_parameters.get("signal_kind", "generic"))


@dataclass
class TelemetryTarget:
    """Everything needed to query one service through one log source."""

    application_id: str
    service_id: str | None
    service_name: str
    service_type: str
    source_kind: str  # log_analytics | application_insights | azure_monitor_metrics | log_tool | synthetic_probe | vendor_status_page
    azure_tenant_id: str | None = None
    azure_resource_id: str | None = None
    log_analytics_workspace_resource_id: str | None = None
    log_analytics_workspace_customer_id: str | None = None
    aks_namespace_filter: str | None = None
    application_insights_role_name: str | None = None
    log_tool_connection: "LogToolConnection | None" = None
    query_scope: dict[str, Any] = field(default_factory=dict)
    environment_name: str = "prod"
    use_simulation: bool = False

    @classmethod
    def from_entities(
        cls,
        service: "MonitoredService",
        log_source: "ServiceLogSource | None",
        component: "ApplicationComponent | None" = None,
        log_tool_connection: "LogToolConnection | None" = None,
    ) -> "TelemetryTarget":
        component_configuration = (component.component_configuration_json or {}) if component else {}
        return cls(
            application_id=service.application_id,
            service_id=service.service_id,
            service_name=service.service_name,
            service_type=service.service_type,
            source_kind=log_source.source_kind if log_source else "azure_monitor_metrics",
            azure_tenant_id=component.azure_tenant_id if component else None,
            azure_resource_id=service.external_resource_identifier,
            log_analytics_workspace_resource_id=log_source.log_analytics_workspace_resource_id if log_source else None,
            log_analytics_workspace_customer_id=log_source.log_analytics_workspace_customer_id if log_source else None,
            aks_namespace_filter=service.aks_namespace_filter,
            application_insights_role_name=service.application_insights_role_name,
            log_tool_connection=log_tool_connection,
            query_scope=(log_source.query_scope_json or {}) if log_source else {},
            environment_name=service.environment_name,
            use_simulation=bool(component_configuration.get("simulated")),
        )


@dataclass
class LogQueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    executed_query_text: str
    query_language: str
    deep_link_url: str | None = None
    is_simulated: bool = False
    is_truncated: bool = False
    duration_milliseconds: int = 0

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass
class MetricSeries:
    metric_name: str
    unit: str
    aggregation: str
    points: list[tuple[datetime, float | None]]


@dataclass
class MetricQueryResult:
    series: list[MetricSeries]
    is_simulated: bool = False


@dataclass
class ChangeEvent:
    occurred_at: datetime
    change_kind: str  # deployment | configuration_change | scaling | restart | other
    operation_name: str
    resource_identifier: str
    description: str
    status: str = "Succeeded"
    caller: str | None = None


@dataclass
class ConnectionTestResult:
    succeeded: bool
    message: str
    newest_log_timestamp: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeResult:
    succeeded: bool
    status_code: int | None
    latency_milliseconds: int
    message: str


class TelemetryGateway:
    """Every telemetry read goes through here, so the access policy (approved applications, the application's own resources) and
    the outbound URL policy are enforced in one place, in simulated mode too."""

    def __init__(
        self,
        settings: Settings,
        azure_client: "AzureClient",
        log_tool_client_factory: "LogToolClientFactory",
        telemetry_simulator: "TelemetrySimulator",
        access_policy: "TelemetryAccessPolicy",
        outbound_url_policy: OutboundUrlPolicy,
    ):
        self.settings = settings
        self.azure_client = azure_client
        self.log_tool_client_factory = log_tool_client_factory
        self.telemetry_simulator = telemetry_simulator
        self.access_policy = access_policy
        self.outbound_url_policy = outbound_url_policy

    def is_simulated(self, telemetry_target: TelemetryTarget | None = None) -> bool:
        return self.settings.telemetry_mode == IntegrationMode.SIMULATED or bool(telemetry_target and telemetry_target.use_simulation)

    async def _ensure_log_tool_endpoints_allowed(self, log_tool_connection: "LogToolConnection") -> None:
        """The stored endpoint may predate the outbound policy or have been changed in the database: check it again before calling."""
        for _field_name, endpoint_url in log_tool_endpoint_urls(log_tool_connection.tool_type, log_tool_connection.endpoint_url, log_tool_connection.connection_configuration_json):
            try:
                await self.outbound_url_policy.ensure_allowed(endpoint_url)
            except OutboundUrlRejectedError as rejection:
                logger.warning("Refused to call the log tool connection %s: %s", log_tool_connection.log_tool_connection_id, rejection.reason)
                raise ForbiddenException(
                    f"Keigan will not call the {log_tool_connection.connection_name} endpoint. {rejection.reason} Ask an application admin to correct the connection."
                ) from None

    async def query_logs(self, telemetry_target: TelemetryTarget, telemetry_query: TelemetryQuery) -> LogQueryResult:
        await self.access_policy.ensure_can_read_source(telemetry_target)
        if self.is_simulated(telemetry_target):
            return await self.telemetry_simulator.query_logs(telemetry_target, telemetry_query)
        started_at = time.monotonic()
        if telemetry_target.source_kind in ("log_analytics", "application_insights"):
            if telemetry_query.query_language != "kql":
                raise BusinessValidationException("Log Analytics sources accept KQL queries only.")
            if not telemetry_target.log_analytics_workspace_customer_id:
                raise BusinessValidationException(f"{telemetry_target.service_name} has no Log Analytics workspace linked.")
            columns, rows = await self.azure_client.query_log_analytics(
                telemetry_target.azure_tenant_id,
                telemetry_target.log_analytics_workspace_customer_id,
                telemetry_query.query_text,
                telemetry_query.time_range_start,
                telemetry_query.time_range_end,
            )
            return LogQueryResult(
                columns=columns,
                rows=rows[: telemetry_query.maximum_rows],
                executed_query_text=telemetry_query.query_text,
                query_language="kql",
                is_truncated=len(rows) > telemetry_query.maximum_rows,
                duration_milliseconds=int((time.monotonic() - started_at) * 1000),
            )
        if telemetry_target.source_kind == "log_tool" and telemetry_target.log_tool_connection is not None:
            await self._ensure_log_tool_endpoints_allowed(telemetry_target.log_tool_connection)
            log_tool_client = await self.log_tool_client_factory.client_for(telemetry_target.log_tool_connection)
            log_query_result = await log_tool_client.search(telemetry_query, telemetry_target.query_scope)
            log_query_result.duration_milliseconds = int((time.monotonic() - started_at) * 1000)
            return log_query_result
        raise ReaderNotAvailableException(f"Keigan cannot query {telemetry_target.source_kind} logs for {telemetry_target.service_name} yet.")

    async def query_metrics(
        self,
        telemetry_target: TelemetryTarget,
        metric_names: list[str],
        time_range_start: datetime,
        time_range_end: datetime,
        interval_minutes: int = 5,
        aggregation: str = "Average",
        metric_filter: str | None = None,
    ) -> MetricQueryResult:
        await self.access_policy.ensure_can_read_metrics(telemetry_target)
        if self.is_simulated(telemetry_target):
            return await self.telemetry_simulator.query_metrics(telemetry_target, metric_names, time_range_start, time_range_end, interval_minutes, aggregation)
        if not telemetry_target.azure_resource_id or not telemetry_target.azure_resource_id.startswith("/subscriptions/"):
            raise ReaderNotAvailableException(f"Metrics for {telemetry_target.service_name} are only available for Azure resources.")
        return await self.azure_client.query_metrics(
            telemetry_target.azure_tenant_id,
            telemetry_target.azure_resource_id,
            metric_names,
            time_range_start,
            time_range_end,
            interval_minutes,
            aggregation,
            metric_filter,
        )

    async def query_activity_changes(
        self,
        application_id: str,
        azure_tenant_id: str | None,
        azure_subscription_id: str | None,
        azure_resource_group_name: str | None,
        time_range_start: datetime,
        time_range_end: datetime,
        use_simulation: bool = False,
    ) -> list[ChangeEvent]:
        await self.access_policy.ensure_can_read_activity(application_id, azure_subscription_id, azure_resource_group_name)
        if self.settings.telemetry_mode == IntegrationMode.SIMULATED or use_simulation or not azure_subscription_id:
            return await self.telemetry_simulator.query_activity_changes(application_id, time_range_start, time_range_end)
        return await self.azure_client.list_activity_changes(
            azure_tenant_id, azure_subscription_id, azure_resource_group_name, time_range_start, time_range_end
        )

    async def test_log_source(self, telemetry_target: TelemetryTarget) -> ConnectionTestResult:
        await self.access_policy.ensure_can_read_source(telemetry_target)
        if self.is_simulated(telemetry_target):
            return ConnectionTestResult(True, "Simulated source: telemetry is readable.", newest_log_timestamp=datetime.now().astimezone())
        if telemetry_target.source_kind in ("log_analytics", "application_insights"):
            return await self.azure_client.test_workspace_query(telemetry_target.azure_tenant_id, telemetry_target.log_analytics_workspace_customer_id)
        if telemetry_target.source_kind == "azure_monitor_metrics":
            return await self.azure_client.test_metric_read(telemetry_target.azure_tenant_id, telemetry_target.azure_resource_id)
        if telemetry_target.source_kind == "log_tool" and telemetry_target.log_tool_connection is not None:
            return await self.test_log_tool_connection(telemetry_target.log_tool_connection)
        if telemetry_target.source_kind == "synthetic_probe":
            probe_result = await self.probe_endpoint(
                str(telemetry_target.query_scope.get("probe_url", "")), application_id=telemetry_target.application_id, use_simulation=telemetry_target.use_simulation
            )
            return ConnectionTestResult(probe_result.succeeded, probe_result.message)
        return ConnectionTestResult(False, f"Keigan cannot test {telemetry_target.source_kind} sources yet.")

    async def test_log_tool_connection(self, log_tool_connection: "LogToolConnection") -> ConnectionTestResult:
        await self.access_policy.ensure_can_use_connection(log_tool_connection)
        if self.settings.telemetry_mode == IntegrationMode.SIMULATED:
            return ConnectionTestResult(True, "Simulated connection: Keigan can read this tool.", newest_log_timestamp=datetime.now().astimezone())
        await self._ensure_log_tool_endpoints_allowed(log_tool_connection)
        try:
            log_tool_client = await self.log_tool_client_factory.client_for(log_tool_connection)
        except ReaderNotAvailableException as reader_error:
            return ConnectionTestResult(False, reader_error.detail, details={"readerNotAvailable": True})
        return await log_tool_client.test_connection()

    async def probe_endpoint(self, probe_url: str, timeout_seconds: float = 10.0, application_id: str | None = None, use_simulation: bool = False) -> ProbeResult:
        if application_id is not None:
            await self.access_policy.ensure_application_approved(application_id)
        if self.settings.telemetry_mode == IntegrationMode.SIMULATED or use_simulation:
            return await self.telemetry_simulator.probe_endpoint(probe_url, application_id)
        try:
            await self.outbound_url_policy.ensure_allowed(probe_url)
        except OutboundUrlRejectedError as rejection:
            logger.warning("Refused to probe %s: %s", probe_url[:200], rejection.reason)
            return ProbeResult(False, None, 0, f"This probe URL is not allowed. {rejection.reason}")
        started_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as http_client:
                probe_response = await http_client.get(probe_url, headers={"User-Agent": "Keigan-Synthetic-Probe/1.0"})
            latency_milliseconds = int((time.monotonic() - started_at) * 1000)
            return ProbeResult(probe_response.status_code < 400, probe_response.status_code, latency_milliseconds, f"HTTP {probe_response.status_code}")
        except httpx.HTTPError as probe_error:
            logger.info("Synthetic probe of %s failed: %s", probe_url, type(probe_error).__name__)
            return ProbeResult(False, None, int((time.monotonic() - started_at) * 1000), "The URL could not be reached (network error or timeout).")

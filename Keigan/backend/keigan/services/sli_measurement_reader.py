"""Reads good/total (or value) samples for an SLI through the telemetry gateway, plus the SLI catalogue loader.

Simulated telemetry answers the ``sli_counts`` signal; live sources use Application Insights KQL, Azure Monitor metrics, or the SLI's own query.
Results are memoised per instance so proposals, accept and backfill do not re-query the same 30 days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.config.settings import RESOURCES_DIRECTORY
from keigan.entities.application_entities import ApplicationComponent, LogToolConnection, MonitoredService, ServiceLogSource
from keigan.exceptions.keigan_exceptions import ReaderNotAvailableException
from keigan.integrations.telemetry_gateway import TelemetryQuery, TelemetryTarget
from keigan.utils.time_utils import ensure_utc

LATENCY_METRIC_NAMES = {"api_management": "Duration", "app_service": "HttpResponseTime", "function_app": "FunctionExecutionUnits", "logic_app": "RunLatency"}
BAD_EVENT_METRICS = {"apim_availability": ("Requests", "FailedRequests"), "appservice_availability": ("Requests", "Http5xx"), "logicapp_run_success": ("RunsCompleted", "RunsFailed"), "adf_pipeline_success": ("PipelineSucceededRuns", "PipelineFailedRuns")}


@lru_cache
def load_sli_catalog() -> dict[str, Any]:
    return yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "sli_catalog.yaml").read_text(encoding="utf-8"))


def catalog_entries_for_service(service: MonitoredService, has_application_insights: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(SLO-grade entries, supporting signals) for one service. Application Insights entries come first when the service is linked to it."""
    catalog = load_sli_catalog()
    type_block = catalog["service_types"].get(service.service_type, {})
    entries = list(type_block.get("entries", []))
    supporting = list(type_block.get("supporting_signals", []))
    if has_application_insights and service.service_type not in ("function_app",):
        entries = list(catalog["application_insights_entries"]) + entries
        supporting = list(catalog["application_insights_supporting_signals"]) + supporting
    return entries, supporting


@dataclass
class SliSample:
    window_start: datetime
    good: int | None
    total: int | None
    value: float | None


class SliMeasurementReader:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._memo: dict[tuple[Any, ...], list[SliSample]] = {}
        self._targets: dict[str, TelemetryTarget] = {}

    async def target_for(self, service_id: str) -> TelemetryTarget:
        if service_id in self._targets:
            return self._targets[service_id]
        service = await self.session.get(MonitoredService, service_id)
        log_source = await self.session.scalar(select(ServiceLogSource).where(ServiceLogSource.service_id == service_id).order_by(ServiceLogSource.is_primary_source.desc()).limit(1))
        component = await self.session.get(ApplicationComponent, service.component_id) if service.component_id else None
        connection = await self.session.get(LogToolConnection, log_source.log_tool_connection_id) if log_source and log_source.log_tool_connection_id else None
        target = TelemetryTarget.from_entities(service, log_source, component, connection)
        self._targets[service_id] = target
        return target

    async def read_samples(
        self, service_id: str, *, sli_kind: str, catalog_entry_key: str, start: datetime, end: datetime, interval_minutes: int, latency_threshold_milliseconds: int | None = None, query_definition: dict[str, Any] | None = None,
    ) -> list[SliSample]:
        memo_key = (service_id, sli_kind, catalog_entry_key, latency_threshold_milliseconds, start, end, interval_minutes, str(query_definition))
        if memo_key in self._memo:
            return self._memo[memo_key]
        target = await self.target_for(service_id)
        gateway = application_context.telemetry_gateway()
        samples: list[SliSample] = []
        if gateway.is_simulated(target):
            simulator_kind = "supporting_signal" if sli_kind == "supporting_signal" else ("latency" if sli_kind == "latency" else "availability")
            result = await gateway.query_logs(target, TelemetryQuery(
                query_language="kql", query_text=f"sli_counts {catalog_entry_key}", time_range_start=start, time_range_end=end, query_purpose="sli_counts",
                purpose_parameters={"signal_kind": "sli_counts", "sli_kind": simulator_kind, "interval_minutes": interval_minutes, "latency_threshold_milliseconds": latency_threshold_milliseconds},
            ))
            samples = [self._row_to_sample(row) for row in result.rows]
        elif query_definition and query_definition.get("kql"):
            result = await gateway.query_logs(target, TelemetryQuery(query_language="kql", query_text=str(query_definition["kql"]), time_range_start=start, time_range_end=end, query_purpose="custom_sli", purpose_parameters={"signal_kind": "generic"}))
            samples = [self._row_to_sample(row) for row in result.rows]
        elif target.source_kind in ("log_analytics", "application_insights") and catalog_entry_key.startswith("appinsights_"):
            result = await gateway.query_logs(target, TelemetryQuery(query_language="kql", query_text=self._application_insights_query(target, catalog_entry_key, latency_threshold_milliseconds, interval_minutes), time_range_start=start, time_range_end=end, query_purpose="sli_counts", purpose_parameters={"signal_kind": "generic"}))
            samples = [self._row_to_sample(row) for row in result.rows]
        elif catalog_entry_key in BAD_EVENT_METRICS:
            total_metric, bad_metric = BAD_EVENT_METRICS[catalog_entry_key]
            metrics = await gateway.query_metrics(target, [total_metric, bad_metric], start, end, interval_minutes, "Total")
            series = {item.metric_name: dict(item.points) for item in metrics.series}
            for window_start, total_value in sorted(series.get(total_metric, {}).items()):
                bad_value = (series.get(bad_metric) or {}).get(window_start) or 0
                if total_value is not None:
                    samples.append(SliSample(window_start, int(max(0, total_value - bad_value)), int(total_value), None))
        else:
            raise ReaderNotAvailableException(f"No reader can measure {catalog_entry_key} for {target.service_name} yet.")
        self._memo[memo_key] = samples
        return samples

    @staticmethod
    def _row_to_sample(row: dict[str, Any]) -> SliSample:
        window_start = ensure_utc(datetime.fromisoformat(str(row["window_start"]).replace("Z", "+00:00")))
        return SliSample(window_start, int(row["good"]) if row.get("good") is not None else None, int(row["total"]) if row.get("total") is not None else None, float(row["value"]) if row.get("value") is not None else None)

    @staticmethod
    def _application_insights_query(target: TelemetryTarget, entry_key: str, threshold: int | None, interval_minutes: int) -> str:
        role_filter = f'| where AppRoleName == "{target.application_insights_role_name}"' if target.application_insights_role_name else ""
        table, good_expression = ("AppDependencies", "countif(Success == true)") if "dependency" in entry_key else ("AppRequests", f"countif(DurationMs <= {threshold or 500})" if "latency" in entry_key else "countif(Success == true)")
        return f"{table} {role_filter} | summarize good={good_expression}, total=count() by window_start=bin(TimeGenerated, {interval_minutes}m)"

    async def read_latency_p95_milliseconds(self, service_id: str, service_type: str, start: datetime, end: datetime) -> float | None:
        target = await self.target_for(service_id)
        metric_name = LATENCY_METRIC_NAMES.get(service_type, "Duration")
        result = await application_context.telemetry_gateway().query_metrics(target, [metric_name], start, end, 60, "Average")
        values = sorted(value for series in result.series for _, value in series.points if value is not None)
        if not values:
            return None
        return values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)]

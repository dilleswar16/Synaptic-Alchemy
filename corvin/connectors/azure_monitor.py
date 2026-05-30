"""Azure Monitor / Log Analytics connector — parametrised from DB config."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from corvin.connectors.base import BaseConnector, TestResult

_log = logging.getLogger(__name__)


class AzureMonitorConnector(BaseConnector):
    """
    Connects to an Azure Log Analytics workspace.

    config keys:
        workspace_id (required): Log Analytics workspace GUID
        apim_table (optional, default "ApiManagementGatewayLogs"): table for log queries
    credential_value: ignored — uses DefaultAzureCredential / managed identity
    """

    def __init__(self, config: dict[str, Any], credential_value: str | None = None) -> None:
        self._workspace_id: str = config.get("workspace_id", "")
        self._apim_table: str = config.get("apim_table", "ApiManagementGatewayLogs")
        self._client = None
        try:
            from azure.identity import DefaultAzureCredential
            from azure.monitor.query import LogsQueryClient
            self._client = LogsQueryClient(DefaultAzureCredential())
        except Exception as exc:
            _log.warning("AzureMonitorConnector: client init failed: %s", exc)

    def test_connection(self) -> TestResult:
        if self._client is None:
            return TestResult(ok=False, message="Azure credential unavailable or SDK not installed")
        if not self._workspace_id:
            return TestResult(ok=False, message="workspace_id is empty")
        t0 = time.monotonic()
        try:
            from azure.monitor.query import LogsQueryStatus
            result = self._client.query_workspace(
                workspace_id=self._workspace_id,
                query="union * | take 1 | project TimeGenerated",
                timespan=timedelta(minutes=5),
            )
            ms = (time.monotonic() - t0) * 1000
            if result.status == LogsQueryStatus.SUCCESS:
                return TestResult(ok=True, message="Connected successfully", latency_ms=ms)
            return TestResult(ok=False, message=f"Query status: {result.status}", latency_ms=ms)
        except Exception as exc:
            ms = (time.monotonic() - t0) * 1000
            return TestResult(ok=False, message=str(exc), latency_ms=ms)

    def fetch_logs(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if self._client is None or not self._workspace_id:
            return []
        from azure.monitor.query import LogsQueryStatus
        query = (
            f"{self._apim_table}\n"
            f'| where BackendId contains "{service_name}" or ApimSubscriptionId contains "{service_name}"\n'
            "| order by TimeGenerated desc\n"
            "| take 100"
        )
        try:
            result = self._client.query_workspace(
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=time_range_minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            cols = [c.name for c in result.tables[0].columns]
            return [dict(zip(cols, row)) for row in result.tables[0].rows]
        except Exception as exc:
            _log.debug("AzureMonitorConnector.fetch_logs: %s", exc)
            return []

    def fetch_metrics(self, service_name: str, time_range_minutes: int = 60) -> list[dict[str, Any]]:
        if self._client is None or not self._workspace_id:
            return []
        from azure.monitor.query import LogsQueryStatus
        query = (
            "ContainerInsights\n"
            f'| where Computer contains "{service_name}" or Namespace contains "{service_name}"\n'
            "| summarize avg(UsagePercent) by bin(TimeGenerated, 5m)\n"
            "| order by TimeGenerated desc"
        )
        try:
            result = self._client.query_workspace(
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=time_range_minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            cols = [c.name for c in result.tables[0].columns]
            return [dict(zip(cols, row)) for row in result.tables[0].rows]
        except Exception as exc:
            _log.debug("AzureMonitorConnector.fetch_metrics: %s", exc)
            return []

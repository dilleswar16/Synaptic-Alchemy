"""Azure Log Analytics evidence adapter.

Queries Log Analytics workspaces for APIM gateway logs using the
azure-monitor-query package. Runtime workspace resolution is DB-first via the
application connector registry. Optional injected config is supported for tests
or explicit overrides.
"""

from __future__ import annotations

import logging
import os
import re

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore is optional; required in corporate proxy environments
from datetime import timedelta
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from corvin.connectors.config_resolver import ROLE_APIM_LOGS, resolve_log_source_config

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


class LogAnalyticsAdapter:
    """Adapter for querying Azure Log Analytics (primarily APIM evidence)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = dict(config or {})
        # Build the credential and client once so they are reused across calls.
        # Construction is guarded so that missing/empty credentials (e.g. local
        # dev without Azure env vars set) produce a warning and a None client
        # rather than raising at import time.
        self._client: LogsQueryClient | None = None
        try:
            # DefaultAzureCredential tries EnvironmentCredential (service principal
            # via AZURE_CLIENT_ID/SECRET/TENANT) first, then falls back to
            # AzureCliCredential for local dev (az login session).
            credential = DefaultAzureCredential()
            self._client = LogsQueryClient(credential)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LogAnalyticsAdapter: could not build client (will return empty results): %s", exc)
        self._workspace_id = _expand(self._config.get("workspace_id", ""))

    def _resolved_config(self, service_name: str) -> dict[str, Any]:
        cfg = resolve_log_source_config(
            service_name,
            source_type="azure_monitor",
            role=ROLE_APIM_LOGS,
            fallback=self._config,
        )
        if cfg.get("workspace_id"):
            cfg["workspace_id"] = _expand(str(cfg["workspace_id"]))
        return cfg

    def get_apim_logs(
        self,
        service_name: str,
        environment: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query Log Analytics for APIM gateway logs related to a service.

        Runs a Kusto query against the configured workspace. Rows are returned
        as plain dicts keyed by column name.

        Args:
            service_name:       API or backend service name to filter on.
            environment:        Optional environment label filter (e.g. "production").
            time_range_minutes: Lookback window; defaults to config default_time_range_minutes.

        Returns:
            List of log row dicts. Empty list on error or no results.
        """
        cfg = self._resolved_config(service_name)
        minutes = time_range_minutes or cfg.get("default_time_range_minutes", 30)
        table = cfg.get("apim_table", "ApiManagementGatewayLogs")
        workspace_id = cfg.get("workspace_id", self._workspace_id)

        if not workspace_id:
            logger.warning(
                "LogAnalyticsAdapter.get_apim_logs skipped: no workspace configured for service=%s",
                service_name,
            )
            return []

        env_filter = (
            f'\n| where ApiId =~ "{environment}"' if environment else ""
        )

        query = (
            f"{table}\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where ApiId contains "{service_name}" or BackendId contains "{service_name}"\n'
            f"{env_filter}"
            f"| project TimeGenerated, OperationName, ResponseCode, BackendResponseCode,"
            f" BackendTime, ApiId, OperationId, BackendId, LastErrorMessage\n"
            f"| order by TimeGenerated desc"
        )

        try:
            if self._client is None:
                logger.warning(
                    "LogAnalyticsAdapter.get_apim_logs skipped: client not configured (service=%s)",
                    service_name,
                )
                return []
            result = self._client.query_workspace(
                workspace_id=workspace_id,
                query=query,
                timespan=timedelta(minutes=minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            log_table = result.tables[0]
            columns = [col.name if hasattr(col, "name") else col for col in log_table.columns]
            return [
                {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(columns, row)}
                for row in log_table.rows
            ]
        except Exception as exc:
            logger.warning(
                "LogAnalyticsAdapter.get_apim_logs failed for service=%s: %s",
                service_name,
                exc,
            )
            return []

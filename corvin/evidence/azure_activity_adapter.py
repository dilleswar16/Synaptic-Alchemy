"""
Azure Activity Log evidence adapter.

Collects recent resource change events from the Azure Activity Log for a
given service using the azure-monitor-query package (LogsQueryClient).  The
Activity Log is queried via Log Analytics using the AzureActivity table.

This is the change-correlation evidence source: it answers "what changed
before the alert fired?"

Runtime config is env/bootstrap-driven by default and can be overridden by
DB connector settings resolved per service at call time.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from typing import Any

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore is optional; required in corporate proxy environments

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from corvin.connectors.config_resolver import ROLE_AZURE_ACTIVITY, resolve_log_source_config

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


class AzureActivityAdapter:
    """Adapter for querying the Azure Activity Log (change correlation)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else _default_config()
        # Build the credential and client once so they are reused across calls.
        # Guard construction so that missing credentials in dev produce a warning
        # and a None client rather than raising at import time.
        self._client: LogsQueryClient | None = None
        try:
            # DefaultAzureCredential tries EnvironmentCredential (service principal
            # via AZURE_CLIENT_ID/SECRET/TENANT) first, then falls back to
            # AzureCliCredential for local dev (az login session).
            credential = DefaultAzureCredential()
            self._client = LogsQueryClient(credential)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AzureActivityAdapter: could not build client (will return empty results): %s", exc
            )
        self._workspace_id = _expand(self._config.get("workspace_id", ""))

    def _resolved_config(self, service_name: str) -> dict[str, Any]:
        cfg = resolve_log_source_config(
            service_name,
            source_type="azure_monitor",
            role=ROLE_AZURE_ACTIVITY,
            fallback=self._config,
        )
        if cfg.get("workspace_id"):
            cfg["workspace_id"] = _expand(str(cfg["workspace_id"]))
        return cfg

    def get_recent_changes(
        self,
        service_name: str,
        environment: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent Activity Log events related to a service.

        Queries the AzureActivity table in Log Analytics, filtering on
        ResourceGroup or Resource containing service_name.

        Args:
            service_name:       Resource name or tag filter to scope Activity Log events.
            environment:        Optional environment hint (not used as a KQL filter;
                                kept for interface parity with other adapters).
            time_range_minutes: How far back to look. Defaults to config value.

        Returns:
            List of Activity Log event dicts keyed by column name. Empty list on error.
        """
        if self._client is None:
            logger.warning(
                "AzureActivityAdapter.get_recent_changes skipped: client not configured (service=%s)",
                service_name,
            )
            return []

        cfg = self._resolved_config(service_name)
        minutes = time_range_minutes or cfg.get("default_time_range_minutes", 60)
        max_events = cfg.get("max_events", 100)
        table = str(cfg.get("activity_table", "AzureActivity"))
        workspace_id = str(cfg.get("workspace_id", self._workspace_id))

        if not workspace_id:
            logger.warning(
                "AzureActivityAdapter.get_recent_changes skipped: no workspace configured for service=%s",
                service_name,
            )
            return []

        query = (
            f"{table}\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where ResourceGroup contains "{service_name}" or Resource contains "{service_name}"\n'
            f"| project TimeGenerated, OperationNameValue, ActivityStatusValue, "
            f"Caller, ResourceGroup, Resource, SubscriptionId, Properties\n"
            f"| order by TimeGenerated desc\n"
            f"| take {max_events}"
        )

        try:
            result = self._client.query_workspace(
                workspace_id=workspace_id,
                query=query,
                timespan=timedelta(minutes=minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            log_table = result.tables[0]
            columns = [col.name if hasattr(col, "name") else col for col in log_table.columns]
            return [dict(zip(columns, row)) for row in log_table.rows]
        except Exception as exc:
            logger.warning(
                "AzureActivityAdapter.get_recent_changes failed for service=%s: %s",
                service_name,
                exc,
            )
            return []


def _default_config() -> dict[str, Any]:
    return {
        "workspace_id": os.environ.get("LOG_ANALYTICS_WORKSPACE_ID", ""),
        "activity_table": os.environ.get("AZURE_ACTIVITY_TABLE", "AzureActivity"),
        "default_time_range_minutes": _env_int("AZURE_ACTIVITY_DEFAULT_TIME_RANGE_MINUTES", 60),
        "max_events": _env_int("AZURE_ACTIVITY_MAX_EVENTS", 100),
    }


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default

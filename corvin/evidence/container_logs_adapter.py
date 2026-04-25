"""
Container Insights evidence adapter.

Queries the CHAD Log Analytics workspace for AKS container logs and pod
inventory using Azure Monitor Container Insights tables:

  - ContainerLogV2    : pod stdout/stderr application logs
  - KubePodInventory  : pod state, restarts, phases
  - KubeEvents        : OOMKill, BackOff, scheduling failures

This adapter replaces Elastic for application and Kubernetes metrics when
Elastic is unavailable (e.g. org SSO restrictions).

Config is loaded from config/integrations/container_logs.yaml.
Auth uses DefaultAzureCredential (AzureCliCredential for local dev,
service principal via AZURE_CLIENT_ID/SECRET/TENANT for production).
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

from corvin.core.config_loader import get_env, load_config

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


def _to_dicts(table: Any) -> list[dict[str, Any]]:
    """Convert a LogsQueryResult table to a list of plain dicts."""
    columns = [c.name if hasattr(c, "name") else c for c in table.columns]
    return [dict(zip(columns, row)) for row in table.rows]


class ContainerLogsAdapter:
    """Adapter for querying AKS container logs via Azure Monitor Container Insights."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = (
            config if config is not None
            else load_config("integrations/container_logs", get_env())
        )
        self._client: LogsQueryClient | None = None
        try:
            credential = DefaultAzureCredential()
            self._client = LogsQueryClient(credential)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ContainerLogsAdapter: could not build client (will return empty results): %s", exc
            )
        self._workspace_id = _expand(self._config.get("workspace_id", ""))

    # ── Public methods ────────────────────────────────────────────────────────

    def get_container_logs(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent stdout/stderr logs for a service from ContainerLogV2.

        Args:
            service_name:       Pod name prefix or container name to filter on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of log row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")
        max_rows = self._config.get("max_log_rows", 200)

        query = (
            f"ContainerLog\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Name contains "{service_name}" or Image contains "{service_name}"\n'
            f"| project TimeGenerated, Name, Image, LogEntry, LogEntrySource, ContainerID\n"
            f"| order by TimeGenerated desc\n"
            f"| take {max_rows}"
        )

        return self._run_query(query, minutes, f"get_container_logs(service={service_name})")

    def get_pod_inventory(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch pod state and restart counts from KubePodInventory.

        Args:
            service_name:       Deployment or pod name prefix to filter on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of pod inventory row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubePodInventory\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| project TimeGenerated, Name, Namespace, PodStatus, ContainerStatus,"
            f" ContainerStatusReason, ContainerRestartCount, PodRestartCount, ControllerName, ControllerKind\n"
            f"| summarize arg_max(TimeGenerated, *) by Name"
        )

        return self._run_query(query, minutes, f"get_pod_inventory(service={service_name})")

    def get_kube_events(
        self,
        service_name: str,
        namespace: str | None = None,
        time_range_minutes: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch Kubernetes warning events for a service from KubeEvents.

        Args:
            service_name:       Object name prefix to filter events on.
            namespace:          Kubernetes namespace. Defaults to config default_namespace.
            time_range_minutes: Lookback window. Defaults to config value.

        Returns:
            List of event row dicts. Empty list on error or no results.
        """
        if self._client is None:
            return []

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        ns = namespace or self._config.get("default_namespace", "chad")

        query = (
            f"KubeEvents\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where Namespace == "{ns}"\n'
            f'| where Name contains "{service_name}"\n'
            f"| where KubeEventType == 'Warning'\n"
            f"| project TimeGenerated, Name, Namespace, Reason, Message, KubeEventType, Count\n"
            f"| order by TimeGenerated desc\n"
            f"| take 50"
        )

        return self._run_query(query, minutes, f"get_kube_events(service={service_name})")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_query(
        self, query: str, minutes: int, label: str
    ) -> list[dict[str, Any]]:
        try:
            result = self._client.query_workspace(  # type: ignore[union-attr]
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            return _to_dicts(result.tables[0])
        except Exception as exc:
            logger.warning("ContainerLogsAdapter.%s failed: %s", label, exc)
            return []

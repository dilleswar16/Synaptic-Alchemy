"""
Azure Activity Log evidence adapter.

Collects recent resource change events from the Azure Activity Log for a
given service using the azure-monitor-query package (LogsQueryClient).  The
Activity Log is queried via Log Analytics using the AzureActivity table.

This is the change-correlation evidence source: it answers "what changed
before the alert fired?"

Config is loaded from config/integrations/azure_activity.yaml with an
optional environment overlay.  Placeholder values like ${AZURE_CLIENT_ID}
are resolved from environment variables at runtime.  The credential and
client are built once in __init__ and reused across calls.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from typing import Any

from azure.identity import ClientSecretCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from corvin.core.config_loader import get_env, load_config

logger = logging.getLogger(__name__)

_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand(value: str) -> str:
    """Expand ${VAR_NAME} placeholders using os.environ."""
    return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), str(value))


class AzureActivityAdapter:
    """Adapter for querying the Azure Activity Log (change correlation)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = (
            config
            if config is not None
            else load_config("integrations/azure_activity", get_env())
        )
        # Build the credential and client once so they are reused across calls.
        # Guard construction so that missing credentials in dev produce a warning
        # and a None client rather than raising at import time.
        self._client: LogsQueryClient | None = None
        try:
            credential = ClientSecretCredential(
                tenant_id=_expand(self._config.get("tenant_id", "")),
                client_id=_expand(self._config.get("client_id", "")),
                client_secret=_expand(self._config.get("client_secret", "")),
            )
            self._client = LogsQueryClient(credential)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AzureActivityAdapter: could not build client (will return empty results): %s", exc
            )
        self._workspace_id = _expand(self._config.get("workspace_id", ""))

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

        minutes = time_range_minutes or self._config.get("default_time_range_minutes", 60)
        max_events = self._config.get("max_events", 100)

        query = (
            f"AzureActivity\n"
            f"| where TimeGenerated >= ago({minutes}m)\n"
            f'| where ResourceGroup contains "{service_name}" or Resource contains "{service_name}"\n'
            f"| project TimeGenerated, OperationNameValue, ActivityStatusValue, "
            f"Caller, ResourceGroup, Resource, SubscriptionId, Properties\n"
            f"| order by TimeGenerated desc\n"
            f"| take {max_events}"
        )

        try:
            result = self._client.query_workspace(
                workspace_id=self._workspace_id,
                query=query,
                timespan=timedelta(minutes=minutes),
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
            log_table = result.tables[0]
            columns = [col.name for col in log_table.columns]
            return [dict(zip(columns, row)) for row in log_table.rows]
        except Exception as exc:
            logger.warning(
                "AzureActivityAdapter.get_recent_changes failed for service=%s: %s",
                service_name,
                exc,
            )
            return []

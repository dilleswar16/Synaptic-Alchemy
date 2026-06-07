"""
Log Analytics toolset.

Wraps LogAnalyticsAdapter and exposes one tool for the investigation engine LLM:
  - log_analytics_get_apim_logs — fetch APIM gateway logs from Log Analytics

Runtime connector resolution is DB-first via the application connector registry.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class LogAnalyticsToolset(Toolset):
    """Toolset for querying Azure Log Analytics (APIM evidence)."""

    name = "log_analytics"

    def __init__(self) -> None:
        self._adapter = LogAnalyticsAdapter()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "log_analytics_get_apim_logs",
                "description": (
                    "Fetch APIM gateway logs from Azure Log Analytics for a named service. "
                    "Use this to find API gateway errors, 5xx responses, latency spikes, "
                    "and backend connectivity issues routed through APIM."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "The API or backend service name to filter logs for.",
                        },
                        "environment": {
                            "type": "string",
                            "description": "Deployment environment to filter by (e.g. 'production', 'staging').",
                        },
                        "time_range_minutes": {
                            "type": "integer",
                            "description": "How many minutes back to retrieve logs. Default: 30.",
                        },
                    },
                    "required": ["service_name"],
                },
            }
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "log_analytics_get_apim_logs":
            return self._adapter.get_apim_logs(
                service_name=arguments["service_name"],
                environment=arguments.get("environment"),
                time_range_minutes=arguments.get("time_range_minutes"),
            )
        raise ValueError(f"LogAnalyticsToolset does not handle tool '{tool_name}'")

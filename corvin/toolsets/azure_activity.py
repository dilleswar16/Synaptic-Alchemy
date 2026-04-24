"""
Azure Activity Log toolset.

Wraps AzureActivityAdapter and exposes one tool for the investigation engine LLM:
  - azure_activity_get_recent_changes — fetch recent resource changes from the Activity Log

This is the change-correlation toolset: it answers "what changed before the alert?"

Config is loaded from config/integrations/azure_activity.yaml.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.azure_activity_adapter import AzureActivityAdapter
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class AzureActivityToolset(Toolset):
    """Toolset for querying the Azure Activity Log (change correlation)."""

    name = "azure_activity"

    def __init__(self) -> None:
        self._adapter = AzureActivityAdapter()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "azure_activity_get_recent_changes",
                "description": (
                    "Fetch recent Azure Activity Log events for a named service to identify "
                    "deployments, config changes, scale operations, or policy changes that "
                    "may have preceded the current incident."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "Resource name or tag filter to scope Activity Log events.",
                        },
                        "environment": {
                            "type": "string",
                            "description": "Deployment environment hint (e.g. 'production', 'staging').",
                        },
                        "time_range_minutes": {
                            "type": "integer",
                            "description": "How many minutes back to look for changes. Default: 60.",
                        },
                    },
                    "required": ["service_name"],
                },
            }
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "azure_activity_get_recent_changes":
            return self._adapter.get_recent_changes(
                service_name=arguments["service_name"],
                environment=arguments.get("environment"),
                time_range_minutes=arguments.get("time_range_minutes"),
            )
        raise ValueError(f"AzureActivityToolset does not handle tool '{tool_name}'")

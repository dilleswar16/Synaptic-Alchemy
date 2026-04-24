"""
Elastic toolset.

Wraps ElasticAdapter and exposes two tools for the investigation engine LLM:
  - elastic_get_logs     — fetch recent application logs for a service
  - elastic_get_metrics  — fetch recent metrics for a service

Config is loaded from config/integrations/elastic.yaml.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class ElasticToolset(Toolset):
    """Toolset for querying Elastic logs and metrics."""

    name = "elastic"

    def __init__(self) -> None:
        self._adapter = ElasticAdapter()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "elastic_get_logs",
                "description": (
                    "Fetch recent application logs from Elastic for a named service. "
                    "Use this to find error messages, stack traces, and log patterns."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "The service name to query logs for.",
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
            },
            {
                "name": "elastic_get_metrics",
                "description": (
                    "Fetch recent application or AKS metrics from Elastic for a named service. "
                    "Use this to check CPU, memory, JVM heap, request rates, and error rates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {
                            "type": "string",
                            "description": "The service name to query metrics for.",
                        },
                        "environment": {
                            "type": "string",
                            "description": "Deployment environment to filter by (e.g. 'production', 'staging').",
                        },
                        "time_range_minutes": {
                            "type": "integer",
                            "description": "How many minutes back to retrieve metrics. Default: 30.",
                        },
                    },
                    "required": ["service_name"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "elastic_get_logs":
            return self._adapter.get_logs(
                service_name=arguments["service_name"],
                environment=arguments.get("environment"),
                time_range_minutes=arguments.get("time_range_minutes"),
            )
        if tool_name == "elastic_get_metrics":
            return self._adapter.get_metrics(
                service_name=arguments["service_name"],
                environment=arguments.get("environment"),
                time_range_minutes=arguments.get("time_range_minutes"),
            )
        raise ValueError(f"ElasticToolset does not handle tool '{tool_name}'")

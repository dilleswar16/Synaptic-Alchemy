"""
Container Logs toolset.

Wraps ContainerLogsAdapter and exposes Kubernetes evidence tools for the
investigation engine LLM:
  - container_logs_get_pod_restarts        — Kubernetes pod restart trends
  - container_logs_get_oom_kill_events     — OOMKilled container events
  - container_logs_get_autoscaler_events   — HPA autoscaler decisions
  - container_logs_get_health_probe_failures — readiness/liveness probe failures
  - container_logs_get_resource_metrics    — CPU/memory usage with limits

Runtime connector resolution is DB-first via the application connector registry.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset

_COMMON_PARAMS = {
    "type": "object",
    "properties": {
        "service_name": {
            "type": "string",
            "description": "Kubernetes deployment or service name.",
        },
        "namespace": {
            "type": "string",
            "description": "Kubernetes namespace. Defaults to config default_namespace.",
        },
        "time_range_minutes": {
            "type": "integer",
            "description": "Lookback window in minutes. Defaults to 60.",
        },
    },
    "required": ["service_name"],
}


@register_toolset
class ContainerLogsToolset(Toolset):
    """Toolset for querying Kubernetes evidence via Log Analytics."""

    name = "container_logs"

    def __init__(self) -> None:
        self._adapter = ContainerLogsAdapter()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "container_logs_get_pod_restarts",
                "description": (
                    "Fetch Kubernetes pod restart counts and trends from KubePodInventory. "
                    "Use this to detect crash-looping or recurring container restarts."
                ),
                "parameters": _COMMON_PARAMS,
            },
            {
                "name": "container_logs_get_oom_kill_events",
                "description": (
                    "Fetch OOMKilled events from KubeEvents. "
                    "Use this to confirm memory exhaustion or container OOM kills."
                ),
                "parameters": _COMMON_PARAMS,
            },
            {
                "name": "container_logs_get_autoscaler_events",
                "description": (
                    "Fetch Horizontal Pod Autoscaler (HPA) events from KubeEvents. "
                    "Use this to detect scaling failures, thrashing, or metric computation errors."
                ),
                "parameters": _COMMON_PARAMS,
            },
            {
                "name": "container_logs_get_health_probe_failures",
                "description": (
                    "Fetch Kubernetes readiness and liveness probe failure events. "
                    "Use this to detect unhealthy pods that are being removed from service."
                ),
                "parameters": _COMMON_PARAMS,
            },
            {
                "name": "container_logs_get_resource_metrics",
                "description": (
                    "Fetch CPU and memory usage with limits from Perf (K8SContainer). "
                    "Use this to check if containers are approaching resource limits."
                ),
                "parameters": _COMMON_PARAMS,
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        svc = arguments["service_name"]
        ns = arguments.get("namespace")
        mins = arguments.get("time_range_minutes")

        dispatch = {
            "container_logs_get_pod_restarts": self._adapter.get_pod_restarts,
            "container_logs_get_oom_kill_events": self._adapter.get_oom_kill_events,
            "container_logs_get_autoscaler_events": self._adapter.get_autoscaler_events,
            "container_logs_get_health_probe_failures": self._adapter.get_health_probe_failures,
            "container_logs_get_resource_metrics": self._adapter.get_resource_metrics,
        }

        fn = dispatch.get(tool_name)
        if fn is None:
            raise ValueError(f"ContainerLogsToolset does not handle tool '{tool_name}'")
        return fn(service_name=svc, namespace=ns, time_range_minutes=mins)

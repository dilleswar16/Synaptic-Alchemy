"""
AKS toolset.

Wraps AKSAdapter and exposes one tool for the investigation engine LLM:
  - aks_get_pod_context — collect pod state, deployment info, and recent events

Config is loaded from config/integrations/aks.yaml.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.evidence.aks_adapter import AKSAdapter
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class AKSToolset(Toolset):
    """Toolset for collecting AKS workload context."""

    name = "aks"

    def __init__(self) -> None:
        self._adapter = AKSAdapter()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "aks_get_pod_context",
                "description": (
                    "Collect pod status, restart counts, resource pressure, recent events, "
                    "and deployment rollout state from AKS for a named service. "
                    "Use this to investigate CrashLoopBackOff, OOMKilled, and deployment failures."
                ),
                "parameters": {
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
                        "environment": {
                            "type": "string",
                            "description": "Target environment (used to resolve namespace or cluster context).",
                        },
                    },
                    "required": ["service_name"],
                },
            }
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "aks_get_pod_context":
            return self._adapter.get_pod_context(
                service_name=arguments["service_name"],
                namespace=arguments.get("namespace"),
                environment=arguments.get("environment"),
            )
        raise ValueError(f"AKSToolset does not handle tool '{tool_name}'")

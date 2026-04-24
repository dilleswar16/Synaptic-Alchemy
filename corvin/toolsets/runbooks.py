"""
Runbooks toolset.

Exposes runbook lookup to the investigation engine LLM.  Runbooks are matched
by keyword against the alert text using runbooks/catalog.json as the index.

  - runbooks_get_matching  — returns the content of all runbooks matching
                             the current alert description / rule name

Config is loaded from config/tools/knowledge.yaml (reuses the same knowledge
config for runbook paths).
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class RunbooksToolset(Toolset):
    """Toolset for fetching investigation runbooks matched by alert keyword."""

    name = "runbooks"

    def __init__(self) -> None:
        self._loader = KnowledgeLoader()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "runbooks_get_matching",
                "description": (
                    "Return the content of all registered runbooks whose keyword matches "
                    "the provided alert text.  Runbooks contain investigation steps, "
                    "common root causes, and fix patterns for known failure modes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "alert_text": {
                            "type": "string",
                            "description": (
                                "The alert rule name and description combined. "
                                "Used to match against runbook keywords."
                            ),
                        }
                    },
                    "required": ["alert_text"],
                },
            }
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "runbooks_get_matching":
            matched = self._loader.load_matching_runbooks(arguments["alert_text"])
            if not matched:
                return "No matching runbooks found for the provided alert text."
            return "\n\n---\n\n".join(matched)
        raise ValueError(f"RunbooksToolset does not handle tool '{tool_name}'")

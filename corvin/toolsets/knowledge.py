"""
Knowledge toolset.

Exposes the static site knowledge base and historical learnings to the
investigation engine LLM as a readable tool.

  - knowledge_get_site_facts  — returns the content of knowledge/site.md
  - knowledge_get_learnings   — returns combined content of knowledge/learnings/*.md

Config is loaded from config/tools/knowledge.yaml.
Enable/disable via config/tools/toolsets.yaml.
"""

from __future__ import annotations

from typing import Any

from corvin.core.knowledge_loader import KnowledgeLoader
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset


@register_toolset
class KnowledgeToolset(Toolset):
    """Toolset for reading the site knowledge base and learnings."""

    name = "knowledge"

    def __init__(self) -> None:
        self._loader = KnowledgeLoader()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "knowledge_get_site_facts",
                "description": (
                    "Return the Corvin site knowledge base: AKS cluster details, "
                    "Elastic index patterns, APIM instance name, monitored service list, "
                    "and other static infrastructure facts relevant to investigation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "knowledge_get_learnings",
                "description": (
                    "Return historical incident learnings recorded by Corvin operators. "
                    "Use this to check if a similar incident has been seen before and what "
                    "the root cause and fix were."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "knowledge_get_site_facts":
            return self._loader.load_site_knowledge()
        if tool_name == "knowledge_get_learnings":
            return self._loader.load_learnings()
        raise ValueError(f"KnowledgeToolset does not handle tool '{tool_name}'")

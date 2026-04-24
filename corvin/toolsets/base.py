"""
Toolset base class.

Every toolset in Corvin implements this interface.  A toolset bundles:
  - a list of tool *definitions* the LLM sees (get_tools)
  - the execution logic for those tools (execute)
  - an optional pre-check to determine whether the toolset is ready (check_prerequisites)

The investigation engine calls get_tools() on each enabled toolset to build
the LLM tool list, and routes execute() calls back to the correct toolset
when the LLM requests a tool invocation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Toolset(ABC):
    """Abstract base class for all Corvin toolsets."""

    # Each subclass must set a unique name. Used as the registry key and
    # as the prefix for all tool names the toolset exposes.
    name: str = ""

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """
        Return the list of tool definitions in OpenAI function-calling format.

        Each definition is a dict with:
          - "name": str
          - "description": str
          - "parameters": JSON Schema dict

        These definitions are passed directly to the LLM as the `tools` argument.
        """
        ...

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Execute a named tool with the given arguments.

        Args:
            tool_name:  Must match one of the names returned by get_tools().
            arguments:  Arguments extracted from the LLM tool call.

        Returns:
            Tool result.  Should be JSON-serialisable so it can be fed back
            to the LLM as a tool result message.

        Raises:
            NotImplementedError: If the toolset is not yet wired to a real client.
            ValueError:          If tool_name is not recognised by this toolset.
        """
        ...

    def check_prerequisites(self) -> bool:
        """
        Return True if all prerequisites for this toolset are satisfied.

        Override to add connectivity checks, required config key checks, etc.
        The registry skips toolsets whose prerequisites fail so the engine
        always receives only ready toolsets.
        """
        return True

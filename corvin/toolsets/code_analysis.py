"""
Code analysis toolset.

Exposes source code reading capabilities to the investigation engine LLM.
When the AI detects a code-related issue from logs/stack traces (null pointers,
missing DB entries, unhandled exceptions, type errors), it can:

  - code_search_files    — search for a class/function/variable name in the repo
  - code_read_file       — read a specific source file by path
  - code_list_directory  — browse the repository structure

The toolset is only active when the service under investigation has git config
registered in its Application onboarding.
"""
from __future__ import annotations

import logging
from typing import Any

from corvin.connectors.git_repo import GitRepoConnector, get_connector_for_service, _MAX_CODE_CONTEXT_CHARS
from corvin.toolsets.base import Toolset
from corvin.toolsets.registry import register_toolset

_log = logging.getLogger(__name__)


@register_toolset
class CodeAnalysisToolset(Toolset):
    """Toolset for reading application source code during investigation."""

    name = "code_analysis"

    def __init__(self) -> None:
        # Connector is lazily resolved per-investigation via set_service_context
        self._connector: GitRepoConnector | None = None
        self._service_name: str | None = None

    def set_service_context(self, service_name: str) -> None:
        """Called by the engine before tool execution to bind to the right repo."""
        self._service_name = service_name
        self._connector = get_connector_for_service(service_name)

    def check_prerequisites(self) -> bool:
        # Always register — availability is per-investigation (checked at runtime)
        return True

    def is_available(self) -> bool:
        """Return True if the current service has git config."""
        return self._connector is not None

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "code_search_files",
                "description": (
                    "Search the application source code for a class, function, variable, "
                    "or error pattern. Use this when you see a stack trace, NullReferenceException, "
                    "KeyError, or similar code-related error in the logs. Returns matching file "
                    "paths and snippets."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query — class name, function name, error message, or variable.",
                        },
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional file extensions to filter (e.g. ['.cs', '.py', '.ts']).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "code_read_file",
                "description": (
                    "Read the content of a specific source file from the application repository. "
                    "Use this after code_search_files identifies a relevant file, or when a stack "
                    "trace points to a specific file path. Returns the file content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to repo root (e.g. 'src/Services/OrderService.cs').",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "code_list_directory",
                "description": (
                    "List files and folders in a directory of the application repository. "
                    "Use this to explore the project structure when you need to locate "
                    "relevant source files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path relative to repo root (e.g. 'src/Services/'). Use '/' for root.",
                        },
                    },
                    "required": ["path"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._connector:
            return {
                "error": "No git repository configured for this service. "
                "Configure git access in the Applications onboarding panel."
            }

        if tool_name == "code_search_files":
            query = arguments["query"]
            extensions = arguments.get("extensions")
            results = self._connector.search_files(query, extensions)
            if not results:
                return {"message": f"No files found matching '{query}'.", "results": []}
            return {"results": results}

        elif tool_name == "code_read_file":
            path = arguments["path"]
            content = self._connector.get_file(path)
            if content is None:
                return {"error": f"File not found: {path}"}
            # Truncate if too large
            if len(content) > _MAX_CODE_CONTEXT_CHARS:
                content = content[:_MAX_CODE_CONTEXT_CHARS] + "\n\n[... truncated — file too large ...]"
            return {"path": path, "content": content}

        elif tool_name == "code_list_directory":
            path = arguments.get("path", "/")
            items = self._connector.list_directory(path)
            if not items:
                return {"message": f"Directory empty or not found: {path}", "items": []}
            return {"path": path, "items": items}

        raise ValueError(f"CodeAnalysisToolset does not handle tool '{tool_name}'")

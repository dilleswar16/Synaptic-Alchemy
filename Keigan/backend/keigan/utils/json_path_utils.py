"""Minimal JSONPath reader for alert payload field mapping (``$.data.essentials.alertId``, ``$.labels[0].name``)."""

from __future__ import annotations

import re
from typing import Any

_PATH_TOKEN_PATTERN = re.compile(r"\.([A-Za-z0-9_@$-]+)|\[(\d+)\]|\['([^']+)'\]|\[\"([^\"]+)\"\]")


def read_json_path(document: Any, json_path: str | None, default: Any = None) -> Any:
    if not json_path:
        return default
    normalized_path = json_path.strip()
    if normalized_path.startswith("$"):
        normalized_path = normalized_path[1:]
    if normalized_path and not normalized_path.startswith((".", "[")):
        normalized_path = "." + normalized_path
    current_value = document
    for property_name, list_index, quoted_name, double_quoted_name in _PATH_TOKEN_PATTERN.findall(normalized_path):
        if current_value is None:
            return default
        if list_index:
            if not isinstance(current_value, list) or int(list_index) >= len(current_value):
                return default
            current_value = current_value[int(list_index)]
        else:
            key_name = property_name or quoted_name or double_quoted_name
            if not isinstance(current_value, dict) or key_name not in current_value:
                return default
            current_value = current_value[key_name]
    return current_value


def list_json_paths(document: Any, prefix: str = "$", maximum_depth: int = 6) -> list[str]:
    """All leaf paths in a sample payload — used to suggest field mappings for generic alert sources."""
    if maximum_depth <= 0:
        return []
    discovered_paths: list[str] = []
    if isinstance(document, dict):
        for key_name, nested_value in document.items():
            child_path = f"{prefix}.{key_name}" if re.fullmatch(r"[A-Za-z0-9_@$-]+", str(key_name)) else f"{prefix}['{key_name}']"
            discovered_paths.extend(list_json_paths(nested_value, child_path, maximum_depth - 1) or [child_path])
    elif isinstance(document, list) and document:
        discovered_paths.extend(list_json_paths(document[0], f"{prefix}[0]", maximum_depth - 1) or [f"{prefix}[0]"])
    return discovered_paths

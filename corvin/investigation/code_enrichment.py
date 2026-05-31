"""
Code enrichment for the investigation pipeline.

After evidence is collected, this module scans logs/errors for stack traces
and file references, then auto-fetches the relevant source code from the
application's Git repository (if configured).

This gives the RCA generator code context alongside operational evidence
so it can identify code-level root causes (null refs, unhandled exceptions,
type errors, missing validations, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from corvin.core.contracts import EvidenceBundle

_log = logging.getLogger(__name__)

# Patterns for extracting file references from stack traces
# .NET: "at Namespace.Class.Method() in /path/File.cs:line 42"
_DOTNET_PATTERN = re.compile(r"in\s+([^\s:]+\.cs):line\s+(\d+)", re.IGNORECASE)
# Python: 'File "/path/file.py", line 42'
_PYTHON_PATTERN = re.compile(r'File\s+"([^"]+\.py)",\s+line\s+(\d+)', re.IGNORECASE)
# Java/Kotlin: "at com.example.Class.method(File.java:42)"
_JAVA_PATTERN = re.compile(r"\(([A-Za-z0-9_]+\.(?:java|kt)):(\d+)\)", re.IGNORECASE)
# TypeScript/JavaScript: "at Object.<anonymous> (/path/file.ts:42:5)"
_TS_PATTERN = re.compile(r"\(([^\s:]+\.(?:ts|js|tsx|jsx)):(\d+):\d+\)", re.IGNORECASE)
# Generic: "ClassName.MethodName" patterns from .NET exceptions
_DOTNET_CLASS_PATTERN = re.compile(
    r"(?:at|in)\s+([\w.]+\.[\w]+)\s*\(", re.IGNORECASE
)

_MAX_CODE_ITEMS = 5  # Max source files to fetch per investigation


def _extract_file_references(text: str) -> list[dict[str, Any]]:
    """Extract file path + line number references from a stack trace string."""
    refs: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for pattern in (_DOTNET_PATTERN, _PYTHON_PATTERN, _JAVA_PATTERN, _TS_PATTERN):
        for match in pattern.finditer(text):
            path = match.group(1)
            line = int(match.group(2))
            if path not in seen_paths:
                refs.append({"path": path, "line": line})
                seen_paths.add(path)

    return refs


def _extract_class_names(text: str) -> list[str]:
    """Extract class/method references that could be searched in the repo."""
    names: list[str] = []
    seen: set[str] = set()
    for match in _DOTNET_CLASS_PATTERN.finditer(text):
        full = match.group(1)
        # Take the last segment (ClassName.Method → search for ClassName)
        parts = full.rsplit(".", 1)
        class_name = parts[0].rsplit(".", 1)[-1] if len(parts) > 1 else parts[0]
        if class_name not in seen and len(class_name) > 3:
            names.append(class_name)
            seen.add(class_name)
    return names


def _scan_evidence_for_traces(evidence: EvidenceBundle) -> str:
    """Collect all text from evidence that might contain stack traces."""
    texts: list[str] = []

    # Scan elastic logs for exception/stack trace fields
    for log in evidence.elastic_logs[:50]:  # cap to avoid slow scans
        msg = log.get("message", "") or log.get("exception", "") or log.get("stackTrace", "")
        if msg:
            texts.append(str(msg))

    # Scan AKS context for container logs with errors
    if evidence.aks_context:
        for key in ("container_logs", "events", "errors"):
            val = evidence.aks_context.get(key)
            if isinstance(val, list):
                for item in val[:20]:
                    texts.append(str(item.get("message", "") if isinstance(item, dict) else item))
            elif isinstance(val, str):
                texts.append(val)

    return "\n".join(texts)


def enrich_with_code_context(service_name: str, evidence: EvidenceBundle) -> None:
    """
    Scan evidence for stack traces and fetch relevant source code.

    Modifies evidence.code_context in-place with fetched source files.
    Safe to call even if no git config exists — will silently skip.
    """
    from corvin.connectors.git_repo import get_connector_for_service

    connector = get_connector_for_service(service_name)
    if connector is None:
        return  # No git config for this service — skip silently

    all_text = _scan_evidence_for_traces(evidence)
    if not all_text.strip():
        return

    # Extract file references from stack traces
    file_refs = _extract_file_references(all_text)
    code_items: list[dict[str, Any]] = []

    # Try to fetch each referenced file
    for ref in file_refs[:_MAX_CODE_ITEMS]:
        try:
            content = connector.get_file(ref["path"])
            if content:
                code_items.append({
                    "path": ref["path"],
                    "line": ref["line"],
                    "content": content,
                    "source": "stack_trace_reference",
                })
        except Exception as exc:
            _log.debug("Failed to fetch %s: %s", ref["path"], exc)

    # If we didn't find files by path, try searching by class name
    if not code_items:
        class_names = _extract_class_names(all_text)
        for name in class_names[:3]:
            try:
                results = connector.search_files(name)
                for result in results[:2]:
                    code_items.append({
                        "path": result["path"],
                        "snippet": result.get("snippet", ""),
                        "source": "class_name_search",
                        "search_query": name,
                    })
                    if len(code_items) >= _MAX_CODE_ITEMS:
                        break
            except Exception as exc:
                _log.debug("Code search for %r failed: %s", name, exc)
            if len(code_items) >= _MAX_CODE_ITEMS:
                break

    if code_items:
        evidence.code_context = code_items
        _log.info(
            "Code enrichment: fetched %d source items for service %s",
            len(code_items),
            service_name,
        )

"""
Knowledge loader for the Corvin investigation engine.

Responsible for:
  1. Loading the static site knowledge base (knowledge/site.md).
  2. Matching an alert description/rule name against runbook keywords and
     loading matching runbook content (knowledge/runbooks/).
  3. Loading learnings files from knowledge/learnings/*.md.

Config is read from config/tools/knowledge.yaml.
Paths in the config are relative to the project root.

Folder structure:
    knowledge/
        site.md          ← static infra facts injected into every investigation prompt
        runbooks/        ← per-alert investigation workflows + catalog.json keyword registry
        learnings/       ← patterns and gotchas discovered from real incidents
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from corvin.core.config_loader import get_env, load_config

# Project root is three levels up from this file:
# corvin/core/knowledge_loader.py -> corvin/ -> project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _read_file(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars is not None:
        text = text[:max_chars]
    return text


class KnowledgeLoader:
    """Loads context files for injection into the investigation engine prompt."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("tools/knowledge", get_env())

    def _resolve(self, key: str) -> Path:
        return _PROJECT_ROOT / self._config.get(key, "")

    # ── Site knowledge ────────────────────────────────────────────────────────

    def load_site_knowledge(self) -> str:
        """Return the content of knowledge/site.md."""
        return _read_file(self._resolve("knowledge_path"))

    # ── Runbooks ──────────────────────────────────────────────────────────────

    def _load_runbook_catalog(self) -> list[dict[str, Any]]:
        """Return normalized catalog entries from knowledge/runbooks/catalog.json."""
        catalog_path = self._resolve("runbooks_path") / "catalog.json"
        if not catalog_path.exists():
            return []

        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, dict):
            entries = payload.get("entries", [])
        else:
            entries = []

        return [entry for entry in entries if isinstance(entry, dict)]

    def _get_match_patterns(self, entry: dict[str, Any]) -> list[str]:
        """Return unique lowercase patterns supported by a catalog entry."""
        candidates: list[str] = []

        for key in ("keywords", "match_patterns"):
            value = entry.get(key)
            if isinstance(value, list):
                candidates.extend(str(item) for item in value if isinstance(item, str))

        keyword = entry.get("keyword")
        if isinstance(keyword, str):
            candidates.append(keyword)

        patterns: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalised = candidate.strip().lower()
            if not normalised or normalised in seen:
                continue
            seen.add(normalised)
            patterns.append(normalised)

        return patterns

    def _resolve_runbook_file(self, entry: dict[str, Any], runbooks_dir: Path) -> Path | None:
        """Resolve a catalog entry's file path against current repo layout."""
        file_value = entry.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            return None

        file_path = Path(file_value)
        if file_path.is_absolute():
            return file_path

        knowledge_root = self._resolve("knowledge_path").parent
        candidates = [
            knowledge_root / file_path,
            runbooks_dir / file_path,
            runbooks_dir / file_path.name,
            _PROJECT_ROOT / file_path,
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def load_matching_runbooks(self, alert_text: str) -> list[str]:
        """
        Return the content of all runbooks whose catalog keywords appear in
        `alert_text` (case-insensitive).

        Args:
            alert_text: Combined alert rule name + description to match against.

        Returns:
            List of runbook content strings (one per matching runbook).
        """
        runbooks_dir = self._resolve("runbooks_path")
        max_chars = self._config.get("runbook_max_chars", 3000)

        if not runbooks_dir.is_dir():
            return []

        matched: list[str] = []
        normalised = alert_text.lower()
        seen_paths: set[Path] = set()

        for entry in self._load_runbook_catalog():
            patterns = self._get_match_patterns(entry)
            if not patterns or not any(pattern in normalised for pattern in patterns):
                continue

            runbook_path = self._resolve_runbook_file(entry, runbooks_dir)
            if runbook_path is None or runbook_path in seen_paths:
                continue

            content = _read_file(runbook_path, max_chars)
            if content:
                matched.append(content)
                seen_paths.add(runbook_path)

        return matched

    # ── Learnings ─────────────────────────────────────────────────────────────

    def load_learnings(self) -> str:
        """Return combined content of all .md files in knowledge/learnings/."""
        learnings_dir = self._resolve("learnings_path")
        max_chars = self._config.get("learnings_max_chars", 4000)

        if not learnings_dir.is_dir():
            return ""

        parts: list[str] = []
        for md_file in sorted(learnings_dir.glob("*.md")):
            content = _read_file(md_file)
            if content:
                parts.append(content)

        combined = "\n\n---\n\n".join(parts)
        return combined[:max_chars]

    # ── Write-back: learnings + runbook steps ─────────────────────────────────

    def append_learning(self, investigation_id: str, content: str) -> Path:
        """Write a learning entry to knowledge/learnings/<investigation_id>.md.

        Creates the file if it does not exist; overwrites if it does.
        Returns the path written.
        """
        learnings_dir = self._resolve("learnings_path")
        learnings_dir.mkdir(parents=True, exist_ok=True)
        path = learnings_dir / f"{investigation_id}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def append_runbook_step(self, service_name: str, step_markdown: str) -> Path:
        """Append a resolution step to knowledge/runbooks/<service_name>.md.

        Creates the runbook file if it does not exist. Also ensures a catalog
        entry exists for the service so the runbook is matched in future prompts.
        Returns the path written.
        """
        runbooks_dir = self._resolve("runbooks_path")
        runbooks_dir.mkdir(parents=True, exist_ok=True)

        runbook_path = runbooks_dir / f"{service_name}.md"
        existing = _read_file(runbook_path)

        separator = "\n\n---\n\n" if existing.strip() else ""
        runbook_path.write_text(existing + separator + step_markdown, encoding="utf-8")

        self._ensure_catalog_entry(service_name, runbooks_dir)
        return runbook_path

    def _ensure_catalog_entry(self, service_name: str, runbooks_dir: Path) -> None:
        """Add a catalog.json entry for service_name if one does not exist."""
        catalog_path = runbooks_dir / "catalog.json"
        entries: list[dict] = []
        if catalog_path.exists():
            try:
                payload = json.loads(catalog_path.read_text(encoding="utf-8"))
                entries = payload if isinstance(payload, list) else payload.get("entries", [])
            except (json.JSONDecodeError, AttributeError):
                entries = []

        if any(e.get("keyword") == service_name for e in entries):
            return  # already registered

        entries.append({
            "keyword": service_name,
            "title": f"{service_name.title()} Runbook",
            "file": f"runbooks/{service_name}.md",
            "match_patterns": [service_name],
        })
        catalog_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


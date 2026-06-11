"""Prompt registry — loads versioned LLM prompts from config/prompts/.

Prompts are stored as YAML files following the naming convention::

    config/prompts/<id>.v<version>.yaml

A deployment-specific override drops into::

    config/prompts/overrides/<id>.yaml

The registry resolves in priority order:
  1. Override file (if present)
  2. Version specified in ``get()`` call
  3. Version declared in ``config/models/llm.yaml`` → ``prompt_versions.<id>``
  4. Default version "1"

Usage::

    registry = get_prompt_registry()
    system_prompt = registry.get("rca_system")
    hypothesis_prompt = registry.get("hypothesis_generation", count=3)

CLI validation::

    python -m corvin.core.prompt_registry --validate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path("config/prompts")
_OVERRIDES_DIR = _PROMPTS_DIR / "overrides"

# Populated on first call to get_prompt_registry(); reset in tests via _reset().
_registry: "PromptRegistry | None" = None


class PromptNotFoundError(KeyError):
    pass


class PromptRegistry:
    """Load and render versioned prompts from the filesystem."""

    def __init__(
        self,
        prompts_dir: Path = _PROMPTS_DIR,
        overrides_dir: Path = _OVERRIDES_DIR,
        version_config: dict[str, str] | None = None,
    ) -> None:
        self._prompts: dict[str, dict[str, Any]] = {}
        self._overrides: dict[str, dict[str, Any]] = {}
        self._version_config: dict[str, str] = version_config or {}
        self._load(prompts_dir, overrides_dir)

    def _load(self, prompts_dir: Path, overrides_dir: Path) -> None:
        if not prompts_dir.exists():
            return
        for path in sorted(prompts_dir.glob("*.v*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "id" not in data or "version" not in data:
                    continue
                key = f"{data['id']}.v{data['version']}"
                self._prompts[key] = data
            except Exception:
                pass

        if overrides_dir.exists():
            for path in overrides_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict) or "id" not in data:
                        continue
                    self._overrides[data["id"]] = data
                except Exception:
                    pass

    def get(self, prompt_id: str, version: str | None = None, **kwargs: Any) -> str:
        """Return the rendered prompt string for ``prompt_id``.

        Override takes precedence. Falls back through version → configured
        default → "1". Raises ``PromptNotFoundError`` if nothing matches.
        """
        if prompt_id in self._overrides:
            return self._render(self._overrides[prompt_id]["content"], kwargs)

        resolved = version or self._version_config.get(prompt_id, "1")
        key = f"{prompt_id}.v{resolved}"
        if key not in self._prompts:
            raise PromptNotFoundError(
                f"Prompt '{prompt_id}' version '{resolved}' not found in {_PROMPTS_DIR}"
            )
        return self._render(self._prompts[key]["content"], kwargs)

    def list_prompts(self) -> list[dict[str, Any]]:
        """Return metadata for every loaded prompt (excluding content)."""
        result = []
        for data in self._prompts.values():
            result.append({k: v for k, v in data.items() if k != "content"})
        for data in self._overrides.values():
            entry = {k: v for k, v in data.items() if k != "content"}
            entry["override"] = True
            result.append(entry)
        return sorted(result, key=lambda d: (d.get("id", ""), d.get("version", "")))

    @staticmethod
    def _render(template: str, variables: dict[str, Any]) -> str:
        if not variables:
            return template
        try:
            return template.format_map(variables)
        except (KeyError, ValueError):
            return template

    def validate(self) -> list[str]:
        """Return a list of validation error strings (empty = OK)."""
        errors: list[str] = []
        for key, data in self._prompts.items():
            if not data.get("content"):
                errors.append(f"{key}: empty 'content' field")
            if data.get("deprecated") and data["id"] in self._version_config:
                errors.append(
                    f"{key}: deprecated prompt is active in llm.yaml prompt_versions"
                )
        for pid, data in self._overrides.items():
            if not data.get("content"):
                errors.append(f"override/{pid}: empty 'content' field")
        return errors


def get_prompt_registry(
    prompts_dir: Path = _PROMPTS_DIR,
    overrides_dir: Path = _OVERRIDES_DIR,
) -> PromptRegistry:
    """Return the process-level singleton PromptRegistry, creating it on first call."""
    global _registry
    if _registry is None:
        version_config = _load_version_config()
        _registry = PromptRegistry(prompts_dir, overrides_dir, version_config)
    return _registry


def _reset_registry() -> None:
    """Reset the singleton — for tests only."""
    global _registry
    _registry = None


def _load_version_config() -> dict[str, str]:
    llm_path = Path("config/models/llm.yaml")
    if not llm_path.exists():
        return {}
    try:
        data = yaml.safe_load(llm_path.read_text(encoding="utf-8"))
        versions = data.get("prompt_versions", {}) if isinstance(data, dict) else {}
        return {k: str(v) for k, v in versions.items()}
    except Exception:
        return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the Corvin prompt registry")
    parser.parse_args()

    registry = get_prompt_registry()
    errors = registry.validate()
    prompts = registry.list_prompts()

    print(f"Loaded {len(prompts)} prompts from {_PROMPTS_DIR}")
    for p in prompts:
        override_tag = " [OVERRIDE]" if p.get("override") else ""
        deprecated_tag = " [DEPRECATED]" if p.get("deprecated") else ""
        print(f"  {p.get('id')}.v{p.get('version', '?')}{override_tag}{deprecated_tag} — {p.get('description', '')}")

    if errors:
        print(f"\n{len(errors)} validation error(s):")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print("\nAll prompts valid.")

"""
Configuration loader for Corvin.

Loads YAML config files from the config/ directory by concern path,
then applies an optional environment overlay from config/environments/.

Usage:
    from corvin.core.config_loader import load_config, get_env

    elastic_cfg = load_config("integrations/elastic")
    llm_cfg = load_config("models/llm", env="local")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root and config/ directory, resolved relative to this file's location.
# corvin/core/ -> corvin/ -> project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"

# Load repo-local .env for normal app runtime. Shell-provided environment
# variables still win because override=False.
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _expand(value: Any) -> Any:
    """Recursively expand ${VAR_NAME} placeholders using os.environ."""
    if isinstance(value, str):
        import re
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(item) for item in value]
    return value


def get_env() -> str:
    """Return the active environment name from CORVIN_ENV (default: local)."""
    return os.environ.get("CORVIN_ENV", "local")


def load_config(concern: str, env: str | None = None) -> dict[str, Any]:
    """
    Load configuration for a given concern with an optional environment overlay.

    Args:
        concern: Slash-separated path inside config/, without .yaml extension.
                 Examples: "integrations/elastic", "models/llm", "policies/investigation"
        env:     Environment name for overlay lookup.
                 If None, uses get_env(). Pass "" to skip overlay entirely.

    Returns:
        Merged dict: base config values overridden by environment-level keys.
    """
    base = _load_yaml(_CONFIG_DIR / f"{concern}.yaml")

    resolved_env = env if env is not None else get_env()
    if resolved_env:
        overlay_path = _CONFIG_DIR / "environments" / f"{resolved_env}.yaml"
        overlay = _load_yaml(overlay_path)
        concern_key = concern.split("/")[-1]
        env_overrides = overlay.get(concern_key, {})
        if isinstance(env_overrides, dict):
            base = {**base, **env_overrides}

    return _expand(base)

"""
Toolset registry.

Provides:
  - register_toolset decorator  — registers a Toolset subclass by its name
  - get_registered_toolsets     — returns all registered toolset classes
  - get_enabled_toolsets        — returns instantiated toolsets that are enabled in
                                  config/tools/toolsets.yaml and pass prerequisites

Usage:
    from corvin.toolsets.registry import get_enabled_toolsets
    from corvin.core.config_loader import load_config, get_env

    toolsets = get_enabled_toolsets(load_config("tools/toolsets", get_env()))

All toolset modules must be imported before calling get_enabled_toolsets,
otherwise they will not be registered.  The recommended place to do this is
in the investigation engine module.
"""

from __future__ import annotations

from typing import Any

from corvin.toolsets.base import Toolset

# name -> Toolset subclass
_REGISTRY: dict[str, type[Toolset]] = {}


def register_toolset(cls: type[Toolset]) -> type[Toolset]:
    """Class decorator that registers a Toolset subclass in the global registry."""
    if not cls.name:
        raise ValueError(f"Toolset subclass {cls.__name__} must define a non-empty name.")
    _REGISTRY[cls.name] = cls
    return cls


def get_registered_toolsets() -> dict[str, type[Toolset]]:
    """Return a copy of the registry (name -> class)."""
    return dict(_REGISTRY)


def merge_toolset_profile(global_config: dict[str, Any], app_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Merge an application-level toolset_profile into the global toolsets config.

    app_profile schema: {"enabled": ["log_analytics", "aks"], "disabled": ["elastic"]}
    Application values take precedence over global defaults.
    """
    if not app_profile:
        return global_config

    merged = dict(global_config)
    toolset_flags: dict[str, Any] = dict(merged.get("toolsets", {}))

    for name in app_profile.get("enabled", []):
        entry = dict(toolset_flags.get(name, {}))
        entry["enabled"] = True
        toolset_flags[name] = entry

    for name in app_profile.get("disabled", []):
        entry = dict(toolset_flags.get(name, {}))
        entry["enabled"] = False
        toolset_flags[name] = entry

    merged["toolsets"] = toolset_flags
    return merged


def get_enabled_toolsets(config: dict[str, Any]) -> list[Toolset]:
    """
    Instantiate and return all toolsets that are:
      1. registered
      2. enabled in the provided config (default: enabled)
      3. passing check_prerequisites()

    Args:
        config: Merged config dict from config/tools/toolsets.yaml (with env overlay).

    Returns:
        List of ready Toolset instances in registration order.
    """
    enabled: list[Toolset] = []
    toolset_flags: dict[str, Any] = config.get("toolsets", {})

    for name, cls in _REGISTRY.items():
        toolset_entry = toolset_flags.get(name, {})
        # Default to enabled=True when not explicitly configured.
        if not toolset_entry.get("enabled", True):
            continue
        instance = cls()
        if instance.check_prerequisites():
            enabled.append(instance)

    return enabled

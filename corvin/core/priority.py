"""Priority classification for investigation requests.

Resolution order (first match wins):
  1. Explicit priority in the trigger payload (P1/P2/P3 literal, or severity keyword).
  2. Per-application environment config from ApplicationRow.environment_config_json in DB.
  3. System-wide defaults from config/policies/environments.yaml.
  4. Hardcoded fallback: P3 (safe default for unknown environments).

Lookback minutes follow the same resolution order.

Usage (from trigger adapters or API routes, AFTER creating the request):

    from corvin.core.priority import classify_priority

    priority, lookback = classify_priority(
        service_name=request.service_name,
        environment=request.environment,
        trigger_source=request.trigger_source,
        raw_payload=request.raw_payload,
    )
    request.incident_priority = priority
    request.lookback_minutes = lookback
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)

# Sentinel returned when payload contains no priority hints.
_NO_PRIORITY: str | None = None

# Hardcoded safe fallback — used only when config AND DB both fail to resolve.
_FALLBACK_PRIORITY = "P3"
_FALLBACK_LOOKBACK = 60


@lru_cache(maxsize=1)
def _load_env_config() -> dict[str, Any]:
    """Load and cache the environments policy config. Cache is per-process."""
    try:
        return load_config("policies/environments", get_env())
    except Exception:
        _log.warning("priority: could not load config/policies/environments.yaml — using hardcoded fallback")
        return {}


def _priority_from_payload(raw_payload: dict[str, Any]) -> str | None:
    """Extract an explicit priority hint from heterogeneous trigger payloads."""
    direct = str(raw_payload.get("incident_priority") or raw_payload.get("priority") or "").upper().strip()
    if direct in {"P1", "P2", "P3"}:
        return direct

    severity_raw = raw_payload.get("severity")
    if severity_raw is None and isinstance(raw_payload.get("essentials"), dict):
        severity_raw = raw_payload["essentials"].get("severity")
    severity = str(severity_raw or "").lower().strip()
    if severity in {"sev0", "sev1", "critical", "high"}:
        return "P1"
    if severity in {"sev2", "medium", "warning"}:
        return "P2"
    if severity in {"sev3", "sev4", "low", "info", "informational"}:
        return "P3"
    return _NO_PRIORITY


def _lookup_from_env_list(
    env_list: list[dict[str, Any]],
    environment: str,
) -> tuple[str | None, int | None]:
    """Search a list of env dicts for a match. Returns (priority_tier, lookback_minutes)."""
    env_lower = environment.lower().strip()
    for entry in env_list:
        if str(entry.get("name", "")).lower().strip() == env_lower:
            return entry.get("priority_tier"), entry.get("lookback_minutes")
    return None, None


def _from_db(service_name: str, environment: str) -> tuple[str | None, int | None]:
    """Query ApplicationRow.environment_config_json for a per-app env mapping."""
    try:
        from sqlalchemy import or_
        from corvin.storage.db import get_session
        from corvin.storage.models import ApplicationServiceRow, ApplicationRow

        with get_session() as session:
            svc = session.query(ApplicationServiceRow).filter(
                or_(
                    ApplicationServiceRow.service_name == service_name,
                    ApplicationServiceRow.k8s_app_label == service_name,
                )
            ).first()
            if svc is None:
                return None, None

            app: ApplicationRow | None = session.get(ApplicationRow, svc.application_id)
            if app is None or not app.environment_config_json:
                return None, None

            env_list = app.environment_config_json.get("environments", [])
            return _lookup_from_env_list(env_list, environment)
    except Exception as exc:
        _log.debug("priority: DB lookup failed for service=%s env=%s: %s", service_name, environment, exc)
        return None, None


def _from_global_config(environment: str) -> tuple[str, int]:
    """Resolve priority and lookback from the system-wide environments.yaml."""
    cfg = _load_env_config()
    env_list = cfg.get("environments", [])
    priority, lookback = _lookup_from_env_list(env_list, environment)
    return (
        priority or cfg.get("default_priority_tier", _FALLBACK_PRIORITY),
        lookback or cfg.get("default_lookback_minutes", _FALLBACK_LOOKBACK),
    )


def classify_priority(
    service_name: str,
    environment: str,
    trigger_source: str,
    raw_payload: dict[str, Any],
) -> tuple[str, int]:
    """Return (incident_priority, lookback_minutes) for an investigation request.

    Resolution order:
      1. Explicit hint in the trigger payload.
      2. Per-application DB config (ApplicationRow.environment_config_json).
      3. System-wide config/policies/environments.yaml.
      4. Hardcoded fallback: P3, 60 minutes.
    """
    # 1. Payload-explicit priority takes precedence.
    payload_priority = _priority_from_payload(raw_payload)
    if payload_priority is not None:
        _, lookback = _from_db(service_name, environment)
        if lookback is None:
            _, lookback = _from_global_config(environment)
        return payload_priority, lookback or _FALLBACK_LOOKBACK

    # 2. Per-application DB override.
    db_priority, db_lookback = _from_db(service_name, environment)
    if db_priority is not None:
        return db_priority, db_lookback or _FALLBACK_LOOKBACK

    # 3. System-wide config.
    return _from_global_config(environment)

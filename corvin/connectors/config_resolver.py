"""DB-first connector configuration resolution for legacy evidence adapters."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_

from corvin.storage.db import get_session
from corvin.storage.models import ApplicationServiceRow, LogSourceRow, OutboundConnectorRow

_log = logging.getLogger(__name__)

ROLE_APIM_LOGS = "apim_logs"
ROLE_CONTAINER_INSIGHTS = "container_insights"
ROLE_AZURE_ACTIVITY = "azure_activity"


def infer_connector_role(source_type: str, config_json: dict[str, Any] | None, display_name: str = "") -> str | None:
    """Infer the connector role from config shape when the role is not explicit."""
    cfg = config_json or {}
    if source_type != "azure_monitor":
        return None

    explicit = str(cfg.get("connector_role", "")).strip()
    if explicit:
        return explicit

    if "apim_table" in cfg:
        return ROLE_APIM_LOGS

    if "activity_table" in cfg or "max_events" in cfg:
        return ROLE_AZURE_ACTIVITY

    container_keys = {"default_namespace", "cluster_name", "max_log_rows"}
    if any(key in cfg for key in container_keys):
        return ROLE_CONTAINER_INSIGHTS

    name = display_name.lower()
    if "container" in name or "insights" in name:
        return ROLE_CONTAINER_INSIGHTS
    if "activity" in name:
        return ROLE_AZURE_ACTIVITY
    if "apim" in name or "log analytics" in name:
        return ROLE_APIM_LOGS
    return None


def resolve_log_source_config(
    service_name: str,
    *,
    source_type: str,
    role: str | None,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Resolve config for a service from DB connector rows, falling back to YAML config.

    The DB row is the source of truth when a matching application service and
    log source connector exist. The fallback config remains in place so legacy
    environments continue to work until they are fully onboarded in the app UI.
    """
    try:
        row = _find_matching_log_source(service_name=service_name, source_type=source_type, role=role)
        if row is None:
            return dict(fallback)
        cfg = dict(fallback)
        cfg.update(row.config_json or {})
        if role and not cfg.get("connector_role"):
            cfg["connector_role"] = role
        return cfg
    except Exception as exc:  # noqa: BLE001
        _log.warning("Connector config resolution failed for service=%s type=%s role=%s: %s", service_name, source_type, role, exc)
        return dict(fallback)


def _find_matching_log_source(service_name: str, source_type: str, role: str | None) -> LogSourceRow | None:
    with get_session() as session:
        svc_rows = session.query(ApplicationServiceRow).filter(
            or_(
                ApplicationServiceRow.service_name == service_name,
                ApplicationServiceRow.k8s_app_label == service_name,
            )
        ).all()
        if not svc_rows:
            return None

        for svc in svc_rows:
            rows = session.query(LogSourceRow).filter(
                LogSourceRow.application_id == svc.application_id,
                LogSourceRow.source_type == source_type,
                LogSourceRow.is_active == True,  # noqa: E712
            ).all()
            if not rows:
                continue

            if role:
                role_matches = [
                    row for row in rows
                    if infer_connector_role(row.source_type, row.config_json, row.display_name) == role
                ]
                if role_matches:
                    return role_matches[0]
                continue

            return rows[0]

        return None


def resolve_service_namespace(service_name: str) -> str | None:
    """Return the configured Kubernetes namespace for a service from the DB.

    Queries ApplicationServiceRow.namespace for the first service matching
    service_name or k8s_app_label. Returns None when the service is not
    onboarded or no namespace has been configured — callers must handle
    None explicitly and should NOT fall back to a hardcoded string.
    """
    try:
        from corvin.storage.db import get_session
        from corvin.storage.models import ApplicationServiceRow

        with get_session() as session:
            row = session.query(ApplicationServiceRow).filter(
                (ApplicationServiceRow.service_name == service_name)
                | (ApplicationServiceRow.k8s_app_label == service_name)
            ).first()
            if row is not None and row.namespace:
                return row.namespace
            return None
    except Exception as exc:
        _log.warning("resolve_service_namespace: DB lookup failed for service=%s: %s", service_name, exc)
        return None


def resolve_outbound_connector_config(
    service_name: str,
    *,
    connector_type: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve outbound connector config for a service from DB rows.

    Returns the first active connector config for the matching application and
    connector type. If no match is found, returns a copy of *fallback* (when
    provided) or None.
    """
    try:
        row = _find_matching_outbound_connector(service_name=service_name, connector_type=connector_type)
        if row is None:
            return dict(fallback) if fallback is not None else None
        cfg = dict(fallback or {})
        cfg.update(row.config_json or {})
        return cfg
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Outbound connector resolution failed for service=%s type=%s: %s",
            service_name,
            connector_type,
            exc,
        )
        return dict(fallback) if fallback is not None else None


def _find_matching_outbound_connector(service_name: str, connector_type: str) -> OutboundConnectorRow | None:
    with get_session() as session:
        svc_rows = session.query(ApplicationServiceRow).filter(
            or_(
                ApplicationServiceRow.service_name == service_name,
                ApplicationServiceRow.k8s_app_label == service_name,
            )
        ).all()
        if not svc_rows:
            return None

        for svc in svc_rows:
            rows = session.query(OutboundConnectorRow).filter(
                OutboundConnectorRow.application_id == svc.application_id,
                OutboundConnectorRow.connector_type == connector_type,
                OutboundConnectorRow.is_active == True,  # noqa: E712
            ).all()
            if rows:
                return rows[0]

        return None
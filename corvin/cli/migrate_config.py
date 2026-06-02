"""
One-time migration: seeds the Application Panel from existing environment and legacy config.

Called via POST /applications/migrate-from-yaml or directly:
    python -m corvin.cli.migrate_config
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from sqlalchemy.orm import Session

from corvin.core.config_loader import get_env
from corvin.connectors.config_resolver import ROLE_APIM_LOGS, ROLE_CONTAINER_INSIGHTS
from corvin.storage.models import (
    ApplicationRow,
    ApplicationServiceRow,
    LogSourceRow,
    OutboundConnectorRow,
    SloConfigRow,
)

_log = logging.getLogger(__name__)

_DEFAULT_APP_NAME = "Auto-discovered Application"
_DEFAULT_TEAM = "Platform Team"


def run_migration(db: Session) -> dict[str, Any]:
    """
    Read existing environment/bootstrap values and knowledge/site.md, then seed a default
    Application record if none exists yet.  Idempotent — re-running is safe.
    """
    existing = db.query(ApplicationRow).count()
    if existing > 0:
        return {"status": "skipped", "reason": "Applications already exist", "count": existing}

    app_id = str(uuid.uuid4())
    app = ApplicationRow(
        id=app_id,
        name=_DEFAULT_APP_NAME,
        description="Auto-migrated from YAML config on first startup",
        team_name=_DEFAULT_TEAM,
        environment_default=get_env() or "dev",
        topology_json={},
    )
    db.add(app)

    services_created = _seed_services(db, app_id)
    connectors_created = _seed_connectors(db, app_id)
    outbound_created = _seed_outbound_connectors(db, app_id)
    slos_created = _seed_slo_defaults(db, app_id, services_created)

    db.flush()
    _log.info(
        "migrate_config: seeded application %r (%d services, %d connectors, %d outbound, %d SLOs)",
        app_id, len(services_created), connectors_created, outbound_created, slos_created,
    )
    return {
        "status": "ok",
        "application_id": app_id,
        "services_created": len(services_created),
        "connectors_created": connectors_created,
        "outbound_connectors_created": outbound_created,
        "slos_created": slos_created,
    }


def _seed_services(db: Session, app_id: str) -> list[str]:
    """Derive services from knowledge/site.md service list (best-effort)."""
    service_names: list[str] = []
    try:
        site_path = os.path.join("knowledge", "site.md")
        if os.path.exists(site_path):
            with open(site_path, encoding="utf-8") as f:
                content = f.read()
            # Extract bullet-point service names (lines starting with "- " or "* ")
            for line in content.splitlines():
                stripped = line.strip().lstrip("-*").strip()
                if stripped and len(stripped) < 80 and not stripped.startswith("#"):
                    if any(kw in stripped.lower() for kw in ["service", "api", "worker", "gateway", "frontend", "backend"]):
                        service_names.append(stripped[:255])
    except Exception as exc:
        _log.debug("migrate_config: could not parse site.md: %s", exc)

    # Fallback default services
    if not service_names:
        service_names = ["service-api", "service-frontend", "service-worker", "api-gateway"]

    tiers = {"frontend": "frontend", "gateway": "api", "api": "api", "worker": "worker", "db": "db"}
    for svc in service_names[:20]:  # cap at 20
        tier = next((v for k, v in tiers.items() if k in svc.lower()), "api")
        db.add(ApplicationServiceRow(
            application_id=app_id,
            service_name=svc,
            display_name=svc.replace("-", " ").title(),
            tier=tier,
            dependencies=[],
            metadata_json={"migrated_from": "site.md"},
        ))
    return service_names[:20]


def _seed_connectors(db: Session, app_id: str) -> int:
    """Seed connectors from existing bootstrap environment values."""
    count = 0
    subscription_id = _env_string("AZURE_SUBSCRIPTION_ID")
    tenant_id = _env_string("AZURE_TENANT_ID")
    aks_cluster_name = _env_string("AKS_CLUSTER_NAME") or _site_value("AKS Cluster", "Cluster name")
    aks_resource_group = _env_string("AKS_RESOURCE_GROUP") or _site_value("AKS Cluster", "Resource group")
    aks_namespace = _env_string("AKS_NAMESPACE") or _site_value("AKS Cluster", "Default namespace") or "default"
    apim_resource_group = _env_string("APIM_RESOURCE_GROUP") or _site_value("Azure API Management (APIM)", "Resource group")

    # Azure Log Analytics
    workspace_id = _env_string("LOG_ANALYTICS_WORKSPACE_ID")
    if workspace_id:
        db.add(LogSourceRow(
            id=str(uuid.uuid4()),
            application_id=app_id,
            source_type="azure_monitor",
            display_name="APIM Log Analytics Workspace",
            config_json={
                "workspace_id": workspace_id,
                "apim_table": "ApiManagementGatewayLogs",
                "subscription_id": subscription_id,
                "tenant_id": tenant_id,
                "resource_group": apim_resource_group,
                "connector_role": ROLE_APIM_LOGS,
            },
            credential_type="env_var",
            credential_ref=None,
        ))
        count += 1

    # Container Insights / AKS application logs
    # Prefer generic name; keep legacy CHAD var as backward-compatible fallback.
    container_workspace_id = (
        _env_string("CONTAINER_LOG_ANALYTICS_WORKSPACE_ID")
        or _env_string("CHAD_LOG_ANALYTICS_WORKSPACE_ID")
    )
    if container_workspace_id:
        db.add(LogSourceRow(
            id=str(uuid.uuid4()),
            application_id=app_id,
            source_type="azure_monitor",
            display_name="Container Insights Workspace",
            config_json={
                "workspace_id": container_workspace_id,
                "cluster_name": aks_cluster_name or "",
                "resource_group": aks_resource_group,
                "subscription_id": subscription_id,
                "tenant_id": tenant_id,
                "default_namespace": aks_namespace,
                "default_time_range_minutes": 60,
                "max_log_rows": 200,
                "connector_role": ROLE_CONTAINER_INSIGHTS,
            },
            credential_type="env_var",
            credential_ref=None,
        ))
        count += 1

    # Elasticsearch
    try:
        elastic_host = os.environ.get("ELASTIC_HOST", "")
        elastic_key = os.environ.get("ELASTIC_API_KEY", "")
        if elastic_host and elastic_host != "https://your-elastic-host:9200":
            db.add(LogSourceRow(
                id=str(uuid.uuid4()),
                application_id=app_id,
                source_type="elastic",
                display_name="Elasticsearch",
                config_json={"cluster_url": elastic_host},
                credential_type="env_var",
                credential_ref="ELASTIC_API_KEY" if elastic_key else None,
            ))
            count += 1
    except Exception as exc:
        _log.debug("migrate_config: elastic config not found: %s", exc)

    return count


def _seed_outbound_connectors(db: Session, app_id: str) -> int:
    """Seed outbound delivery connectors from existing integration config."""
    count = 0

    webhook_url = str(os.environ.get("TEAMS_WEBHOOK_URL", "")).strip()
    if webhook_url and not webhook_url.startswith("${"):
        db.add(OutboundConnectorRow(
            id=str(uuid.uuid4()),
            application_id=app_id,
            connector_type="teams_webhook",
            display_name="Microsoft Teams",
            config_json={
                "endpoint": webhook_url,
                "auth": {"type": "none"},
                "variables": [
                    {"key": "title", "default_value": "Corvin Alert: {{service_name}}"},
                    {"key": "summary", "default_value": "{{rca_summary}}"},
                    {"key": "severity_color", "default_value": "FF0000"},
                ],
                "payload_template": '{"title":"{{title}}","text":"{{summary}}","themeColor":"{{severity_color}}"}',
            },
        ))
        count += 1

    return count


def _seed_slo_defaults(db: Session, app_id: str, service_names: list[str]) -> int:
    """Seed default availability SLOs for each discovered service."""
    for svc in service_names[:10]:
        db.add(SloConfigRow(
            application_id=app_id,
            service_name=svc,
            sli_type="availability",
            target_pct=99.9,
            time_window_days=30,
            enabled=True,
        ))
    return min(len(service_names), 10)


def _env_string(name: str) -> str | None:
    value = str(os.environ.get(name, "")).strip()
    return value or None


def _site_value(section_name: str, field_name: str) -> str | None:
    site_path = os.path.join("knowledge", "site.md")
    if not os.path.exists(site_path):
        return None
    try:
        with open(site_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as exc:  # noqa: BLE001
        _log.debug("migrate_config: could not read site.md for %s/%s: %s", section_name, field_name, exc)
        return None

    in_section = False
    target_prefix = f"- {field_name}:"
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line[3:].strip() == section_name
            continue
        if in_section and line.startswith(target_prefix):
            value = line.split(":", 1)[1].strip().strip("`")
            return value or None
    return None


if __name__ == "__main__":
    from corvin.storage.db import get_session
    with get_session() as session:
        result = run_migration(session)
    print(result)

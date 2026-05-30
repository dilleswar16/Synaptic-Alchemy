"""
One-time migration: seeds the Application Panel from YAML config files.

Called via POST /applications/migrate-from-yaml or directly:
    python -m corvin.cli.migrate_config
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from sqlalchemy.orm import Session

from corvin.core.config_loader import load_config, get_env
from corvin.storage.models import ApplicationRow, ApplicationServiceRow, LogSourceRow, SloConfigRow

_log = logging.getLogger(__name__)

_DEFAULT_APP_NAME = "ChAD Platform"
_DEFAULT_TEAM = "AMS Platform"


def run_migration(db: Session) -> dict[str, Any]:
    """
    Read config/integrations/*.yaml and knowledge/site.md, then seed a default
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
    slos_created = _seed_slo_defaults(db, app_id, services_created)

    db.flush()
    _log.info(
        "migrate_config: seeded application %r (%d services, %d connectors, %d SLOs)",
        app_id, len(services_created), connectors_created, slos_created,
    )
    return {
        "status": "ok",
        "application_id": app_id,
        "services_created": len(services_created),
        "connectors_created": connectors_created,
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
        service_names = ["chad-api", "chad-frontend", "chad-worker", "apim-gateway"]

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
    """Seed connectors from existing YAML integration configs."""
    count = 0
    # Azure Log Analytics
    try:
        la_cfg = load_config("integrations/log_analytics", get_env())
        workspace_id = la_cfg.get("workspace_id", "")
        if workspace_id and not workspace_id.startswith("${"):
            db.add(LogSourceRow(
                id=str(uuid.uuid4()),
                application_id=app_id,
                source_type="azure_monitor",
                display_name="Azure Log Analytics (APIM)",
                config_json={
                    "workspace_id": workspace_id,
                    "apim_table": la_cfg.get("apim_table", "ApiManagementGatewayLogs"),
                },
                credential_type="env_var",
                credential_ref=None,  # Uses DefaultAzureCredential
            ))
            count += 1
    except Exception as exc:
        _log.debug("migrate_config: log_analytics config not found: %s", exc)

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


if __name__ == "__main__":
    from corvin.storage.db import get_session
    with get_session() as session:
        result = run_migration(session)
    print(result)

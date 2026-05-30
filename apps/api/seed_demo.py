"""
Demo data seeder for Corvin.

Populates the DB with 25 realistic MetLife-style services across 5 applications,
each with SLO configs and historical snapshots.  The endpoint schemas are
identical to what a real connector would produce — swap in a real connector
and the simulated rows age out naturally.

Activation:
    Set  CORVIN_DEMO_MODE=true  (default in dev) before starting uvicorn.
    The seeder is idempotent: it skips if the applications table is non-empty.

Data contract:
    All SloSnapshotRow rows are written with  data_source='simulated'.
    The SLO and Investigation routes are *unchanged* — they query the DB as
    normal.  This means the frontend API calls need zero modification to
    switch from demo to real data.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from corvin.storage.models import (
    ApplicationRow,
    ApplicationServiceRow,
    SloConfigRow,
    SloSnapshotRow,
)

log = logging.getLogger("corvin.seed_demo")

# ---------------------------------------------------------------------------
# Service catalogue
# Each entry: (app_id_key, service_name, display_name, tier, namespace, health_profile)
#
# health_profile controls the simulated SLO trajectory:
#   "healthy"   -> 99.95%+ availability, low burn rate
#   "ok"        -> 99.5–99.9%, moderate burn rate
#   "at_risk"   -> 98–99%, elevated burn rate (>0.8)
#   "breaching" -> <98%, fast burn (>1.5), SLO violated
# ---------------------------------------------------------------------------

_APPS: list[dict] = [
    {
        "key": "claims",
        "name": "Claims Platform",
        "description": "End-to-end claims intake, workflow automation, and payment disbursement",
        "team": "Claims Engineering",
        "env": "production",
        "services": [
            ("claims-api",          "Claims API",           "api",    "claims",     "healthy"),
            ("claims-workflow",     "Workflow Engine",      "worker", "claims",     "ok"),
            ("document-processor",  "Document Processor",   "worker", "claims",     "at_risk"),
            ("fraud-detection",     "Fraud Detection",      "api",    "claims",     "ok"),
            ("claims-payments",     "Payments Gateway",     "api",    "claims",     "breaching"),
        ],
    },
    {
        "key": "policy",
        "name": "Policy Management",
        "description": "Policy lifecycle management, underwriting, and rating engine",
        "team": "Policy Platform",
        "env": "production",
        "services": [
            ("policy-service",      "Policy Service",       "api",    "policy",     "healthy"),
            ("underwriting-svc",    "Underwriting Engine",  "api",    "policy",     "ok"),
            ("rating-engine",       "Rating Engine",        "api",    "policy",     "healthy"),
            ("policy-events",       "Policy Event Bus",     "queue",  "policy",     "ok"),
            ("policy-search",       "Policy Search",        "api",    "policy",     "at_risk"),
        ],
    },
    {
        "key": "portal",
        "name": "Customer Portal",
        "description": "Customer-facing web and mobile authentication, profiles, and notifications",
        "team": "Digital Experience",
        "env": "production",
        "services": [
            ("auth-service",        "Auth Service",         "api",    "portal",     "healthy"),
            ("profile-api",         "Profile API",          "api",    "portal",     "ok"),
            ("notifications-svc",   "Notifications",        "worker", "portal",     "healthy"),
            ("preferences-api",     "Preferences API",      "api",    "portal",     "ok"),
            ("session-manager",     "Session Manager",      "api",    "portal",     "at_risk"),
        ],
    },
    {
        "key": "data",
        "name": "Data Platform",
        "description": "Data ingestion pipelines, analytics APIs, ML model serving, and reporting",
        "team": "Data Engineering",
        "env": "production",
        "services": [
            ("data-ingestion",      "Data Ingestion",       "worker", "data",       "ok"),
            ("analytics-api",       "Analytics API",        "api",    "data",       "ok"),
            ("reporting-svc",       "Reporting Service",    "api",    "data",       "healthy"),
            ("data-quality",        "Data Quality",         "worker", "data",       "at_risk"),
            ("ml-inference",        "ML Inference",         "api",    "data",       "breaching"),
        ],
    },
    {
        "key": "infra",
        "name": "Infrastructure",
        "description": "Cross-cutting infrastructure: API gateway, service mesh, config, and secrets",
        "team": "Platform Engineering",
        "env": "production",
        "services": [
            ("api-gateway",         "API Gateway",          "api",    "infra",      "healthy"),
            ("service-mesh",        "Service Mesh",         "api",    "infra",      "ok"),
            ("monitoring-agent",    "Monitoring Agent",     "worker", "infra",      "healthy"),
            ("config-service",      "Config Service",       "api",    "infra",      "ok"),
            ("secret-manager",      "Secret Manager",       "api",    "infra",      "healthy"),
        ],
    },
]

# SLO targets per health profile (availability %, latency_ms_threshold)
_AVAIL_TARGET: dict[str, float] = {
    "healthy":   99.9,
    "ok":        99.5,
    "at_risk":   99.0,
    "breaching": 99.5,  # target is still high — they're violating it
}
_LATENCY_TARGET: dict[str, float] = {
    "healthy":   99.9,
    "ok":        99.5,
    "at_risk":   99.0,
    "breaching": 99.5,
}

# Snapshot values per health profile over 5 time windows (most-recent LAST)
# Each tuple: (measured_avail_pct, measured_latency_pct, error_budget_pct, burn_rate)
_SNAPSHOTS: dict[str, list[tuple[float, float, float, float]]] = {
    "healthy": [
        (99.97, 99.95, 95.2, 0.04),
        (99.96, 99.94, 94.8, 0.06),
        (99.98, 99.96, 96.1, 0.04),
        (99.97, 99.95, 95.5, 0.05),
        (99.96, 99.93, 95.0, 0.06),
    ],
    "ok": [
        (99.72, 99.61, 68.4, 0.31),
        (99.68, 99.58, 64.2, 0.36),
        (99.75, 99.63, 70.1, 0.30),
        (99.71, 99.60, 66.8, 0.33),
        (99.69, 99.57, 63.5, 0.37),
    ],
    "at_risk": [
        (98.91, 98.72, 28.4, 0.81),
        (98.74, 98.55, 22.1, 0.93),
        (98.62, 98.44, 17.8, 1.02),
        (98.55, 98.38, 13.2, 1.11),
        (98.41, 98.26,  9.6, 1.21),
    ],
    "breaching": [
        (97.83, 97.61,  8.2, 1.52),
        (97.51, 97.34,  4.4, 1.71),
        (97.22, 97.08,  1.8, 1.89),
        (96.94, 96.82,  0.3, 2.14),
        (96.71, 96.55, -2.1, 2.31),  # negative = already blown through budget
    ],
}

_NOW = datetime.now(tz=timezone.utc)


def _snapshot_times(n: int = 5) -> list[datetime]:
    """Return n evenly-spaced timestamps over the last 30 days, ending ~now."""
    step = timedelta(days=30) / n
    return [_NOW - timedelta(days=30) + step * i for i in range(n)]


def ensure_demo_data(db: Session) -> bool:
    """
    Seed the DB with demo data if the applications table is empty.

    Returns True if data was seeded, False if the table was already populated.
    The function is idempotent — safe to call on every startup.
    """
    already_seeded = db.query(ApplicationRow).filter_by(name="Claims Platform").first()
    if already_seeded is not None:
        log.info("Demo seed: demo data already present, skipping.")
        return False

    log.info("Demo seed: seeding 25 MetLife-style services …")

    times = _snapshot_times(5)

    for app_def in _APPS:
        app_id = str(uuid.uuid4())
        app = ApplicationRow(
            id=app_id,
            name=app_def["name"],
            description=app_def["description"],
            team_name=app_def["team"],
            environment_default=app_def["env"],
            topology_json={},
        )
        db.add(app)
        db.flush()  # get app.id before FK inserts

        for svc_name, display_name, tier, namespace, profile in app_def["services"]:
            # ── Service row ───────────────────────────────────────────────
            svc = ApplicationServiceRow(
                application_id=app_id,
                service_name=svc_name,
                display_name=display_name,
                namespace=namespace,
                tier=tier,
                dependencies=[],
                metadata_json={"health_profile": profile},
            )
            db.add(svc)

            snaps = _SNAPSHOTS[profile]
            avail_target = _AVAIL_TARGET[profile]
            latency_target = _LATENCY_TARGET[profile]

            # ── Availability SLO config ───────────────────────────────────
            avail_cfg = SloConfigRow(
                application_id=app_id,
                service_name=svc_name,
                sli_type="availability",
                target_pct=avail_target,
                time_window_days=30,
                latency_threshold_ms=None,
                enabled=True,
            )
            db.add(avail_cfg)
            db.flush()

            for i, (avail_pct, _lat_pct, budget_pct, burn) in enumerate(snaps):
                db.add(SloSnapshotRow(
                    slo_config_id=avail_cfg.id,
                    application_id=app_id,
                    service_name=svc_name,
                    sli_type="availability",
                    target_pct=avail_target,
                    measured_pct=avail_pct,
                    error_budget_pct=budget_pct,
                    burn_rate=burn,
                    is_compliant=avail_pct >= avail_target,
                    data_source="simulated",
                    sampled_at=times[i],
                    raw_json={"profile": profile, "snapshot_index": i},
                ))

            # ── Latency SLO config ────────────────────────────────────────
            latency_cfg = SloConfigRow(
                application_id=app_id,
                service_name=svc_name,
                sli_type="latency",
                target_pct=latency_target,
                time_window_days=30,
                latency_threshold_ms=200,
                enabled=True,
            )
            db.add(latency_cfg)
            db.flush()

            for i, (_avail_pct, lat_pct, budget_pct, burn) in enumerate(snaps):
                # Latency budget slightly different from availability
                lat_budget = max(budget_pct - 3.0, budget_pct * 0.92)
                db.add(SloSnapshotRow(
                    slo_config_id=latency_cfg.id,
                    application_id=app_id,
                    service_name=svc_name,
                    sli_type="latency",
                    target_pct=latency_target,
                    measured_pct=lat_pct,
                    error_budget_pct=lat_budget,
                    burn_rate=round(burn * 1.08, 3),
                    is_compliant=lat_pct >= latency_target,
                    data_source="simulated",
                    sampled_at=times[i],
                    raw_json={"profile": profile, "snapshot_index": i},
                ))

    db.commit()
    total_apps = len(_APPS)
    total_svcs = sum(len(a["services"]) for a in _APPS)
    log.info(
        "Demo seed complete: %d apps, %d services, %d SLO configs, %d snapshots.",
        total_apps, total_svcs, total_svcs * 2, total_svcs * 2 * 5,
    )
    return True

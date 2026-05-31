"""
Seeder for Corvin — CHAD application only.

Populates the DB with the single real CHAD application and its three services:
  - fundapis     (k8s: chad-fundapis)    — Fund APIs backend, via APIM
  - fundsso      (k8s: chad-fundsso)     — SSO / auth service, direct (no APIM)
  - partnerapis  (k8s: chad-partnerapis) — Partner APIs backend, via APIM

Activation:
    Set  CORVIN_DEMO_MODE=true  (default in dev) before starting uvicorn.
    The seeder is idempotent: it skips if CHAD is already present.

Data contract:
    SloSnapshotRow rows are written with  data_source='simulated'.
    Swap in a real SLO connector and the simulated rows age out naturally.
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
# CHAD application — single entry
# Services: (service_name, display_name, k8s_label, tier, health_profile)
#
# health_profile controls simulated SLO trajectory:
#   "ok"       -> 99.5–99.9%, moderate burn rate
#   "at_risk"  -> 98–99%, elevated burn rate (>0.8)
# ---------------------------------------------------------------------------

_CHAD_APP: dict = {
    "name": "CHAD",
    "description": (
        "Channel Account & Distribution platform — fund APIs, partner APIs, "
        "and SSO service running in AKS namespace 'chad'."
    ),
    "team": "CHAD Engineering",
    "env": "dev",
    "services": [
        # (service_name,  display_name,    k8s_label,          tier,   health_profile)
        ("fundapis",     "Fund APIs",      "chad-fundapis",     "api",  "ok"),
        ("fundsso",      "Fund SSO",       "chad-fundsso",      "api",  "ok"),
        ("partnerapis",  "Partner APIs",   "chad-partnerapis",  "api",  "at_risk"),
    ],
}

_AVAIL_TARGET: dict[str, float] = {
    "ok":      99.5,
    "at_risk": 99.0,
}
_LATENCY_TARGET: dict[str, float] = {
    "ok":      99.5,
    "at_risk": 99.0,
}

# Snapshot values per health profile over 5 windows (most-recent LAST)
# Each tuple: (measured_avail_pct, measured_latency_pct, error_budget_pct, burn_rate)
_SNAPSHOTS: dict[str, list[tuple[float, float, float, float]]] = {
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
}

_NOW = datetime.now(tz=timezone.utc)


def _snapshot_times(n: int = 5) -> list[datetime]:
    """Return n evenly-spaced timestamps over the last 30 days, ending ~now."""
    step = timedelta(days=30) / n
    return [_NOW - timedelta(days=30) + step * i for i in range(n)]


def ensure_demo_data(db: Session) -> bool:
    """
    Seed the DB with the CHAD application if it is not already present.

    Returns True if data was seeded, False if already populated.
    Idempotent — safe to call on every startup.
    """
    already_seeded = db.query(ApplicationRow).filter_by(name="CHAD").first()
    if already_seeded is not None:
        log.info("Demo seed: CHAD already present, skipping.")
        return False

    log.info("Demo seed: seeding CHAD application with 3 services …")

    app_id = str(uuid.uuid4())
    app = ApplicationRow(
        id=app_id,
        name=_CHAD_APP["name"],
        description=_CHAD_APP["description"],
        team_name=_CHAD_APP["team"],
        environment_default=_CHAD_APP["env"],
        topology_json={},
    )
    db.add(app)
    db.flush()

    times = _snapshot_times(5)

    for svc_name, display_name, k8s_label, tier, profile in _CHAD_APP["services"]:
        svc = ApplicationServiceRow(
            application_id=app_id,
            service_name=svc_name,
            display_name=display_name,
            namespace="chad",
            tier=tier,
            k8s_app_label=k8s_label,
            dependencies=[],
            metadata_json={
                "health_profile": profile,
                "apim_routes_through_gateway": svc_name != "fundsso",
                "apim_api_id": svc_name,
                "is_sso_direct": svc_name == "fundsso",
            },
        )
        db.add(svc)

        snaps = _SNAPSHOTS[profile]
        avail_target = _AVAIL_TARGET[profile]
        latency_target = _LATENCY_TARGET[profile]

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
    log.info("Demo seed complete: 1 app (CHAD), 3 services, 6 SLO configs, 30 snapshots.")
    return True

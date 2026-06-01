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


def _baseline_service_metadata(service_name: str, profile: str) -> dict:
    return {
        "health_profile": profile,
        "apim_routes_through_gateway": service_name != "fundsso",
        "apim_api_id": service_name,
        "is_sso_direct": service_name == "fundsso",
    }


def _ensure_slo_config(
    db: Session,
    *,
    app_id: str,
    service_name: str,
    sli_type: str,
    target_pct: float,
    latency_threshold_ms: int | None,
) -> tuple[SloConfigRow, bool]:
    existing = db.query(SloConfigRow).filter_by(
        application_id=app_id,
        service_name=service_name,
        sli_type=sli_type,
    ).first()
    if existing is not None:
        return existing, False

    cfg = SloConfigRow(
        application_id=app_id,
        service_name=service_name,
        sli_type=sli_type,
        target_pct=target_pct,
        time_window_days=30,
        latency_threshold_ms=latency_threshold_ms,
        enabled=True,
    )
    db.add(cfg)
    db.flush()
    return cfg, True


def _ensure_slo_snapshots(
    db: Session,
    *,
    app_id: str,
    service_name: str,
    slo_config_id: int,
    sli_type: str,
    target_pct: float,
    profile: str,
    times: list[datetime],
    snaps: list[tuple[float, float, float, float]],
) -> bool:
    existing_count = db.query(SloSnapshotRow).filter_by(slo_config_id=slo_config_id).count()
    if existing_count > 0:
        return False

    for i, (avail_pct, lat_pct, budget_pct, burn) in enumerate(snaps):
        measured_pct = avail_pct if sli_type == "availability" else lat_pct
        snapshot_budget = budget_pct if sli_type == "availability" else max(budget_pct - 3.0, budget_pct * 0.92)
        snapshot_burn = burn if sli_type == "availability" else round(burn * 1.08, 3)
        db.add(SloSnapshotRow(
            slo_config_id=slo_config_id,
            application_id=app_id,
            service_name=service_name,
            sli_type=sli_type,
            target_pct=target_pct,
            measured_pct=measured_pct,
            error_budget_pct=snapshot_budget,
            burn_rate=snapshot_burn,
            is_compliant=measured_pct >= target_pct,
            data_source="simulated",
            sampled_at=times[i],
            raw_json={"profile": profile, "snapshot_index": i},
        ))
    return True


def ensure_demo_data(db: Session) -> bool:
    """
    Seed the DB with the CHAD application if it is not already present.

    Returns True if data was seeded, False if already populated.
    Idempotent — safe to call on every startup.
    """
    changed = False
    app = db.query(ApplicationRow).filter_by(name="CHAD").first()
    if app is None:
        log.info("Demo seed: creating CHAD application baseline …")
        app = ApplicationRow(
            id=str(uuid.uuid4()),
            name=_CHAD_APP["name"],
            description=_CHAD_APP["description"],
            team_name=_CHAD_APP["team"],
            environment_default=_CHAD_APP["env"],
            topology_json={},
        )
        db.add(app)
        db.flush()
        changed = True
    else:
        log.info("Demo seed: reconciling CHAD baseline data …")

    times = _snapshot_times(5)
    app_id = app.id
    existing_services = {
        row.service_name: row
        for row in db.query(ApplicationServiceRow).filter_by(application_id=app_id).all()
    }

    for svc_name, display_name, k8s_label, tier, profile in _CHAD_APP["services"]:
        baseline_metadata = _baseline_service_metadata(svc_name, profile)
        svc = existing_services.get(svc_name)
        if svc is None:
            svc = ApplicationServiceRow(
                application_id=app_id,
                service_name=svc_name,
                display_name=display_name,
                namespace="chad",
                tier=tier,
                k8s_app_label=k8s_label,
                dependencies=[],
                metadata_json=baseline_metadata,
            )
            db.add(svc)
            changed = True
        else:
            merged_metadata = dict(baseline_metadata)
            merged_metadata.update(svc.metadata_json or {})
            if not svc.display_name:
                svc.display_name = display_name
                changed = True
            if not svc.namespace:
                svc.namespace = "chad"
                changed = True
            if not svc.tier:
                svc.tier = tier
                changed = True
            if not svc.k8s_app_label:
                svc.k8s_app_label = k8s_label
                changed = True
            if merged_metadata != (svc.metadata_json or {}):
                svc.metadata_json = merged_metadata
                changed = True

        snaps = _SNAPSHOTS[profile]
        avail_target = _AVAIL_TARGET[profile]
        latency_target = _LATENCY_TARGET[profile]

        avail_cfg, avail_created = _ensure_slo_config(
            db,
            app_id=app_id,
            service_name=svc_name,
            sli_type="availability",
            target_pct=avail_target,
            latency_threshold_ms=None,
        )
        latency_cfg, latency_created = _ensure_slo_config(
            db,
            app_id=app_id,
            service_name=svc_name,
            sli_type="latency",
            target_pct=latency_target,
            latency_threshold_ms=200,
        )
        changed = avail_created or changed
        changed = latency_created or changed

        changed = _ensure_slo_snapshots(
            db,
            app_id=app_id,
            service_name=svc_name,
            slo_config_id=avail_cfg.id,
            sli_type="availability",
            target_pct=avail_target,
            profile=profile,
            times=times,
            snaps=snaps,
        ) or changed
        changed = _ensure_slo_snapshots(
            db,
            app_id=app_id,
            service_name=svc_name,
            slo_config_id=latency_cfg.id,
            sli_type="latency",
            target_pct=latency_target,
            profile=profile,
            times=times,
            snaps=snaps,
        ) or changed

    db.commit()
    if changed:
        log.info("Demo seed complete: CHAD baseline is present and reconciled.")
    else:
        log.info("Demo seed: CHAD baseline already complete, no changes needed.")
    return changed

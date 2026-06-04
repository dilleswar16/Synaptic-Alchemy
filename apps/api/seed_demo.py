"""Demo data seeder — reads from config/demo/seed_data.yaml.

Activation:
    Set CORVIN_DEMO_MODE=true before starting uvicorn.
    The seeder is idempotent: it skips rows that already exist.

To customise for a new deployment, edit config/demo/seed_data.yaml.
No source code changes are required.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from corvin.storage.models import (
    ApplicationEnvironmentRow,
    ApplicationRow,
    ApplicationServiceRow,
    KnowledgeBaseRow,
    SimulatorPresetRow,
    SloConfigRow,
    SloSnapshotRow,
)

log = logging.getLogger("corvin.seed_demo")

_SEED_FILE = Path(__file__).parents[2] / "config" / "demo" / "seed_data.yaml"
_NOW = datetime.now(tz=timezone.utc)


def _load_seed_config() -> dict[str, Any]:
    if not _SEED_FILE.exists():
        log.warning("Demo seed: %s not found — skipping", _SEED_FILE)
        return {}
    with _SEED_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _snapshot_times(n: int = 5) -> list[datetime]:
    step = timedelta(days=30) / n
    return [_NOW - timedelta(days=30) + step * i for i in range(n)]


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
    if db.query(SloSnapshotRow).filter_by(slo_config_id=slo_config_id).count() > 0:
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
    """Seed the DB from config/demo/seed_data.yaml if not already present.

    Returns True if data was inserted or updated, False if already complete.
    Idempotent — safe to call on every startup.
    """
    seed = _load_seed_config()
    if not seed:
        return False

    app_cfg: dict[str, Any] = seed.get("application", {})
    app_name = app_cfg.get("name", "Demo Application")
    if not app_name:
        log.warning("Demo seed: application.name not set in seed_data.yaml — skipping")
        return False

    changed = False
    app = db.query(ApplicationRow).filter_by(name=app_name).first()
    if app is None:
        log.info("Demo seed: creating '%s' application …", app_name)
        app = ApplicationRow(
            id=str(uuid.uuid4()),
            name=app_name,
            description=app_cfg.get("description"),
            team_name=app_cfg.get("team_name"),
            environment_default=app_cfg.get("environment_default", "dev"),
            topology_json={},
        )
        db.add(app)
        db.flush()
        changed = True
    else:
        log.info("Demo seed: reconciling '%s' baseline data …", app_name)

    slo_profiles: dict[str, Any] = seed.get("slo_profiles", {})
    service_metadata: dict[str, Any] = seed.get("service_metadata", {})
    times = _snapshot_times(5)
    app_id = app.id

    existing_services = {
        row.service_name: row
        for row in db.query(ApplicationServiceRow).filter_by(application_id=app_id).all()
    }

    for svc_def in seed.get("services", []):
        svc_name = svc_def["service_name"]
        display_name = svc_def.get("display_name", svc_name)
        k8s_label = svc_def.get("k8s_app_label", svc_name)
        namespace = svc_def.get("namespace")
        tier = svc_def.get("tier")
        profile = svc_def.get("health_profile", "ok")
        metadata = dict(service_metadata.get(svc_name, {}))

        svc = existing_services.get(svc_name)
        if svc is None:
            svc = ApplicationServiceRow(
                application_id=app_id,
                service_name=svc_name,
                display_name=display_name,
                namespace=namespace,
                tier=tier,
                k8s_app_label=k8s_label,
                dependencies=[],
                metadata_json=metadata,
            )
            db.add(svc)
            changed = True
        else:
            merged_metadata = dict(metadata)
            merged_metadata.update(svc.metadata_json or {})
            if not svc.display_name:
                svc.display_name = display_name
                changed = True
            if not svc.namespace and namespace:
                svc.namespace = namespace
                changed = True
            if not svc.tier and tier:
                svc.tier = tier
                changed = True
            if not svc.k8s_app_label and k8s_label:
                svc.k8s_app_label = k8s_label
                changed = True
            if merged_metadata != (svc.metadata_json or {}):
                svc.metadata_json = merged_metadata
                changed = True

        profile_cfg = slo_profiles.get(profile, {})
        snaps_raw = profile_cfg.get("snapshots", [])
        snaps: list[tuple[float, float, float, float]] = [tuple(s) for s in snaps_raw]  # type: ignore[misc]
        avail_target = float(profile_cfg.get("availability_target_pct", 99.5))
        latency_target = float(profile_cfg.get("latency_target_pct", 99.5))
        latency_threshold_ms = profile_cfg.get("latency_threshold_ms", 200)

        avail_cfg, avail_created = _ensure_slo_config(
            db, app_id=app_id, service_name=svc_name,
            sli_type="availability", target_pct=avail_target, latency_threshold_ms=None,
        )
        latency_cfg, latency_created = _ensure_slo_config(
            db, app_id=app_id, service_name=svc_name,
            sli_type="latency", target_pct=latency_target, latency_threshold_ms=latency_threshold_ms,
        )
        changed = avail_created or latency_created or changed

        changed = _ensure_slo_snapshots(
            db, app_id=app_id, service_name=svc_name,
            slo_config_id=avail_cfg.id, sli_type="availability",
            target_pct=avail_target, profile=profile, times=times, snaps=snaps,
        ) or changed
        changed = _ensure_slo_snapshots(
            db, app_id=app_id, service_name=svc_name,
            slo_config_id=latency_cfg.id, sli_type="latency",
            target_pct=latency_target, profile=profile, times=times, snaps=snaps,
        ) or changed

    # ── Environments ─────────────────────────────────────────────────────────
    existing_env_names = {
        row.name
        for row in db.query(ApplicationEnvironmentRow).filter_by(application_id=app_id).all()
    }
    for order, env_def in enumerate(seed.get("environments", [])):
        name = env_def.get("name")
        if not name or name in existing_env_names:
            continue
        db.add(ApplicationEnvironmentRow(
            application_id=app_id,
            name=name,
            display_name=env_def.get("display_name", name.title()),
            priority_tier=env_def.get("priority_tier", "P3"),
            lookback_minutes=int(env_def.get("lookback_minutes", 60)),
            is_default=bool(env_def.get("is_default", False)),
            display_order=int(env_def.get("display_order", order)),
        ))
        changed = True

    # ── Knowledge base ────────────────────────────────────────────────────────
    existing_kb_count = db.query(KnowledgeBaseRow).filter_by(application_id=app_id).count()
    if existing_kb_count == 0:
        for order, kb_def in enumerate(seed.get("knowledge_base", [])):
            title = kb_def.get("title")
            content = kb_def.get("content")
            if not title or not content:
                continue
            db.add(KnowledgeBaseRow(
                id=str(uuid.uuid4()),
                application_id=app_id,
                title=title,
                content=str(content).strip(),
                is_active=True,
                display_order=int(kb_def.get("display_order", order)),
            ))
            changed = True

    # ── Simulator presets ─────────────────────────────────────────────────────
    existing_preset_ids = {
        row.scenario_id
        for row in db.query(SimulatorPresetRow).filter_by(application_id=app_id).all()
    }
    for order, preset_def in enumerate(seed.get("simulator_presets", [])):
        sid = preset_def.get("scenario_id")
        if not sid or sid in existing_preset_ids:
            continue
        db.add(SimulatorPresetRow(
            id=str(uuid.uuid4()),
            application_id=app_id,
            scenario_id=sid,
            label=preset_def.get("label", sid),
            service_name=preset_def["service_name"],
            environment=preset_def.get("environment", "dev"),
            description=preset_def.get("description", ""),
            icon_key=preset_def.get("icon_key"),
            accent_color=preset_def.get("accent_color"),
            is_active=True,
            display_order=preset_def.get("display_order", order),
        ))
        changed = True

    db.commit()
    status = "complete and reconciled" if changed else "already complete, no changes needed"
    log.info("Demo seed (%s): %s.", app_name, status)
    return changed

"""SLO Monitoring REST routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from corvin.storage.db import get_session as _get_session
from corvin.storage.models import ApplicationRow, SloConfigRow, SloSnapshotRow
from corvin.slo.snapshot import compute_snapshots_once

router = APIRouter()


def _db() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


# ── Response helpers ──────────────────────────────────────────────────────────


def _breach_analysis(cfg: SloConfigRow, snap: SloSnapshotRow | None) -> dict[str, Any]:
    """Compute human-readable breach reason and recommended action."""
    if snap is None or snap.measured_pct is None:
        return {"breach_reason": None, "recommended_action": None, "severity": None}
    if snap.is_compliant:
        return {"breach_reason": None, "recommended_action": None, "severity": None}

    gap = cfg.target_pct - snap.measured_pct
    burn = snap.burn_rate or 0

    # Determine severity
    if gap > 5 or burn > 10:
        severity = "critical"
    elif gap > 2 or burn > 3:
        severity = "warning"
    else:
        severity = "minor"

    # Build reason
    if cfg.sli_type == "availability":
        error_rate = 100 - snap.measured_pct
        reason = (
            f"{error_rate:.2f}% of requests are failing (5xx errors) "
            f"over the last {cfg.time_window_days}d — {gap:.2f}pp above the "
            f"{100 - cfg.target_pct:.1f}% error budget allowance."
        )
        if burn > 5:
            action = f"Investigate elevated 5xx errors immediately — burning budget at {burn:.1f}× normal rate. Check recent deployments and downstream dependencies."
        elif burn > 2:
            action = "Review recent deployment changes and health-check failures. Consider rolling back the last release if errors correlate."
        else:
            action = "Monitor error trends — intermittent failures may resolve. Check for transient dependency timeouts."
    else:
        threshold_ms = cfg.latency_threshold_ms or 500
        slow_pct = 100 - snap.measured_pct
        reason = (
            f"{slow_pct:.1f}% of requests exceed the {threshold_ms}ms latency threshold "
            f"over the last {cfg.time_window_days}d — target is ≥{cfg.target_pct}% within threshold."
        )
        if burn > 5:
            action = f"Critical latency degradation — {slow_pct:.0f}% of traffic is slow. Check for resource saturation (CPU/memory), cold starts, or downstream bottlenecks."
        elif burn > 2:
            action = f"Latency creep detected. Review connection pool sizing, database query performance, and consider scaling out or increasing the threshold to {threshold_ms + 500}ms."
        else:
            action = "Minor latency drift — consider adjusting the threshold if this reflects normal traffic patterns, or review recent load changes."

    return {"breach_reason": reason, "recommended_action": action, "severity": severity}


def _snap_dict(snap: SloSnapshotRow) -> dict[str, Any]:
    return {
        "id": snap.id,
        "slo_config_id": snap.slo_config_id,
        "application_id": snap.application_id,
        "service_name": snap.service_name,
        "sli_type": snap.sli_type,
        "target_pct": snap.target_pct,
        "measured_pct": snap.measured_pct,
        "error_budget_pct": snap.error_budget_pct,
        "burn_rate": snap.burn_rate,
        "is_compliant": snap.is_compliant,
        "data_source": snap.data_source,
        "sampled_at": snap.sampled_at.isoformat() if snap.sampled_at else None,
    }


def _config_dict(cfg: SloConfigRow, latest: SloSnapshotRow | None) -> dict[str, Any]:
    analysis = _breach_analysis(cfg, latest)
    return {
        "id": cfg.id,
        "application_id": cfg.application_id,
        "service_name": cfg.service_name,
        "sli_type": cfg.sli_type,
        "target_pct": cfg.target_pct,
        "time_window_days": cfg.time_window_days,
        "latency_threshold_ms": cfg.latency_threshold_ms,
        "enabled": cfg.enabled,
        "latest_snapshot": _snap_dict(latest) if latest else None,
        "breach_reason": analysis["breach_reason"],
        "recommended_action": analysis["recommended_action"],
        "breach_severity": analysis["severity"],
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/")
def list_slo_status(
    app_id: str | None = Query(default=None, alias="app_id"),
    db: Session = Depends(_db),
) -> list[dict[str, Any]]:
    """List all SLO configs with their latest snapshot."""
    q = db.query(SloConfigRow).filter(SloConfigRow.enabled == True)  # noqa: E712
    if app_id:
        q = q.filter(SloConfigRow.application_id == app_id)
    configs: list[SloConfigRow] = q.all()

    results: list[dict[str, Any]] = []
    for cfg in configs:
        latest = (
            db.query(SloSnapshotRow)
            .filter(SloSnapshotRow.slo_config_id == cfg.id)
            .order_by(SloSnapshotRow.sampled_at.desc())
            .first()
        )
        results.append(_config_dict(cfg, latest))
    return results


@router.get("/summary")
def get_slo_summary(db: Session = Depends(_db)) -> dict[str, Any]:
    """Aggregate SLO status counts — one entry per distinct service (availability preferred)."""
    configs: list[SloConfigRow] = (
        db.query(SloConfigRow).filter(SloConfigRow.enabled == True).all()  # noqa: E712
    )

    # Deduplicate by service_name: prefer availability SLI; fall back to whatever is first.
    best: dict[str, SloConfigRow] = {}
    for cfg in configs:
        key = f"{cfg.application_id}:{cfg.service_name}"
        existing = best.get(key)
        if existing is None or cfg.sli_type == "availability":
            best[key] = cfg

    compliant = at_risk = breached = no_data = 0

    for cfg in best.values():
        snap = (
            db.query(SloSnapshotRow)
            .filter(SloSnapshotRow.slo_config_id == cfg.id)
            .order_by(SloSnapshotRow.sampled_at.desc())
            .first()
        )
        if snap is None or snap.measured_pct is None:
            no_data += 1
        elif not snap.is_compliant:
            breached += 1
        elif snap.burn_rate is not None and snap.burn_rate > 0.9:
            at_risk += 1
        else:
            compliant += 1

    return {
        "total": len(best),
        "compliant": compliant,
        "at_risk": at_risk,
        "breached": breached,
        "no_data": no_data,
    }


@router.get("/{slo_id}/history")
def get_slo_history(
    slo_id: int,
    limit: int = Query(default=30, le=200),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Return the N most-recent snapshots for one SLO config."""
    cfg = db.get(SloConfigRow, slo_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="SLO config not found")
    snaps: list[SloSnapshotRow] = (
        db.query(SloSnapshotRow)
        .filter(SloSnapshotRow.slo_config_id == slo_id)
        .order_by(SloSnapshotRow.sampled_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "config": _config_dict(cfg, snaps[0] if snaps else None),
        "history": [_snap_dict(s) for s in snaps],
    }


@router.post("/refresh")
def refresh_snapshots(
    app_id: str | None = Query(default=None, alias="app_id"),
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Trigger an immediate SLO snapshot computation."""
    if app_id:
        # restrict to one app
        from corvin.storage.models import LogSourceRow
        configs: list[SloConfigRow] = (
            db.query(SloConfigRow)
            .filter(SloConfigRow.application_id == app_id, SloConfigRow.enabled == True)  # noqa: E712
            .all()
        )
        if not configs:
            return {"snapshots_written": 0}
        from corvin.slo.snapshot import compute_snapshot
        sources = (
            db.query(LogSourceRow)
            .filter(LogSourceRow.application_id == app_id, LogSourceRow.is_active == True)  # noqa: E712
            .all()
        )
        written = 0
        for cfg in configs:
            try:
                snap = compute_snapshot(cfg, sources)
                db.add(snap)
                written += 1
            except Exception:  # noqa: BLE001
                pass
        db.commit()
        return {"snapshots_written": written}

    results = compute_snapshots_once(db)
    return {"snapshots_written": len(results)}

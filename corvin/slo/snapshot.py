"""SLO Snapshot Engine — computes and stores health snapshots for each enabled SLO config."""
from __future__ import annotations

import asyncio
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from corvin.storage.db import get_session
from corvin.storage.models import ApplicationRow, LogSourceRow, SloConfigRow, SloSnapshotRow
from corvin.connectors.registry import ConnectorRegistry

logger = logging.getLogger(__name__)
_registry = ConnectorRegistry()

# ── Simulated data helpers ─────────────────────────────────────────────────────


def _simulate_availability(target_pct: float, seed: int) -> float:
    """Generate realistic availability value, biased toward target with occasional dips."""
    rng = random.Random(seed)
    # Normal distribution centred above target with small sigma
    base = target_pct + rng.gauss(0.15, 0.3)
    # Occasional degradation event (5% chance)
    if rng.random() < 0.05:
        base -= rng.uniform(0.5, 2.0)
    return round(min(100.0, max(0.0, base)), 4)


def _simulate_latency_pct(threshold_ms: int, seed: int) -> float:
    """Simulate % of requests below the latency threshold. Returns availability-like pct."""
    rng = random.Random(seed)
    # 95–99.9% of requests within threshold
    pct = rng.uniform(95.5, 99.9)
    if rng.random() < 0.04:
        pct -= rng.uniform(1.0, 5.0)
    return round(min(100.0, max(0.0, pct)), 4)


# ── Core computation ───────────────────────────────────────────────────────────


def _error_budget_pct(target: float, measured: float, window_days: int) -> tuple[float, float]:
    """
    Returns (error_budget_pct_remaining, burn_rate).

    error_budget_total = (1 - target/100) * window_days * 24 * 60  (minutes)
    consumed = (1 - measured/100) * window_days * 24 * 60
    remaining = max(0, total - consumed)
    remaining_pct = remaining / total * 100
    burn_rate = consumed / total  (1.0 = exactly at target; >1 = burning fast)
    """
    if target >= 100.0:
        return (100.0 if measured >= 100.0 else 0.0, 1.0)
    total_budget = (1.0 - target / 100.0) * window_days * 24 * 60
    if total_budget <= 0:
        return 100.0, 0.0
    consumed = (1.0 - measured / 100.0) * window_days * 24 * 60
    remaining = max(0.0, total_budget - consumed)
    remaining_pct = round(remaining / total_budget * 100, 2)
    burn_rate = round(consumed / total_budget, 4)
    return remaining_pct, burn_rate


def _try_connector_availability(
    log_sources: list[LogSourceRow],
    service_name: str,
    sli_type: str,
    latency_threshold_ms: int | None,
) -> tuple[float | None, dict[str, Any], str]:
    """
    Attempt to get real data from a connector.
    Returns (measured_pct | None, raw_dict, data_source).
    """
    for src in log_sources:
        if not src.is_active:
            continue
        connector = _registry.get_connector(src)
        if connector is None:
            continue
        try:
            if sli_type == "availability":
                result = connector.get_availability(service_name)
            else:
                result = connector.get_latency_pct(service_name, latency_threshold_ms or 500)
            if result is not None:
                return result["pct"], result.get("raw", {}), "connector"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Connector %s failed for %s/%s: %s", src.id, service_name, sli_type, exc)
    return None, {}, "simulated"


def compute_snapshot(
    cfg: SloConfigRow,
    log_sources: list[LogSourceRow],
) -> SloSnapshotRow:
    """Compute one snapshot for a given SloConfigRow."""
    seed = hash((cfg.id, datetime.now(timezone.utc).date().isoformat()))

    measured, raw, data_source = _try_connector_availability(
        log_sources, cfg.service_name, cfg.sli_type, cfg.latency_threshold_ms
    )

    if measured is None:
        if cfg.sli_type == "availability":
            measured = _simulate_availability(cfg.target_pct, seed)
        else:
            measured = _simulate_latency_pct(cfg.latency_threshold_ms or 500, seed)
        data_source = "simulated"

    budget_pct, burn_rate = _error_budget_pct(cfg.target_pct, measured, cfg.time_window_days)
    is_compliant = measured >= cfg.target_pct

    return SloSnapshotRow(
        slo_config_id=cfg.id,
        application_id=cfg.application_id,
        service_name=cfg.service_name,
        sli_type=cfg.sli_type,
        target_pct=cfg.target_pct,
        measured_pct=measured,
        error_budget_pct=budget_pct,
        burn_rate=burn_rate,
        is_compliant=is_compliant,
        data_source=data_source,
        sampled_at=datetime.now(timezone.utc),
        raw_json=raw,
    )


def compute_snapshots_once(db: Session) -> list[dict[str, Any]]:
    """
    Iterate all enabled SLO configs, compute snapshots, persist to DB.
    Returns a summary list.
    """
    configs: list[SloConfigRow] = (
        db.query(SloConfigRow)
        .filter(SloConfigRow.enabled == True)  # noqa: E712
        .all()
    )
    if not configs:
        return []

    # Bulk-load log sources per application to avoid N+1
    app_ids = list({c.application_id for c in configs})
    sources_by_app: dict[str, list[LogSourceRow]] = {}
    for app_id in app_ids:
        sources_by_app[app_id] = (
            db.query(LogSourceRow)
            .filter(LogSourceRow.application_id == app_id, LogSourceRow.is_active == True)  # noqa: E712
            .all()
        )

    results: list[dict[str, Any]] = []
    for cfg in configs:
        try:
            snap = compute_snapshot(cfg, sources_by_app.get(cfg.application_id, []))
            db.add(snap)
            results.append({
                "slo_config_id": cfg.id,
                "service_name": cfg.service_name,
                "sli_type": cfg.sli_type,
                "measured_pct": snap.measured_pct,
                "is_compliant": snap.is_compliant,
                "data_source": snap.data_source,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("Snapshot failed for slo_config %s: %s", cfg.id, exc)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("SLO snapshot computed: %d configs processed.", len(results))
    return results


# ── Background runner ──────────────────────────────────────────────────────────


async def run_forever(interval_seconds: int = 3600) -> None:
    """Periodically compute SLO snapshots. Runs every `interval_seconds`."""
    logger.info("SLO snapshot job started (interval=%ds).", interval_seconds)
    while True:
        try:
            with get_session() as db:
                results = compute_snapshots_once(db)
            logger.info("SLO snapshot job ran: %d snapshots written.", len(results))
        except asyncio.CancelledError:
            logger.info("SLO snapshot job cancelled.")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("SLO snapshot job error: %s", exc)
        await asyncio.sleep(interval_seconds)

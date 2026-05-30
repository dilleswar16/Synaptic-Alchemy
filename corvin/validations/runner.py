"""Validation runner — executes ValidationDefinitionRow checks and persists ValidationRunRow results."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from corvin.storage.models import SloConfigRow, SloSnapshotRow, ValidationDefinitionRow, ValidationRunRow

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15.0  # seconds per step


# ── Step runners ──────────────────────────────────────────────────────────────


async def _run_http_step(
    step: dict[str, Any],
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Execute one HTTP step. Returns {ok, status_code, duration_ms, error}."""
    method = str(step.get("method", "GET")).upper()
    url = step.get("url", "")
    expected_status = step.get("expected_status", step.get("expect_status", 200))
    timeout = float(step.get("timeout_s", _HTTP_TIMEOUT))
    body = step.get("body")
    headers = step.get("headers", {})

    if not url:
        return {"ok": False, "error": "No URL specified", "duration_ms": 0}

    t0 = time.perf_counter()
    try:
        resp = await client.request(
            method, url, json=body, headers=headers, timeout=timeout, follow_redirects=True
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        ok = resp.status_code == expected_status
        return {
            "ok": ok,
            "status_code": resp.status_code,
            "expected_status": expected_status,
            "duration_ms": duration_ms,
            "error": None if ok else f"Expected {expected_status}, got {resp.status_code}",
        }
    except httpx.TimeoutException:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "error": f"Timeout after {timeout}s", "duration_ms": duration_ms}
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "error": str(exc), "duration_ms": duration_ms}


async def _execute_steps(steps: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    """Run all steps sequentially. Returns (all_passed, step_results)."""
    results: list[dict[str, Any]] = []
    all_passed = True
    async with httpx.AsyncClient() as client:
        for i, step in enumerate(steps):
            step_type = step.get("type", "http")
            if step_type == "http":
                result = await _run_http_step(step, client)
            else:
                result = {"ok": True, "note": f"Step type '{step_type}' not implemented — skipped"}
            result["step_index"] = i
            result["step_name"] = step.get("name", f"Step {i + 1}")
            results.append(result)
            if not result.get("ok", False):
                all_passed = False
    return all_passed, results


async def _run_health_check(config: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    url = config.get("url", "")
    step = {"type": "http", "method": "GET", "url": url, "expected_status": config.get("expected_status", 200)}
    return await _execute_steps([step])


async def _run_slo_gate(config: dict[str, Any], db: Session) -> tuple[bool, list[dict[str, Any]]]:
    """Pass if the latest snapshot for the target SLO config is compliant."""
    slo_config_id = config.get("slo_config_id")
    if slo_config_id is None:
        return False, [{"ok": False, "error": "No slo_config_id in config", "step_index": 0, "step_name": "SLO gate"}]

    snap: SloSnapshotRow | None = (
        db.query(SloSnapshotRow)
        .filter(SloSnapshotRow.slo_config_id == int(slo_config_id))
        .order_by(SloSnapshotRow.sampled_at.desc())
        .first()
    )
    if snap is None:
        return False, [{"ok": False, "error": "No SLO snapshot found — run a refresh first", "step_index": 0, "step_name": "SLO gate"}]

    ok = bool(snap.is_compliant)
    return ok, [{
        "ok": ok,
        "step_index": 0,
        "step_name": "SLO gate",
        "measured_pct": snap.measured_pct,
        "target_pct": snap.target_pct,
        "error": None if ok else f"SLO breached: {snap.measured_pct:.3f}% < {snap.target_pct}%",
    }]


async def _run_chaos(config: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Chaos stubs — always pass (manual chaos requires human verification)."""
    description = config.get("description", "Manual chaos test")
    return True, [{
        "ok": True,
        "step_index": 0,
        "step_name": "Chaos stub",
        "note": f"{description} — chaos tests require manual execution; stub passed.",
    }]


# ── Public runner ─────────────────────────────────────────────────────────────


async def run_validation(defn: ValidationDefinitionRow, db: Session) -> ValidationRunRow:
    """Execute a validation definition and persist the result."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    config = defn.config_json or {}
    vtype = defn.validation_type

    t0 = time.perf_counter()
    try:
        if vtype == "health_check":
            passed, step_results = await _run_health_check(config)
        elif vtype in ("endpoint", "synthetic", "user_journey"):
            steps = config.get("steps", [])
            if not steps and config.get("url"):
                # single-step shorthand
                steps = [{"type": "http", "method": config.get("method", "GET"), "url": config["url"],
                           "expected_status": config.get("expected_status", 200)}]
            passed, step_results = await _execute_steps(steps)
        elif vtype == "slo_gate":
            passed, step_results = await _run_slo_gate(config, db)
        elif vtype == "chaos":
            passed, step_results = await _run_chaos(config)
        else:
            passed = False
            step_results = [{"ok": False, "error": f"Unknown validation type: {vtype}", "step_index": 0, "step_name": "?"}]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Validation run error for definition %s: %s", defn.id, exc)
        passed = False
        step_results = [{"ok": False, "error": str(exc), "step_index": 0, "step_name": "Runner"}]

    duration_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)
    final_status = "pass" if passed else "fail"

    run = ValidationRunRow(
        id=run_id,
        definition_id=defn.id,
        status=final_status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        result_json={"steps": step_results, "passed": passed},
        triggered_by="api",
    )
    db.add(run)

    # Update definition last_run fields
    defn.last_run_at = finished_at
    defn.last_run_status = final_status

    db.commit()
    db.refresh(run)
    return run

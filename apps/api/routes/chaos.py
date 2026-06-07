"""Chaos Engineering API routes — Level-1 Kubernetes chaos experiment execution.

Lifecycle per experiment:
  POST /chaos/arm              → validate, preview commands, create ChaosRunRow (status=armed)
  POST /chaos/runs/{id}/execute → spawn background executor task (status=running)
  GET  /chaos/runs/{id}/status  → poll live status + output
  POST /chaos/runs/{id}/abort   → signal abort event → executor rolls back
  GET  /chaos/runs              → full run history (most recent first)

Experiment types (scenario_id prefix 'k8s_' = real kubectl execution):
  k8s_pod_kill          pod termination
  k8s_scale_down        replica reduction
  k8s_resource_pressure CPU/memory limit injection
  k8s_rollout_pause     deployment pause
  k8s_cascading         scale-to-zero cascade
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from corvin.storage.db import get_session as _get_session
from corvin.storage.models import ApplicationServiceRow, ChaosRunRow, SimulatorPresetRow
from corvin.execution.chaos_executor import (
    EXPERIMENT_CATALOGUE,
    build_commands,
    execute_experiment,
    signal_abort,
)

router = APIRouter()


def _db() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ArmRequest(BaseModel):
    """Request body for POST /chaos/arm."""
    preset_id: str
    environment: str = "dev"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_dict(run: ChaosRunRow) -> dict[str, Any]:
    return {
        "id": run.id,
        "preset_id": run.preset_id,
        "application_id": run.application_id,
        "service_name": run.service_name,
        "namespace": run.namespace,
        "experiment_type": run.experiment_type,
        "experiment_name": run.experiment_name,
        "parameters": run.parameters,
        "commands": run.commands,
        "rollback_commands": run.rollback_commands,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_seconds": run.duration_seconds,
        "output": run.output,
        "observations": run.observations,
        "rollback_status": run.rollback_status,
        "triggered_by": run.triggered_by,
        "created_at": run.created_at.isoformat(),
        # Experiment catalogue metadata
        "catalogue": EXPERIMENT_CATALOGUE.get(run.experiment_type, {}),
    }


def _resolve_k8s_info(service_name: str, db: Session) -> tuple[str, str, str]:
    """Return (deployment_name, namespace, k8s_label) for a service.

    Looks up ApplicationServiceRow for real values; falls back to
    convention-based defaults if the service isn't registered.
    """
    svc = db.query(ApplicationServiceRow).filter(
        ApplicationServiceRow.service_name == service_name
    ).first()

    if svc:
        namespace = svc.namespace or "chad"
        k8s_label = svc.k8s_app_label or f"chad-{service_name}"
        deployment = k8s_label  # k8s_app_label is the deployment name for CHAD
    else:
        namespace = "chad"
        k8s_label = f"chad-{service_name}"
        deployment = k8s_label

    return deployment, namespace, k8s_label


def _experiment_type_from_scenario(scenario_id: str) -> str | None:
    """Map scenario_id prefix to experiment_type. Returns None for alert-sim presets."""
    for etype in EXPERIMENT_CATALOGUE:
        if scenario_id.startswith(etype):
            return etype
    return None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/arm", status_code=201)
def arm_experiment(payload: ArmRequest, db: Session = Depends(_db)) -> dict[str, Any]:
    """Validate prerequisites, build command preview, create armed ChaosRunRow.

    Does NOT execute anything. Returns the run record with exact commands for
    operator review before the execute step.
    """
    preset = db.get(SimulatorPresetRow, payload.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Simulator preset not found")

    experiment_type = _experiment_type_from_scenario(preset.scenario_id)
    if experiment_type is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Preset '{preset.scenario_id}' is an alert simulation preset, not a Level-1 "
                "Kubernetes experiment. Use POST /triggers/simulate for alert simulations."
            ),
        )

    catalogue = EXPERIMENT_CATALOGUE[experiment_type]
    deployment, namespace, k8s_label = _resolve_k8s_info(preset.service_name, db)

    # Build parameters from preset + catalogue defaults
    params: dict[str, Any] = {
        "deployment": deployment,
        "k8s_label": k8s_label,
        "grace_period": 0,
        "target_replicas": 1,
        "cpu_limit": "50m",
        "memory_limit": "256Mi",
    }

    commands, rollback_commands = build_commands(
        experiment_type, deployment, namespace, k8s_label, params
    )

    run = ChaosRunRow(
        id=str(uuid.uuid4()),
        preset_id=preset.id,
        application_id=preset.application_id,
        service_name=preset.service_name,
        namespace=namespace,
        experiment_type=experiment_type,
        experiment_name=catalogue["name"],
        parameters=params,
        commands=commands,
        rollback_commands=rollback_commands,
        status="armed",
        duration_seconds=catalogue["duration_seconds"],
        output="",
        observations={},
        triggered_by="ui",
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _run_dict(run)


@router.post("/runs/{run_id}/execute")
async def execute_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(_db),
) -> dict[str, Any]:
    """Execute an armed chaos run. Spawns background task; returns immediately."""
    run = db.get(ChaosRunRow, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Chaos run not found")
    if run.status != "armed":
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}' — only 'armed' runs can be executed",
        )

    background_tasks.add_task(_run_background, run_id)
    return _run_dict(run)


async def _run_background(run_id: str) -> None:
    """Thin wrapper so BackgroundTasks can call the async executor."""
    await execute_experiment(run_id, _get_session)


@router.get("/runs/{run_id}/status")
def get_run_status(run_id: str, db: Session = Depends(_db)) -> dict[str, Any]:
    """Poll the current status, output, and observations for a run."""
    run = db.get(ChaosRunRow, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Chaos run not found")
    return _run_dict(run)


@router.post("/runs/{run_id}/abort")
def abort_run(run_id: str, db: Session = Depends(_db)) -> dict[str, Any]:
    """Signal the running experiment to abort and roll back immediately."""
    run = db.get(ChaosRunRow, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Chaos run not found")
    if run.status not in ("armed", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot abort run in status '{run.status}'",
        )

    signal_abort(run_id)

    if run.status == "armed":
        run.status = "aborted"
        run.completed_at = datetime.now(timezone.utc)
        run.rollback_status = "not_needed"
        db.commit()
        db.refresh(run)

    return _run_dict(run)


@router.get("/runs")
def list_runs(
    limit: int = Query(default=20, le=100),
    application_id: str | None = Query(default=None),
    db: Session = Depends(_db),
) -> list[dict[str, Any]]:
    """Return recent chaos run history, newest first."""
    q = db.query(ChaosRunRow)
    if application_id:
        q = q.filter(ChaosRunRow.application_id == application_id)
    runs = q.order_by(ChaosRunRow.created_at.desc()).limit(limit).all()
    return [_run_dict(r) for r in runs]


@router.get("/catalogue")
def get_catalogue() -> dict[str, Any]:
    """Return the full experiment catalogue — types, descriptions, hypotheses."""
    return {"experiments": EXPERIMENT_CATALOGUE}

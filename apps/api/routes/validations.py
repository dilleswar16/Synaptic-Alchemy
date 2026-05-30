"""Validations REST routes — CRUD for validation definitions and run triggers."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from corvin.storage.db import get_session as _get_session
from corvin.storage.models import ValidationDefinitionRow, ValidationRunRow

router = APIRouter()

_VALID_TYPES = {"health_check", "endpoint", "synthetic", "user_journey", "slo_gate", "chaos"}


def _db() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ValidationCreate(BaseModel):
    name: str
    description: str | None = None
    validation_type: str = "health_check"
    application_id: str | None = None
    config_json: dict[str, Any] = {}
    enabled: bool = True


class ValidationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    validation_type: str | None = None
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None


# ── Response helpers ──────────────────────────────────────────────────────────


def _run_dict(run: ValidationRunRow) -> dict[str, Any]:
    return {
        "id": run.id,
        "definition_id": run.definition_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "result_json": run.result_json,
        "triggered_by": run.triggered_by,
    }


def _defn_dict(defn: ValidationDefinitionRow, last_run: ValidationRunRow | None = None) -> dict[str, Any]:
    return {
        "id": defn.id,
        "application_id": defn.application_id,
        "name": defn.name,
        "description": defn.description,
        "validation_type": defn.validation_type,
        "config_json": defn.config_json,
        "enabled": defn.enabled,
        "last_run_at": defn.last_run_at.isoformat() if defn.last_run_at else None,
        "last_run_status": defn.last_run_status,
        "created_at": defn.created_at.isoformat(),
        "last_run": _run_dict(last_run) if last_run else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/")
def list_validations(
    app_id: str | None = Query(default=None, alias="app_id"),
    db: Session = Depends(_db),
) -> list[dict[str, Any]]:
    q = db.query(ValidationDefinitionRow)
    if app_id:
        q = q.filter(ValidationDefinitionRow.application_id == app_id)
    defns: list[ValidationDefinitionRow] = q.order_by(ValidationDefinitionRow.created_at.desc()).all()
    results = []
    for defn in defns:
        last_run = (
            db.query(ValidationRunRow)
            .filter(ValidationRunRow.definition_id == defn.id)
            .order_by(ValidationRunRow.started_at.desc())
            .first()
        )
        results.append(_defn_dict(defn, last_run))
    return results


@router.get("/{definition_id}")
def get_validation(definition_id: str, db: Session = Depends(_db)) -> dict[str, Any]:
    defn = db.get(ValidationDefinitionRow, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Validation not found")
    last_run = (
        db.query(ValidationRunRow)
        .filter(ValidationRunRow.definition_id == definition_id)
        .order_by(ValidationRunRow.started_at.desc())
        .first()
    )
    return _defn_dict(defn, last_run)


@router.post("/", status_code=201)
def create_validation(payload: ValidationCreate, db: Session = Depends(_db)) -> dict[str, Any]:
    if payload.validation_type not in _VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"validation_type must be one of {_VALID_TYPES}")
    defn = ValidationDefinitionRow(
        id=str(uuid.uuid4()),
        application_id=payload.application_id,
        name=payload.name,
        description=payload.description,
        validation_type=payload.validation_type,
        config_json=payload.config_json,
        enabled=payload.enabled,
        created_at=datetime.now(timezone.utc),
    )
    db.add(defn)
    db.commit()
    db.refresh(defn)
    return _defn_dict(defn)


@router.patch("/{definition_id}")
def update_validation(
    definition_id: str, payload: ValidationUpdate, db: Session = Depends(_db)
) -> dict[str, Any]:
    defn = db.get(ValidationDefinitionRow, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Validation not found")
    if payload.name is not None:
        defn.name = payload.name
    if payload.description is not None:
        defn.description = payload.description
    if payload.validation_type is not None:
        if payload.validation_type not in _VALID_TYPES:
            raise HTTPException(status_code=422, detail=f"validation_type must be one of {_VALID_TYPES}")
        defn.validation_type = payload.validation_type
    if payload.config_json is not None:
        defn.config_json = payload.config_json
    if payload.enabled is not None:
        defn.enabled = payload.enabled
    db.commit()
    db.refresh(defn)
    return _defn_dict(defn)


@router.delete("/{definition_id}", status_code=204)
def delete_validation(definition_id: str, db: Session = Depends(_db)) -> None:
    defn = db.get(ValidationDefinitionRow, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Validation not found")
    db.delete(defn)
    db.commit()


@router.post("/{definition_id}/run")
async def trigger_run(definition_id: str, db: Session = Depends(_db)) -> dict[str, Any]:
    """Execute a validation immediately (synchronous — waits for result)."""
    defn = db.get(ValidationDefinitionRow, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Validation not found")
    if not defn.enabled:
        raise HTTPException(status_code=409, detail="Validation is disabled")

    from corvin.validations.runner import run_validation
    run = await run_validation(defn, db)
    return _run_dict(run)


@router.get("/{definition_id}/history")
def get_run_history(
    definition_id: str,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(_db),
) -> list[dict[str, Any]]:
    defn = db.get(ValidationDefinitionRow, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Validation not found")
    runs: list[ValidationRunRow] = (
        db.query(ValidationRunRow)
        .filter(ValidationRunRow.definition_id == definition_id)
        .order_by(ValidationRunRow.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_run_dict(r) for r in runs]

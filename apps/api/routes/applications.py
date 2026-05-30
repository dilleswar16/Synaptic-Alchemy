"""Application Panel REST routes — CRUD for applications, services, connectors, and SLO configs."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from corvin.storage.db import get_session as _get_session
from corvin.storage.models import (
    ApplicationRow,
    ApplicationServiceRow,
    LogSourceRow,
    SloConfigRow,
    NotificationContactRow,
    OutboundConnectorRow,
)
from corvin.connectors.registry import ConnectorRegistry

router = APIRouter()
_registry = ConnectorRegistry()

_VALID_SOURCE_TYPES = {"azure_monitor", "elastic", "byoa", "aks"}
_VALID_CREDENTIAL_TYPES = {"db_encrypted", "kv_reference", "env_var"}
_VALID_SLI_TYPES = {"availability", "latency"}


# ── FastAPI session dependency ────────────────────────────────────────────────

def _db() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


# ── Pydantic I/O schemas ──────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    name: str
    description: str | None = None
    team_name: str | None = None
    environment_default: str = "dev"
    topology_json: dict[str, Any] = {}


class ApplicationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    team_name: str | None = None
    environment_default: str | None = None
    topology_json: dict[str, Any] | None = None


class ServiceCreate(BaseModel):
    service_name: str
    display_name: str | None = None
    namespace: str | None = None
    tier: str | None = None  # frontend|api|db|queue|worker
    dependencies: list[str] = []
    metadata_json: dict[str, Any] = {}
    k8s_app_label: str | None = None


class ServiceUpdate(BaseModel):
    display_name: str | None = None
    namespace: str | None = None
    tier: str | None = None
    dependencies: list[str] | None = None
    metadata_json: dict[str, Any] | None = None
    k8s_app_label: str | None = None


class ConnectorCreate(BaseModel):
    source_type: str
    display_name: str
    config_json: dict[str, Any] = {}
    credential_type: str = "env_var"
    # Provide ONE of these:
    credential_value: str | None = None  # plaintext — encrypted at rest when credential_type=db_encrypted
    credential_ref: str | None = None    # env var name or "vault_url|secret_name"

    @field_validator("source_type")
    @classmethod
    def _check_source_type(cls, v: str) -> str:
        if v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}")
        return v

    @field_validator("credential_type")
    @classmethod
    def _check_credential_type(cls, v: str) -> str:
        if v not in _VALID_CREDENTIAL_TYPES:
            raise ValueError(f"credential_type must be one of {sorted(_VALID_CREDENTIAL_TYPES)}")
        return v


class SloConfigCreate(BaseModel):
    service_name: str
    sli_type: str = "availability"
    target_pct: float = 99.9
    time_window_days: int = 30
    latency_threshold_ms: int | None = None
    enabled: bool = True

    @field_validator("sli_type")
    @classmethod
    def _check_sli_type(cls, v: str) -> str:
        if v not in _VALID_SLI_TYPES:
            raise ValueError(f"sli_type must be one of {sorted(_VALID_SLI_TYPES)}")
        return v


class SloConfigUpdate(BaseModel):
    target_pct: float | None = None
    time_window_days: int | None = None
    latency_threshold_ms: int | None = None
    enabled: bool | None = None


_VALID_CONTACT_METHODS = {"email", "phone", "teams"}
_VALID_PRIORITY_FILTERS = {"all", "p1_only", "p1_p2"}
_VALID_OUTBOUND_TYPES = {"teams_webhook", "servicenow", "email", "pagerduty"}


class NotificationContactCreate(BaseModel):
    contact_name: str
    method: str
    value: str
    priority_filter: str = "all"

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        if v not in _VALID_CONTACT_METHODS:
            raise ValueError(f"method must be one of {sorted(_VALID_CONTACT_METHODS)}")
        return v

    @field_validator("priority_filter")
    @classmethod
    def _check_priority(cls, v: str) -> str:
        if v not in _VALID_PRIORITY_FILTERS:
            raise ValueError(f"priority_filter must be one of {sorted(_VALID_PRIORITY_FILTERS)}")
        return v


class NotificationContactUpdate(BaseModel):
    contact_name: str | None = None
    method: str | None = None
    value: str | None = None
    priority_filter: str | None = None
    is_active: bool | None = None


class OutboundConnectorCreate(BaseModel):
    connector_type: str
    display_name: str
    config_json: dict[str, Any] = {}

    @field_validator("connector_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in _VALID_OUTBOUND_TYPES:
            raise ValueError(f"connector_type must be one of {sorted(_VALID_OUTBOUND_TYPES)}")
        return v


# ── Applications ──────────────────────────────────────────────────────────────

@router.get("/", summary="List all applications")
def list_applications(db: Session = Depends(_db)):
    return [_app_summary(r) for r in db.query(ApplicationRow).all()]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create application")
def create_application(body: ApplicationCreate, db: Session = Depends(_db)):
    row = ApplicationRow(id=str(uuid.uuid4()), **body.model_dump())
    db.add(row)
    db.flush()
    db.refresh(row)
    return _app_detail(row)


@router.get("/{app_id}", summary="Get application detail")
def get_application(app_id: str, db: Session = Depends(_db)):
    return _app_detail(_get_or_404(db, app_id))


@router.put("/{app_id}", summary="Update application")
def update_application(app_id: str, body: ApplicationUpdate, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(row)
    return _app_detail(row)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete application")
def delete_application(app_id: str, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    db.delete(row)


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/{app_id}/services", summary="List services")
def list_services(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_svc_dict(r) for r in db.query(ApplicationServiceRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/services", status_code=status.HTTP_201_CREATED, summary="Add service")
def add_service(app_id: str, body: ServiceCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = ApplicationServiceRow(application_id=app_id, **body.model_dump())
    db.add(row)
    db.flush()
    db.refresh(row)
    return _svc_dict(row)


@router.put("/{app_id}/services/{svc_id}", summary="Update service")
def update_service(app_id: str, svc_id: int, body: ServiceUpdate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(ApplicationServiceRow, svc_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Service not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.flush()
    db.refresh(row)
    return _svc_dict(row)


@router.delete("/{app_id}/services/{svc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(app_id: str, svc_id: int, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(ApplicationServiceRow, svc_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(row)


# ── Connectors ────────────────────────────────────────────────────────────────

@router.get("/{app_id}/connectors", summary="List connectors")
def list_connectors(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_mask_connector(r) for r in db.query(LogSourceRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/connectors", status_code=status.HTTP_201_CREATED, summary="Add connector")
def add_connector(app_id: str, body: ConnectorCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    credential_ref = _store_credential(body)
    row = LogSourceRow(
        id=str(uuid.uuid4()),
        application_id=app_id,
        source_type=body.source_type,
        display_name=body.display_name,
        config_json=body.config_json,
        credential_type=body.credential_type,
        credential_ref=credential_ref,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return _mask_connector(row)


@router.delete("/{app_id}/connectors/{src_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(app_id: str, src_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(LogSourceRow, src_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Connector not found")
    db.delete(row)


@router.post("/{app_id}/connectors/{src_id}/test", summary="Test connector connectivity")
def test_connector(app_id: str, src_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(LogSourceRow, src_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Connector not found")
    connector = _registry.get_connector(row)
    if connector is None:
        raise HTTPException(status_code=400, detail=f"Unknown source_type: {row.source_type!r}")
    result = connector.test_connection()
    row.last_tested_at = datetime.now(timezone.utc)
    row.test_status = "ok" if result.ok else "error"
    row.test_message = result.message
    db.flush()
    return {"ok": result.ok, "message": result.message, "latency_ms": result.latency_ms}


# ── SLO Configs ───────────────────────────────────────────────────────────────

@router.get("/{app_id}/slo-configs", summary="List SLO configurations")
def list_slo_configs(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_slo_dict(r) for r in db.query(SloConfigRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/slo-configs", status_code=status.HTTP_201_CREATED, summary="Add SLO config")
def add_slo_config(app_id: str, body: SloConfigCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = SloConfigRow(application_id=app_id, **body.model_dump())
    db.add(row)
    db.flush()
    db.refresh(row)
    return _slo_dict(row)


@router.put("/{app_id}/slo-configs/{cfg_id}", summary="Update SLO config")
def update_slo_config(app_id: str, cfg_id: int, body: SloConfigUpdate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(SloConfigRow, cfg_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="SLO config not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.flush()
    db.refresh(row)
    return _slo_dict(row)


@router.delete("/{app_id}/slo-configs/{cfg_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slo_config(app_id: str, cfg_id: int, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(SloConfigRow, cfg_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="SLO config not found")
    db.delete(row)


# ── Notification Contacts ─────────────────────────────────────────────────────

@router.get("/{app_id}/notification-contacts", summary="List notification contacts")
def list_notification_contacts(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_contact_dict(r) for r in db.query(NotificationContactRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/notification-contacts", status_code=status.HTTP_201_CREATED, summary="Add notification contact")
def add_notification_contact(app_id: str, body: NotificationContactCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = NotificationContactRow(application_id=app_id, **body.model_dump())
    db.add(row)
    db.flush()
    db.refresh(row)
    return _contact_dict(row)


@router.put("/{app_id}/notification-contacts/{contact_id}", summary="Update notification contact")
def update_notification_contact(app_id: str, contact_id: int, body: NotificationContactUpdate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(NotificationContactRow, contact_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Notification contact not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.flush()
    db.refresh(row)
    return _contact_dict(row)


@router.delete("/{app_id}/notification-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_contact(app_id: str, contact_id: int, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(NotificationContactRow, contact_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Notification contact not found")
    db.delete(row)


# ── Outbound Connectors ───────────────────────────────────────────────────────

@router.get("/{app_id}/outbound-connectors", summary="List outbound connectors")
def list_outbound_connectors(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_outbound_dict(r) for r in db.query(OutboundConnectorRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/outbound-connectors", status_code=status.HTTP_201_CREATED, summary="Add outbound connector")
def add_outbound_connector(app_id: str, body: OutboundConnectorCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = OutboundConnectorRow(
        id=str(uuid.uuid4()),
        application_id=app_id,
        **body.model_dump(),
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return _outbound_dict(row)


@router.delete("/{app_id}/outbound-connectors/{conn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outbound_connector(app_id: str, conn_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(OutboundConnectorRow, conn_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Outbound connector not found")
    db.delete(row)


# ── Config migration ──────────────────────────────────────────────────────────

@router.post("/migrate-from-yaml", summary="One-time YAML → Application Panel migration")
def migrate_from_yaml(db: Session = Depends(_db)):
    from corvin.cli.migrate_config import run_migration
    return run_migration(db)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, app_id: str) -> ApplicationRow:
    row = db.get(ApplicationRow, app_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Application {app_id!r} not found")
    return row


def _store_credential(body: ConnectorCreate) -> str | None:
    if body.credential_type == "db_encrypted" and body.credential_value:
        from corvin.connectors.crypto import encrypt
        return encrypt(body.credential_value)
    if body.credential_type in ("kv_reference", "env_var") and body.credential_ref:
        return body.credential_ref
    return None


def _mask_connector(row: LogSourceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "source_type": row.source_type,
        "display_name": row.display_name,
        "config_json": row.config_json,
        "credential_type": row.credential_type,
        "credential_ref": "***" if row.credential_ref else None,  # never expose stored secrets
        "is_active": row.is_active,
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "test_status": row.test_status,
        "test_message": row.test_message,
        "created_at": row.created_at.isoformat(),
    }


def _app_summary(row: ApplicationRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "team_name": row.team_name,
        "environment_default": row.environment_default,
        "service_count": len(row.services),
        "connector_count": len(row.log_sources),
        "slo_count": len(row.slo_configs),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _app_detail(row: ApplicationRow) -> dict[str, Any]:
    return {
        **_app_summary(row),
        "topology_json": row.topology_json,
        "services": [_svc_dict(s) for s in row.services],
        "log_sources": [_mask_connector(c) for c in row.log_sources],
        "slo_configs": [_slo_dict(s) for s in row.slo_configs],
        "notification_contacts": [_contact_dict(c) for c in row.notification_contacts],
        "outbound_connectors": [_outbound_dict(c) for c in row.outbound_connectors],
    }


def _svc_dict(row: ApplicationServiceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "service_name": row.service_name,
        "display_name": row.display_name,
        "namespace": row.namespace,
        "tier": row.tier,
        "dependencies": row.dependencies,
        "metadata_json": row.metadata_json,
        "k8s_app_label": row.k8s_app_label,
    }


def _slo_dict(row: SloConfigRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "service_name": row.service_name,
        "sli_type": row.sli_type,
        "target_pct": row.target_pct,
        "time_window_days": row.time_window_days,
        "latency_threshold_ms": row.latency_threshold_ms,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat(),
    }


def _contact_dict(row: NotificationContactRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "contact_name": row.contact_name,
        "method": row.method,
        "value": row.value,
        "priority_filter": row.priority_filter,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat(),
    }


def _outbound_dict(row: OutboundConnectorRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "connector_type": row.connector_type,
        "display_name": row.display_name,
        "config_json": row.config_json,
        "is_active": row.is_active,
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "test_status": row.test_status,
        "test_message": row.test_message,
        "created_at": row.created_at.isoformat(),
    }

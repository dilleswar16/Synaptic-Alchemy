"""Application Panel REST routes — CRUD for applications, services, connectors, and SLO configs."""
from __future__ import annotations

import uuid
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, model_validator, field_validator
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
from corvin.connectors.crypto import encrypt as _encrypt_token
from corvin.connectors.config_resolver import (
    infer_connector_role,
    ROLE_APIM_LOGS,
    ROLE_CONTAINER_INSIGHTS,
    ROLE_AZURE_ACTIVITY,
)
from corvin.delivery.outbound_connectors import test_outbound_connector

router = APIRouter()
_registry = ConnectorRegistry()

_VALID_SOURCE_TYPES = {"azure_monitor", "elastic", "byoa", "aks"}
_VALID_CREDENTIAL_TYPES = {"db_encrypted", "kv_reference", "env_var"}
_VALID_SLI_TYPES = {"availability", "latency"}
_VALID_AZURE_MONITOR_ROLES = {ROLE_APIM_LOGS, ROLE_CONTAINER_INSIGHTS, ROLE_AZURE_ACTIVITY}


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
    git_provider: str | None = None  # azure_devops | github
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_token: str | None = None  # plaintext PAT — encrypted before storage

    @field_validator("git_provider")
    @classmethod
    def _check_git_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("azure_devops", "github"):
            raise ValueError("git_provider must be 'azure_devops' or 'github'")
        return v


class ApplicationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    team_name: str | None = None
    environment_default: str | None = None
    topology_json: dict[str, Any] | None = None
    git_provider: str | None = None
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_token: str | None = None  # plaintext PAT — encrypted before storage

    @field_validator("git_provider")
    @classmethod
    def _check_git_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("azure_devops", "github"):
            raise ValueError("git_provider must be 'azure_devops' or 'github'")
        return v


class ServiceCreate(BaseModel):
    service_name: str
    display_name: str | None = None
    namespace: str | None = None
    tier: str | None = None  # frontend|api|db|queue|worker
    dependencies: list[str] = []
    metadata_json: dict[str, Any] = {}
    k8s_app_label: str | None = None
    git_provider: str | None = None  # azure_devops | github
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_token: str | None = None  # plaintext PAT — encrypted before storage

    @field_validator("git_provider")
    @classmethod
    def _check_git_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("azure_devops", "github"):
            raise ValueError("git_provider must be 'azure_devops' or 'github'")
        return v


class ServiceUpdate(BaseModel):
    display_name: str | None = None
    namespace: str | None = None
    tier: str | None = None
    dependencies: list[str] | None = None
    metadata_json: dict[str, Any] | None = None
    k8s_app_label: str | None = None
    git_provider: str | None = None
    git_repo_url: str | None = None
    git_branch: str | None = None
    git_token: str | None = None

    @field_validator("git_provider")
    @classmethod
    def _check_git_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("azure_devops", "github"):
            raise ValueError("git_provider must be 'azure_devops' or 'github'")
        return v


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

    @model_validator(mode="after")
    def _validate_connector_shape(self) -> ConnectorCreate:
        _validate_connector_payload(self.source_type, self.config_json)
        return self


class ConnectorUpdate(BaseModel):
    source_type: str | None = None
    display_name: str | None = None
    config_json: dict[str, Any] | None = None
    credential_type: str | None = None
    credential_value: str | None = None
    credential_ref: str | None = None

    @field_validator("source_type")
    @classmethod
    def _check_source_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}")
        return v

    @field_validator("credential_type")
    @classmethod
    def _check_credential_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_CREDENTIAL_TYPES:
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
_VALID_OUTBOUND_TYPES = {
    "teams_webhook",
    "servicenow",
    "email",
    "pagerduty",
    "generic_http",
    "azure_devops_boards",
    "azure_devops_wiki",
    "sharepoint",
}

# Per-type field schema used as hints (frontend reads this via /meta endpoint if needed)
CONNECTOR_FIELD_SCHEMA: dict[str, dict] = {
    "teams_webhook": {"endpoint": "Webhook URL"},
    "servicenow": {"endpoint": "Instance URL (https://instance.service-now.com)", "table": "Table (default: incident)"},
    "email": {"endpoint": "SMTP host or API endpoint", "port": "SMTP port", "from": "From address"},
    "pagerduty": {"endpoint": "Events API URL (https://events.pagerduty.com/v2/enqueue)"},
    "generic_http": {"endpoint": "Endpoint URL", "http_method": "HTTP method (POST/PUT/PATCH/GET)"},
    "azure_devops_boards": {
        "endpoint": "Azure DevOps org URL (https://dev.azure.com/<org>)",
        "project_name": "Project name",
        "work_item_type": "Work item type (default: Issue)",
    },
    "azure_devops_wiki": {
        "endpoint": "Azure DevOps org URL (https://dev.azure.com/<org>)",
        "project_name": "Project name",
        "wiki_id": "Wiki id or slug (or 'auto')",
    },
    "sharepoint": {
        "endpoint": "SharePoint site URL",
        "site_id": "SharePoint site id",
        "drive_id": "Document library drive id (or 'auto')",
        "folder_path": "Folder path",
    },
}


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


class OutboundConnectorUpdate(BaseModel):
    connector_type: str | None = None
    display_name: str | None = None
    config_json: dict[str, Any] | None = None

    @field_validator("connector_type")
    @classmethod
    def _check_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_OUTBOUND_TYPES:
            raise ValueError(f"connector_type must be one of {sorted(_VALID_OUTBOUND_TYPES)}")
        return v


_BOOTSTRAP_OUTBOUND_TYPES = {
    "teams_webhook",
    "email",
    "azure_devops_boards",
    "azure_devops_wiki",
    "sharepoint",
}


class OutboundBootstrapRequest(BaseModel):
    include_types: list[str] | None = None
    overwrite_existing: bool = True

    @field_validator("include_types")
    @classmethod
    def _check_include_types(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        bad = [item for item in v if item not in _BOOTSTRAP_OUTBOUND_TYPES]
        if bad:
            raise ValueError(
                f"include_types supports only {sorted(_BOOTSTRAP_OUTBOUND_TYPES)}; got invalid {bad}"
            )
        return v


# ── Applications ──────────────────────────────────────────────────────────────

@router.get("/", summary="List all applications")
def list_applications(db: Session = Depends(_db)):
    return [_app_summary(r) for r in db.query(ApplicationRow).all()]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create application")
def create_application(body: ApplicationCreate, db: Session = Depends(_db)):
    data = body.model_dump(exclude={"git_token"})
    if body.git_token:
        data["git_token_encrypted"] = _encrypt_token(body.git_token)
    row = ApplicationRow(id=str(uuid.uuid4()), **data)
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
    data = body.model_dump(exclude_none=True, exclude={"git_token"})
    if body.git_token is not None:
        data["git_token_encrypted"] = _encrypt_token(body.git_token)
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(row)
    return _app_detail(row)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete application")
def delete_application(app_id: str, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    db.delete(row)


# ── Git Config ────────────────────────────────────────────────────────────────

class GitConfigUpdate(BaseModel):
    git_provider: str  # azure_devops | github
    git_repo_url: str
    git_branch: str = "main"
    git_token: str  # plaintext PAT — encrypted before storage

    @field_validator("git_provider")
    @classmethod
    def _check_provider(cls, v: str) -> str:
        if v not in ("azure_devops", "github"):
            raise ValueError("git_provider must be 'azure_devops' or 'github'")
        return v


@router.put("/{app_id}/git-config", summary="Set or update Git repository config")
def update_git_config(app_id: str, body: GitConfigUpdate, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    row.git_provider = body.git_provider
    row.git_repo_url = body.git_repo_url
    row.git_branch = body.git_branch
    row.git_token_encrypted = _encrypt_token(body.git_token)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(row)
    return {
        "provider": row.git_provider,
        "repo_url": row.git_repo_url,
        "branch": row.git_branch,
        "has_token": True,
    }


@router.get("/{app_id}/git-config/test", summary="Test Git repository connectivity")
def test_git_config(app_id: str, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    if not row.git_provider or not row.git_repo_url or not row.git_token_encrypted:
        raise HTTPException(status_code=400, detail="Git config not configured for this application")

    from corvin.connectors.git_repo import GitRepoConnector

    connector = GitRepoConnector(
        provider=row.git_provider,
        repo_url=row.git_repo_url,
        branch=row.git_branch or "main",
        token_encrypted=row.git_token_encrypted,
    )
    try:
        files = connector.list_directory("")
        return {"status": "ok", "files_found": len(files), "sample": files[:5]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Git connectivity failed: {exc}")


@router.delete("/{app_id}/git-config", status_code=status.HTTP_204_NO_CONTENT, summary="Remove Git config")
def delete_git_config(app_id: str, db: Session = Depends(_db)):
    row = _get_or_404(db, app_id)
    row.git_provider = None
    row.git_repo_url = None
    row.git_branch = None
    row.git_token_encrypted = None
    row.updated_at = datetime.now(timezone.utc)
    db.flush()


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/{app_id}/services", summary="List services")
def list_services(app_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    return [_svc_dict(r) for r in db.query(ApplicationServiceRow).filter_by(application_id=app_id).all()]


@router.post("/{app_id}/services", status_code=status.HTTP_201_CREATED, summary="Add service")
def add_service(app_id: str, body: ServiceCreate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    data = body.model_dump(exclude={"git_token"})
    if body.git_token:
        data["git_token_encrypted"] = _encrypt_token(body.git_token)
    row = ApplicationServiceRow(application_id=app_id, **data)
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
    data = body.model_dump(exclude_none=True, exclude={"git_token"})
    if body.git_token:
        data["git_token_encrypted"] = _encrypt_token(body.git_token)
    for k, v in data.items():
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
    config_json = _normalize_connector_config(body.source_type, body.display_name, body.config_json)
    row = LogSourceRow(
        id=str(uuid.uuid4()),
        application_id=app_id,
        source_type=body.source_type,
        display_name=body.display_name,
        config_json=config_json,
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


@router.put("/{app_id}/connectors/{src_id}", summary="Update connector")
def update_connector(app_id: str, src_id: str, body: ConnectorUpdate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(LogSourceRow, src_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Connector not found")

    data = body.model_dump(exclude_none=True)
    if "credential_type" in data:
        row.credential_type = data["credential_type"]
    if "credential_value" in data or "credential_ref" in data or "credential_type" in data:
        effective_type = data.get("credential_type", row.credential_type)
        effective_value = data.get("credential_value")
        effective_ref = data.get("credential_ref")
        if effective_type == "db_encrypted" and effective_value:
            from corvin.connectors.crypto import encrypt
            row.credential_ref = encrypt(effective_value)
        elif effective_type in ("kv_reference", "env_var") and effective_ref is not None:
            row.credential_ref = effective_ref

    for k in ("source_type", "display_name", "config_json"):
        if k in data:
            setattr(row, k, data[k])

    row.config_json = _normalize_connector_config(row.source_type, row.display_name, row.config_json)
    _validate_connector_payload(row.source_type, row.config_json)

    db.flush()
    db.refresh(row)
    return _mask_connector(row)


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


@router.put("/{app_id}/outbound-connectors/{conn_id}", summary="Update outbound connector")
def update_outbound_connector(app_id: str, conn_id: str, body: OutboundConnectorUpdate, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(OutboundConnectorRow, conn_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Outbound connector not found")
    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.flush()
    db.refresh(row)
    return _outbound_dict(row)


@router.post("/{app_id}/outbound-connectors/{conn_id}/test", summary="Test outbound connector connectivity")
def test_outbound_connector_route(app_id: str, conn_id: str, db: Session = Depends(_db)):
    _get_or_404(db, app_id)
    row = db.get(OutboundConnectorRow, conn_id)
    if not row or row.application_id != app_id:
        raise HTTPException(status_code=404, detail="Outbound connector not found")
    result = test_outbound_connector(row.connector_type, row.display_name, row.config_json or {})
    row.last_tested_at = datetime.now(timezone.utc)
    row.test_status = "ok" if result.ok else "error"
    row.test_message = result.message
    db.flush()
    return {"ok": result.ok, "message": result.message, "latency_ms": result.latency_ms}


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


def _normalize_connector_config(source_type: str, display_name: str, config_json: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(config_json or {})
    role = infer_connector_role(source_type, cfg, display_name)
    if role and not cfg.get("connector_role"):
        cfg["connector_role"] = role
    if source_type == "aks":
        return _normalize_aks_config(cfg)
    if source_type == "azure_monitor":
        cfg = _normalize_azure_monitor_config(cfg)
    return cfg


def _normalize_aks_config(config_json: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config_json)
    for key in ("cluster_name", "resource_group", "subscription_id", "tenant_id", "kube_config_path"):
        if key in cfg and cfg[key] is not None:
            value = str(cfg[key]).strip()
            if value:
                cfg[key] = value
            else:
                cfg.pop(key, None)

    namespaces = _normalize_namespaces(cfg.get("namespaces"), cfg.get("default_namespace"))
    cfg["namespaces"] = namespaces
    cfg["default_namespace"] = namespaces[0]

    clusters_raw = cfg.get("clusters")
    if isinstance(clusters_raw, list):
        normalized_clusters: list[dict[str, Any]] = []
        for item in clusters_raw:
            if not isinstance(item, dict):
                continue
            cluster: dict[str, Any] = {}
            for key in ("cluster_name", "resource_group", "subscription_id", "tenant_id", "kube_config_path"):
                value = item.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    cluster[key] = text
            cluster["in_cluster"] = bool(item.get("in_cluster", False))
            cluster_namespaces = _normalize_namespaces(item.get("namespaces"), item.get("default_namespace") or cfg["default_namespace"])
            cluster["namespaces"] = cluster_namespaces
            cluster["default_namespace"] = cluster_namespaces[0]

            if not cluster.get("cluster_name"):
                continue
            normalized_clusters.append(cluster)

        if normalized_clusters:
            cfg["clusters"] = normalized_clusters
        else:
            cfg.pop("clusters", None)
    return cfg


def _normalize_azure_monitor_config(config_json: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config_json)
    role = str(cfg.get("connector_role", "")).strip()
    workspace_id = str(cfg.get("workspace_id", "")).strip()
    if workspace_id:
        cfg["workspace_id"] = workspace_id
    for key in ("subscription_id", "resource_group", "tenant_id", "apim_service_name", "cluster_name", "default_namespace"):
        if key in cfg and cfg[key] is not None:
            value = str(cfg[key]).strip()
            if value:
                cfg[key] = value
            else:
                cfg.pop(key, None)
    if role == ROLE_APIM_LOGS:
        cfg.setdefault("apim_table", "ApiManagementGatewayLogs")
    if role == ROLE_CONTAINER_INSIGHTS:
        namespaces = _normalize_namespaces(cfg.get("namespaces"), cfg.get("default_namespace"))
        cfg["namespaces"] = namespaces
        cfg["default_namespace"] = namespaces[0]
    if role == ROLE_AZURE_ACTIVITY:
        cfg.setdefault("activity_table", "AzureActivity")
        cfg.setdefault("default_time_range_minutes", 60)
        cfg.setdefault("max_events", 100)
    return cfg


def _validate_connector_payload(source_type: str, config_json: dict[str, Any] | None) -> None:
    cfg = dict(config_json or {})
    if source_type == "aks":
        clusters = cfg.get("clusters") if isinstance(cfg.get("clusters"), list) else []
        if clusters:
            for idx, cluster in enumerate(clusters):
                if not isinstance(cluster, dict):
                    raise ValueError(f"aks clusters[{idx}] must be an object")
                if not str(cluster.get("cluster_name", "")).strip():
                    raise ValueError(f"aks clusters[{idx}] requires cluster_name")
                if not str(cluster.get("resource_group", "")).strip():
                    raise ValueError(f"aks clusters[{idx}] requires resource_group")
                if not str(cluster.get("subscription_id", "")).strip():
                    raise ValueError(f"aks clusters[{idx}] requires subscription_id")
                ns_list = _normalize_namespaces(cluster.get("namespaces"), cluster.get("default_namespace"))
                if not ns_list:
                    raise ValueError(f"aks clusters[{idx}] requires at least one namespace")
        else:
            cluster_name = str(cfg.get("cluster_name", "")).strip()
            resource_group = str(cfg.get("resource_group", "")).strip()
            subscription_id = str(cfg.get("subscription_id", "")).strip()
            if not cluster_name:
                raise ValueError("aks connector requires cluster_name")
            if not resource_group:
                raise ValueError("aks connector requires resource_group")
            if not subscription_id:
                raise ValueError("aks connector requires subscription_id")
        namespaces = _normalize_namespaces(cfg.get("namespaces"), cfg.get("default_namespace"))
        if not namespaces:
            raise ValueError("aks connector requires at least one namespace")
        return

    if source_type != "azure_monitor":
        return

    role = str(cfg.get("connector_role", "")).strip()
    if role not in _VALID_AZURE_MONITOR_ROLES:
        raise ValueError(
            f"azure_monitor connector_role must be one of {sorted(_VALID_AZURE_MONITOR_ROLES)}"
        )

    workspace_id = str(cfg.get("workspace_id", "")).strip()
    if not workspace_id:
        raise ValueError("azure_monitor workspace_id is required")

    if role == ROLE_APIM_LOGS:
        return

    if role == ROLE_CONTAINER_INSIGHTS:
        cluster_name = str(cfg.get("cluster_name", "")).strip()
        if not cluster_name:
            raise ValueError("container_insights connector requires cluster_name")
        namespaces = _normalize_namespaces(cfg.get("namespaces"), cfg.get("default_namespace"))
        if not namespaces:
            raise ValueError("container_insights connector requires at least one namespace")
        return

    if role == ROLE_AZURE_ACTIVITY:
        return


def _normalize_namespaces(value: Any, fallback: Any = None) -> list[str]:
    values: list[str] = []

    if isinstance(value, list):
        values = [str(v).strip() for v in value if str(v).strip()]
    elif isinstance(value, str):
        values = [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]

    if not values:
        fb = str(fallback or "").strip()
        if fb:
            values = [fb]

    if not values:
        values = ["default"]

    deduped: list[str] = []
    seen: set[str] = set()
    for ns in values:
        key = ns.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ns)
    return deduped


@router.post("/{app_id}/outbound-connectors/bootstrap", summary="Bootstrap default outbound connectors for an application")
def bootstrap_outbound_connectors(
    app_id: str,
    body: OutboundBootstrapRequest | None = Body(default=None),
    db: Session = Depends(_db),
):
    _get_or_404(db, app_id)

    include_types = set((body.include_types if body and body.include_types else sorted(_BOOTSTRAP_OUTBOUND_TYPES)))
    overwrite_existing = body.overwrite_existing if body is not None else True

    org = str(os.environ.get("AZURE_DEVOPS_ORG", "")).strip()
    project = str(os.environ.get("AZURE_DEVOPS_PROJECT", "")).strip()
    pat = str(os.environ.get("AZURE_DEVOPS_PAT", "")).strip()
    teams_webhook = str(os.environ.get("TEAMS_WEBHOOK_URL", "")).strip()
    email_host = str(os.environ.get("CORVIN_SMTP_HOST", "smtp.office365.com")).strip() or "smtp.office365.com"
    email_from = str(os.environ.get("CORVIN_EMAIL_FROM", "")).strip()
    email_to = str(os.environ.get("CORVIN_EMAIL_TO", "")).strip()
    email_user = str(os.environ.get("CORVIN_SMTP_USERNAME", "")).strip()
    email_pass = str(os.environ.get("CORVIN_SMTP_PASSWORD", "")).strip()
    sharepoint_site_id = str(os.environ.get("SHAREPOINT_SITE_ID", "")).strip()

    ado_endpoint = f"https://dev.azure.com/{org}" if org else "https://dev.azure.com/your-org"
    sharepoint_endpoint = "https://yourtenant.sharepoint.com/sites/your-site"
    if sharepoint_site_id:
        host = sharepoint_site_id.split(",", 1)[0].strip()
        if host:
            if host.startswith("http://") or host.startswith("https://"):
                sharepoint_endpoint = host
            else:
                sharepoint_endpoint = f"https://{host}"

    defaults: dict[str, dict[str, Any]] = {
        "teams_webhook": {
            "display_name": "Microsoft Teams",
            "config_json": {
                "endpoint": teams_webhook or "https://placeholder.webhook.office.com/webhookb2/placeholder",
                "endpoint_fields": {"http_method": "POST"},
                "auth": {"type": "none"},
                "variables": [
                    {"key": "title", "default_value": "Corvin Alert: {{service_name}}"},
                    {"key": "summary", "default_value": "{{rca_summary}}"},
                    {"key": "severity_color", "default_value": "FF0000"},
                ],
                "payload_template": "{}",
            },
        },
        "email": {
            "display_name": "Corvin Email Delivery",
            "config_json": {
                "endpoint": email_host,
                "endpoint_fields": {"port": "587", "from": email_from},
                "auth": {
                    "type": "basic" if email_user and email_pass else "none",
                    "username": email_user,
                    "password": email_pass,
                },
                "variables": [
                    {"key": "to", "default_value": email_to},
                    {"key": "title", "default_value": "[Corvin] {{service_name}} alert"},
                    {"key": "summary", "default_value": "{{rca_summary}}"},
                ],
                "payload_template": "{}",
            },
        },
        "azure_devops_boards": {
            "display_name": "Azure DevOps Boards",
            "config_json": {
                "endpoint": ado_endpoint,
                "endpoint_fields": {
                    "project_name": project,
                    "work_item_type": "Issue",
                    "http_method": "GET",
                },
                "auth": {
                    "type": "api_key" if pat else "none",
                    "api_key": pat,
                    "api_key_header": "X-API-Key",
                },
                "variables": [{"key": "tags", "default_value": "corvin;{{environment}};{{service_name}}"}],
                "payload_template": "{}",
            },
        },
        "azure_devops_wiki": {
            "display_name": "Azure DevOps Wiki",
            "config_json": {
                "endpoint": ado_endpoint,
                "endpoint_fields": {
                    "project_name": project,
                    "wiki_id": "auto",
                    "http_method": "GET",
                },
                "auth": {
                    "type": "api_key" if pat else "none",
                    "api_key": pat,
                    "api_key_header": "X-API-Key",
                },
                "variables": [{"key": "section", "default_value": "Investigations"}],
                "payload_template": "{}",
            },
        },
        "sharepoint": {
            "display_name": "SharePoint RCA Library",
            "config_json": {
                "endpoint": sharepoint_endpoint,
                "endpoint_fields": {
                    "site_id": sharepoint_site_id,
                    "drive_id": "auto",
                    "folder_path": "Corvin/Investigations",
                    "http_method": "GET",
                },
                "auth": {"type": "none"},
                "variables": [{"key": "folder_hint", "default_value": "{{environment}}/{{service_name}}"}],
                "payload_template": "{}",
            },
        },
    }

    inserted = 0
    updated = 0
    results: list[dict[str, str]] = []
    for connector_type, payload in defaults.items():
        if connector_type not in include_types:
            continue
        row = db.query(OutboundConnectorRow).filter_by(
            application_id=app_id,
            connector_type=connector_type,
        ).first()
        if row is None:
            row = OutboundConnectorRow(
                id=str(uuid.uuid4()),
                application_id=app_id,
                connector_type=connector_type,
                display_name=str(payload["display_name"]),
                config_json=dict(payload["config_json"]),
                is_active=True,
            )
            db.add(row)
            inserted += 1
            action = "inserted"
        else:
            if not overwrite_existing:
                results.append({"connector_type": connector_type, "action": "skipped"})
                continue
            row.display_name = str(payload["display_name"])
            row.config_json = dict(payload["config_json"])
            row.is_active = True
            updated += 1
            action = "updated"
        results.append({"connector_type": connector_type, "action": action})

    db.flush()
    return {
        "status": "ok",
        "application_id": app_id,
        "inserted": inserted,
        "updated": updated,
        "overwrite_existing": overwrite_existing,
        "connectors": results,
    }


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
        "git_config": {
            "provider": row.git_provider,
            "repo_url": row.git_repo_url,
            "branch": row.git_branch,
            "has_token": row.git_token_encrypted is not None,
        },
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
        "git_provider": row.git_provider,
        "git_repo_url": row.git_repo_url,
        "git_branch": row.git_branch,
        "has_git_token": row.git_token_encrypted is not None,
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

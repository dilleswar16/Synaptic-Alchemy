"""Validations REST routes — CRUD for validation definitions and run triggers."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from corvin.storage.db import get_session as _get_session
from corvin.storage.models import ValidationAutomationPolicyRow, ValidationDefinitionRow, ValidationRunRow

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


class DryRunRequest(BaseModel):
    """Run a journey config without persisting — for testing in the builder."""
    config_json: dict[str, Any]
    validation_type: str = "user_journey"


class PlaywrightGenerateRequest(BaseModel):
    """Generate a Playwright test script from a journey config."""
    config_json: dict[str, Any]
    name: str = "User Journey Test"


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


# ── Automation Policy schemas ─────────────────────────────────────────────────


class AutomationPolicyCreate(BaseModel):
    service_name: str
    alert_type: str
    min_confidence_pct: float = 70.0
    validation_definition_id: str
    enabled: bool = True


class AutomationPolicyUpdate(BaseModel):
    service_name: str | None = None
    alert_type: str | None = None
    min_confidence_pct: float | None = None
    validation_definition_id: str | None = None
    enabled: bool | None = None


# ── Dry Run & Playwright (BEFORE parameterized routes) ────────────────────────


@router.post("/dry-run")
async def dry_run_validation(payload: DryRunRequest) -> dict[str, Any]:
    """Execute a validation config without persisting — used by the journey builder."""
    from corvin.validations.runner import _execute_steps, _run_health_check

    config = payload.config_json
    vtype = payload.validation_type

    import time
    t0 = time.perf_counter()

    if vtype == "health_check":
        passed, step_results = await _run_health_check(config)
    elif vtype in ("endpoint", "synthetic", "user_journey"):
        steps = config.get("steps", [])
        auth_config = config.get("auth")
        base_url = config.get("base_url", "")
        abort_on_failure = config.get("abort_on_failure", True)
        passed, step_results = await _execute_steps(steps, auth_config, base_url, abort_on_failure)
    else:
        passed = False
        step_results = [{"ok": False, "error": f"Dry-run not supported for type: {vtype}", "step_index": 0, "step_name": "?"}]

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "passed": passed,
        "duration_ms": duration_ms,
        "steps": step_results,
    }


@router.post("/generate-playwright")
def generate_playwright_script(payload: PlaywrightGenerateRequest) -> dict[str, Any]:
    """Generate a Playwright test script from a user journey config."""
    config = payload.config_json
    steps = config.get("steps", [])
    base_url = config.get("base_url", "")
    auth_config = config.get("auth")
    name = payload.name

    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"test('{name}', async ({{ request }}) => {{",
    ]

    # Auth setup
    if auth_config:
        auth_type = auth_config.get("type", "none")
        if auth_type == "bearer":
            lines.append(f"  const authToken = '{auth_config.get('token', 'YOUR_TOKEN')}';")
            lines.append("")
        elif auth_type == "oauth2_client_credentials":
            lines.append("  // Fetch OAuth2 token")
            lines.append(f"  const tokenResp = await request.post('{auth_config.get('token_url', '')}', {{")
            lines.append("    form: {")
            lines.append("      grant_type: 'client_credentials',")
            lines.append(f"      client_id: '{auth_config.get('client_id', '')}',")
            lines.append(f"      client_secret: process.env.CLIENT_SECRET || '{auth_config.get('client_secret', '')}',")
            if auth_config.get("scope"):
                lines.append(f"      scope: '{auth_config['scope']}',")
            lines.append("    },")
            lines.append("  });")
            lines.append("  expect(tokenResp.ok()).toBeTruthy();")
            lines.append("  const { access_token: authToken } = await tokenResp.json();")
            lines.append("")
        elif auth_type == "api_key":
            header_name = auth_config.get("header_name", "X-API-Key")
            lines.append(f"  const apiKeyHeader = {{ '{header_name}': process.env.API_KEY || '{auth_config.get('key', '')}' }};")
            lines.append("")

    # Steps
    for i, step in enumerate(steps):
        step_name = step.get("name", f"Step {i + 1}")
        method = step.get("method", "GET").lower()
        url = step.get("url", "")
        if base_url and url and not url.startswith(("http://", "https://")):
            url = base_url.rstrip("/") + "/" + url.lstrip("/")
        expected_status = step.get("expected_status", 200)
        body = step.get("body")
        headers = step.get("headers", {})
        extractions = step.get("extract", [])

        lines.append(f"  // {step_name}")
        opts_parts = []
        if headers or auth_config:
            h = {**headers}
            if auth_config and auth_config.get("type") == "bearer":
                h["Authorization"] = f"Bearer ${{authToken}}"
            elif auth_config and auth_config.get("type") == "api_key":
                pass  # handled via apiKeyHeader spread
            header_pairs = ', '.join("'%s': '%s'" % (k, v) for k, v in h.items())
            api_key_spread = ', ...apiKeyHeader' if auth_config and auth_config.get('type') == 'api_key' else ''
            opts_parts.append(f"headers: {{ {header_pairs}{api_key_spread} }}")
        if body:
            opts_parts.append(f"data: {json.dumps(body)}")

        opts_str = ""
        if opts_parts:
            opts_str = ", {\n    " + ",\n    ".join(opts_parts) + ",\n  }"

        var_name = f"resp{i}"
        lines.append(f"  const {var_name} = await request.{method}('{url}'{opts_str});")
        lines.append(f"  expect({var_name}.status()).toBe({expected_status});")

        # Assertions
        for assertion in step.get("assertions", []):
            atype = assertion.get("type")
            if atype == "body_contains":
                lines.append(f"  expect(await {var_name}.text()).toContain('{assertion.get('value', '')}');")
            elif atype == "json_path_equals":
                path = assertion.get("path", "")
                val = assertion.get("value", "")
                path_chain = ".".join(f"['{p}']" if not p.isdigit() else f"[{p}]" for p in path.split("."))
                lines.append(f"  const json{i} = await {var_name}.json();")
                lines.append(f"  expect(json{i}{path_chain}).toBe('{val}');")
            elif atype == "max_latency_ms":
                # Playwright doesn't natively track per-request timing easily; add a note
                lines.append(f"  // Assert: response within {assertion.get('value', 5000)}ms (measured by test infra)")

        # Extractions
        for ext in extractions:
            var = ext.get("variable", "")
            if ext.get("source") == "json_path":
                path = ext.get("path", "")
                path_chain = ".".join(f"['{p}']" if not p.isdigit() else f"[{p}]" for p in path.split("."))
                if f"json{i}" not in "\n".join(lines):
                    lines.append(f"  const json{i} = await {var_name}.json();")
                lines.append(f"  const {var} = json{i}{path_chain};")

        lines.append("")

    lines.append("});")
    lines.append("")

    import json
    return {"script": "\n".join(lines), "filename": f"{name.lower().replace(' ', '_')}.spec.ts"}


def _policy_dict(p: ValidationAutomationPolicyRow) -> dict[str, Any]:
    return {
        "id": p.id,
        "service_name": p.service_name,
        "alert_type": p.alert_type,
        "min_confidence_pct": p.min_confidence_pct,
        "validation_definition_id": p.validation_definition_id,
        "enabled": p.enabled,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ── Automation Policy routes (BEFORE parameterized routes) ────────────────────


@router.get("/automation-policies")
def list_automation_policies(db: Session = Depends(_db)) -> list[dict[str, Any]]:
    policies = db.query(ValidationAutomationPolicyRow).order_by(
        ValidationAutomationPolicyRow.created_at.desc()
    ).all()
    return [_policy_dict(p) for p in policies]


@router.post("/automation-policies", status_code=201)
def create_automation_policy(
    payload: AutomationPolicyCreate, db: Session = Depends(_db)
) -> dict[str, Any]:
    defn = db.get(ValidationDefinitionRow, payload.validation_definition_id)
    if defn is None:
        raise HTTPException(status_code=422, detail="validation_definition_id not found")

    policy = ValidationAutomationPolicyRow(
        service_name=payload.service_name,
        alert_type=payload.alert_type,
        min_confidence_pct=payload.min_confidence_pct,
        validation_definition_id=payload.validation_definition_id,
        enabled=payload.enabled,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return _policy_dict(policy)


@router.patch("/automation-policies/{policy_id}")
def update_automation_policy(
    policy_id: int, payload: AutomationPolicyUpdate, db: Session = Depends(_db)
) -> dict[str, Any]:
    policy = db.get(ValidationAutomationPolicyRow, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Automation policy not found")

    if payload.service_name is not None:
        policy.service_name = payload.service_name
    if payload.alert_type is not None:
        policy.alert_type = payload.alert_type
    if payload.min_confidence_pct is not None:
        policy.min_confidence_pct = payload.min_confidence_pct
    if payload.validation_definition_id is not None:
        defn = db.get(ValidationDefinitionRow, payload.validation_definition_id)
        if defn is None:
            raise HTTPException(status_code=422, detail="validation_definition_id not found")
        policy.validation_definition_id = payload.validation_definition_id
    if payload.enabled is not None:
        policy.enabled = payload.enabled

    db.commit()
    db.refresh(policy)
    return _policy_dict(policy)


@router.delete("/automation-policies/{policy_id}", status_code=204)
def delete_automation_policy(policy_id: int, db: Session = Depends(_db)) -> None:
    policy = db.get(ValidationAutomationPolicyRow, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Automation policy not found")
    db.delete(policy)
    db.commit()


# ── Parameterized validation routes ──────────────────────────────────────────


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

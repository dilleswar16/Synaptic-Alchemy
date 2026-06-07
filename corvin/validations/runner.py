"""Validation runner — executes ValidationDefinitionRow checks and persists ValidationRunRow results.

Supports:
- Auth injection (Bearer, OAuth2 client_credentials, API key, custom header)
- Variable extraction from responses (JSON path → {{variable}})
- Assertions beyond status code (body_contains, json_path_equals, max_latency_ms)
- Base URL resolution
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from corvin.storage.models import SloConfigRow, SloSnapshotRow, ValidationDefinitionRow, ValidationRunRow

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15.0  # seconds per step
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


# ── Variable substitution ─────────────────────────────────────────────────────


def _substitute_vars(value: Any, variables: dict[str, str]) -> Any:
    """Replace {{var_name}} placeholders in strings, dicts, and lists."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            return variables.get(m.group(1), m.group(0))
        return _VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _substitute_vars(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_vars(item, variables) for item in value]
    return value


def _extract_json_path(data: Any, path: str) -> Any:
    """Simple dot-notation JSON path extractor (e.g., 'data.token' or 'items[0].id')."""
    parts = re.split(r"\.|(\[\d+\])", path)
    current = data
    for part in parts:
        if part is None or part == "":
            continue
        if part.startswith("[") and part.endswith("]"):
            idx = int(part[1:-1])
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


# ── Auth resolution ───────────────────────────────────────────────────────────


async def _resolve_auth_headers(auth_config: dict[str, Any] | None) -> dict[str, str]:
    """Resolve auth config into HTTP headers to inject into every step."""
    if not auth_config:
        return {}

    auth_type = auth_config.get("type", "none")

    if auth_type == "none":
        return {}
    elif auth_type == "bearer":
        token = auth_config.get("token", "")
        return {"Authorization": f"Bearer {token}"} if token else {}
    elif auth_type == "api_key":
        header_name = auth_config.get("header_name", "X-API-Key")
        key = auth_config.get("key", "")
        return {header_name: key} if key else {}
    elif auth_type == "oauth2_client_credentials":
        token_url = auth_config.get("token_url", "")
        client_id = auth_config.get("client_id", "")
        client_secret = auth_config.get("client_secret", "")
        scope = auth_config.get("scope", "")
        if not all([token_url, client_id, client_secret]):
            return {}
        try:
            async with httpx.AsyncClient() as client:
                data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
                if scope:
                    data["scope"] = scope
                resp = await client.post(token_url, data=data, timeout=10.0)
                if resp.status_code == 200:
                    token = resp.json().get("access_token", "")
                    return {"Authorization": f"Bearer {token}"} if token else {}
                else:
                    logger.warning("OAuth2 token fetch failed: %s %s", resp.status_code, resp.text[:200])
                    return {}
        except Exception as exc:
            logger.warning("OAuth2 token fetch error: %s", exc)
            return {}
    elif auth_type == "custom_header":
        header_name = auth_config.get("header_name", "")
        header_value = auth_config.get("header_value", "")
        return {header_name: header_value} if header_name and header_value else {}

    return {}


# ── Assertions ────────────────────────────────────────────────────────────────


def _run_assertions(
    assertions: list[dict[str, Any]],
    resp_body: Any,
    duration_ms: int,
) -> list[dict[str, Any]]:
    """Run assertions against a response. Returns list of {type, passed, detail}."""
    results = []
    for assertion in assertions:
        atype = assertion.get("type", "")
        if atype == "status_code":
            # Handled separately — skip here
            continue
        elif atype == "body_contains":
            text = assertion.get("value", "")
            body_str = json.dumps(resp_body) if not isinstance(resp_body, str) else resp_body
            passed = text in body_str
            results.append({"type": atype, "passed": passed, "detail": f"Body {'contains' if passed else 'does not contain'} '{text}'"})
        elif atype == "json_path_equals":
            path = assertion.get("path", "")
            expected = assertion.get("value")
            actual = _extract_json_path(resp_body, path)
            passed = str(actual) == str(expected)
            results.append({"type": atype, "passed": passed, "detail": f"$.{path} = {actual!r} (expected {expected!r})"})
        elif atype == "max_latency_ms":
            threshold = int(assertion.get("value", 5000))
            passed = duration_ms <= threshold
            results.append({"type": atype, "passed": passed, "detail": f"{duration_ms}ms {'≤' if passed else '>'} {threshold}ms"})
        elif atype == "json_path_exists":
            path = assertion.get("path", "")
            actual = _extract_json_path(resp_body, path)
            passed = actual is not None
            results.append({"type": atype, "passed": passed, "detail": f"$.{path} {'exists' if passed else 'not found'}"})
    return results


# ── Step runners ──────────────────────────────────────────────────────────────


async def _run_http_step(
    step: dict[str, Any],
    client: httpx.AsyncClient,
    variables: dict[str, str],
    auth_headers: dict[str, str],
    base_url: str = "",
) -> dict[str, Any]:
    """Execute one HTTP step with variable substitution, auth, and assertions."""
    # Substitute variables in the step config
    step = _substitute_vars(step, variables)

    method = str(step.get("method", "GET")).upper()
    url = step.get("url", "")
    # Resolve relative URLs against base_url
    if base_url and url and not url.startswith(("http://", "https://")):
        url = base_url.rstrip("/") + "/" + url.lstrip("/")

    expected_status = step.get("expected_status", step.get("expect_status", 200))
    timeout = float(step.get("timeout_s", _HTTP_TIMEOUT))
    body = step.get("body")
    headers = {**auth_headers, **step.get("headers", {})}
    assertions = step.get("assertions", [])
    extractions = step.get("extract", [])

    if not url:
        return {"ok": False, "error": "No URL specified", "duration_ms": 0, "extracted": {}}

    t0 = time.perf_counter()
    try:
        resp = await client.request(
            method, url, json=body if body else None, headers=headers, timeout=timeout, follow_redirects=True
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)

        # Parse response body
        resp_body: Any = None
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        # Status code check
        status_ok = resp.status_code == expected_status

        # Run assertions
        assertion_results = _run_assertions(assertions, resp_body, duration_ms)
        assertions_ok = all(a["passed"] for a in assertion_results) if assertion_results else True

        # Extract variables
        extracted: dict[str, str] = {}
        for ext in extractions:
            var_name = ext.get("variable", "")
            source = ext.get("source", "json_path")
            if source == "json_path":
                path = ext.get("path", "")
                value = _extract_json_path(resp_body, path)
                if value is not None:
                    extracted[var_name] = str(value)
            elif source == "header":
                header_name = ext.get("header", "")
                value = resp.headers.get(header_name)
                if value:
                    extracted[var_name] = value

        ok = status_ok and assertions_ok
        error = None
        if not status_ok:
            error = f"Expected {expected_status}, got {resp.status_code}"
        elif not assertions_ok:
            failed = [a for a in assertion_results if not a["passed"]]
            error = f"Assertion failed: {failed[0]['detail']}" if failed else "Assertion failed"

        return {
            "ok": ok,
            "status_code": resp.status_code,
            "expected_status": expected_status,
            "duration_ms": duration_ms,
            "error": error,
            "assertions": assertion_results if assertion_results else None,
            "extracted": extracted,
        }
    except httpx.TimeoutException:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "error": f"Timeout after {timeout}s", "duration_ms": duration_ms, "extracted": {}}
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "error": str(exc), "duration_ms": duration_ms, "extracted": {}}


async def _execute_steps(
    steps: list[dict[str, Any]],
    auth_config: dict[str, Any] | None = None,
    base_url: str = "",
    abort_on_failure: bool = True,
) -> tuple[bool, list[dict[str, Any]]]:
    """Run all steps sequentially with variable chaining. Returns (all_passed, step_results)."""
    auth_headers = await _resolve_auth_headers(auth_config)
    variables: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    all_passed = True

    async with httpx.AsyncClient() as client:
        for i, step in enumerate(steps):
            step_type = step.get("type", "http")
            if step_type == "http" or step_type == "":
                result = await _run_http_step(step, client, variables, auth_headers, base_url)
            elif step_type == "wait":
                wait_ms = int(step.get("duration_ms", 1000))
                await asyncio.sleep(wait_ms / 1000)
                result = {"ok": True, "note": f"Waited {wait_ms}ms", "duration_ms": wait_ms, "extracted": {}}
            else:
                result = {"ok": True, "note": f"Step type '{step_type}' not implemented — skipped", "extracted": {}}

            # Merge extracted variables into the chain
            extracted = result.pop("extracted", {})
            if extracted:
                variables.update(extracted)
                result["extracted_vars"] = extracted

            result["step_index"] = i
            result["step_name"] = step.get("name", f"Step {i + 1}")
            results.append(result)

            if not result.get("ok", False):
                all_passed = False
                if abort_on_failure:
                    # Mark remaining steps as skipped
                    for j in range(i + 1, len(steps)):
                        results.append({
                            "ok": False, "step_index": j,
                            "step_name": steps[j].get("name", f"Step {j + 1}"),
                            "error": "Skipped — previous step failed",
                            "skipped": True,
                        })
                    break

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
    """Chaos validations require manual confirmation — do not auto-pass."""
    description = config.get("description", "Manual chaos test")
    return False, [{
        "ok": False,
        "step_index": 0,
        "step_name": "Chaos (pending confirmation)",
        "status": "pending_confirmation",
        "note": f"{description} — chaos tests require manual execution and operator confirmation before passing.",
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
            auth_config = config.get("auth")
            base_url = config.get("base_url", "")
            abort_on_failure = config.get("abort_on_failure", True)
            passed, step_results = await _execute_steps(steps, auth_config, base_url, abort_on_failure)
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

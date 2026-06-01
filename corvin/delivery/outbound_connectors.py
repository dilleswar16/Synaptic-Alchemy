"""Helpers for validating and testing outbound connector configurations."""
from __future__ import annotations

from base64 import b64encode
import logging
import re
import time
from typing import Any

import httpx

from corvin.connectors.base import TestResult

_log = logging.getLogger(__name__)

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def test_outbound_connector(connector_type: str, display_name: str, config_json: dict[str, Any]) -> TestResult:
    """Validate an outbound connector and, when possible, probe the target endpoint.

    EV1 keeps outbound connector setup flexible. We do a real HTTP probe when the
    configured endpoint is HTTP-based and fall back to structural validation for
    non-HTTP destinations such as SMTP hosts.
    """
    endpoint = _connector_endpoint(config_json)
    if not endpoint:
        return TestResult(ok=False, message="endpoint is empty")

    auth = _as_dict(config_json.get("auth"))
    endpoint_fields = _as_dict(config_json.get("endpoint_fields"))

    validation_error = _validate_config(connector_type, auth, endpoint_fields)
    if validation_error:
        return TestResult(ok=False, message=validation_error)

    if connector_type == "email" and not _HTTP_URL_RE.match(endpoint):
        port = str(endpoint_fields.get("port", "587")).strip() or "587"
        from_address = str(endpoint_fields.get("from", "")).strip() or "(unspecified)"
        return TestResult(
            ok=True,
            message=f"Email connector saved for SMTP host {endpoint}:{port} from {from_address}",
        )

    if not _HTTP_URL_RE.match(endpoint):
        return TestResult(ok=False, message=f"Endpoint must be an http(s) URL, got {endpoint!r}")

    method = str(endpoint_fields.get("http_method", "POST") or "POST").upper()
    if method not in {"GET", "POST", "PUT", "PATCH"}:
        return TestResult(ok=False, message=f"Unsupported HTTP method {method!r}")

    headers = {"Content-Type": "application/json"}
    try:
        headers.update(_build_auth_headers(auth))
    except ValueError as exc:
        return TestResult(ok=False, message=str(exc))

    payload = _build_probe_payload(connector_type, display_name, config_json)
    timeout_seconds = _coerce_timeout(config_json.get("timeout_seconds", 10))

    t0 = time.monotonic()
    try:
        response = httpx.request(
            method,
            endpoint,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
            follow_redirects=True,
            verify=False,
        )
        latency_ms = (time.monotonic() - t0) * 1000
        if 200 <= response.status_code < 400:
            return TestResult(ok=True, message=f"HTTP {response.status_code}", latency_ms=latency_ms)
        if response.status_code in {401, 403}:
            return TestResult(
                ok=False,
                message=f"HTTP {response.status_code}: endpoint reachable but auth rejected",
                latency_ms=latency_ms,
            )
        return TestResult(
            ok=False,
            message=f"HTTP {response.status_code}: {response.text[:200]}",
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.monotonic() - t0) * 1000
        _log.debug("Outbound connector test failed: %s", exc)
        return TestResult(ok=False, message=str(exc), latency_ms=latency_ms)


def _connector_endpoint(config_json: dict[str, Any]) -> str:
    endpoint = str(config_json.get("endpoint", "") or config_json.get("webhook_url", "")).strip()
    return endpoint


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = 10.0
    return max(1.0, min(timeout, 60.0))


def _validate_config(connector_type: str, auth: dict[str, Any], endpoint_fields: dict[str, Any]) -> str | None:
    auth_type = str(auth.get("type", "none") or "none").strip().lower()
    if auth_type not in {"none", "bearer", "api_key", "basic", "oauth2"}:
        return f"Unsupported auth.type {auth_type!r}"

    if auth_type == "bearer" and not str(auth.get("bearer_token", "")).strip():
        return "bearer auth requires bearer_token"
    if auth_type == "api_key" and not str(auth.get("api_key", "")).strip():
        return "api_key auth requires api_key"
    if auth_type == "basic" and (not str(auth.get("username", "")).strip() or not str(auth.get("password", "")).strip()):
        return "basic auth requires username and password"
    if auth_type == "oauth2":
        for key in ("token_url", "client_id", "client_secret"):
            if not str(auth.get(key, "")).strip():
                return f"oauth2 auth requires {key}"

    if connector_type == "servicenow" and not str(endpoint_fields.get("table", "incident")).strip():
        return "servicenow connectors require a table"
    if connector_type == "email":
        if not str(endpoint_fields.get("from", "")).strip():
            return "email connectors require endpoint_fields.from"
        if not str(endpoint_fields.get("port", "")).strip():
            return "email connectors require endpoint_fields.port"

    return None


def _build_auth_headers(auth: dict[str, Any]) -> dict[str, str]:
    auth_type = str(auth.get("type", "none") or "none").strip().lower()
    if auth_type in {"", "none"}:
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {str(auth.get('bearer_token', '')).strip()}"}
    if auth_type == "api_key":
        header_name = str(auth.get("api_key_header", "X-API-Key") or "X-API-Key").strip()
        return {header_name: str(auth.get("api_key", "")).strip()}
    if auth_type == "basic":
        username = str(auth.get("username", "")).strip()
        password = str(auth.get("password", "")).strip()
        token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    if auth_type == "oauth2":
        token_url = str(auth.get("token_url", "")).strip()
        client_id = str(auth.get("client_id", "")).strip()
        client_secret = str(auth.get("client_secret", "")).strip()
        scopes = str(auth.get("scopes", "")).strip()
        data: dict[str, str] = {"grant_type": "client_credentials"}
        if scopes:
            data["scope"] = scopes
        response = httpx.post(
            token_url,
            data=data,
            auth=(client_id, client_secret),
            timeout=10,
            follow_redirects=True,
            verify=False,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError("OAuth2 token response did not include access_token")
        return {"Authorization": f"Bearer {token}"}
    raise ValueError(f"Unsupported auth.type {auth_type!r}")


def _build_probe_payload(connector_type: str, display_name: str, config_json: dict[str, Any]) -> dict[str, Any]:
    variables = config_json.get("variables") if isinstance(config_json.get("variables"), list) else []
    payload = {
        "source": "corvin",
        "connector_type": connector_type,
        "display_name": display_name,
        "event": "connectivity_test",
    }
    for item in variables:
        if isinstance(item, dict):
            key = str(item.get("key", "")).strip()
            if key:
                payload[key] = item.get("default_value", "")
    return payload
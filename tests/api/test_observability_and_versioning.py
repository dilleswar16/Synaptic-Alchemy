"""
Phase 2-lite API hardening tests.

Covers:
  - RequestContextMiddleware: X-Request-ID generation and inbound passthrough
  - ApiVersionMiddleware: /v1 prefix routing + X-API-Version header
  - RFC 7807 problem+json error responses (404, 422) with `detail` kept
    as a plain string for existing clients
  - JsonFormatter: structured fields, request_id propagation, extra= merging
  - get_session() context manager behaviour (TD-H1 regression guard)

No real adapters, LLM, or Postgres needed — uses TestClient against the real
app with the same dependency_overrides pattern as test_slice9_api_cli.py.
"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from apps.api.main import app
from corvin.core.logging_config import JsonFormatter
from corvin.core.request_context import (
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)

client = TestClient(app)


# ── Request ID middleware ─────────────────────────────────────────────────────


def test_response_carries_generated_request_id() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert "x-request-id" in res.headers
    assert len(res.headers["x-request-id"]) >= 8


def test_inbound_request_id_is_propagated() -> None:
    res = client.get("/health", headers={"X-Request-ID": "gateway-id-42"})
    assert res.headers["x-request-id"] == "gateway-id-42"


def test_request_ids_differ_between_requests() -> None:
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]
    assert first != second


# ── API versioning (/v1 prefix) ───────────────────────────────────────────────


def test_health_reachable_at_root() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_reachable_under_v1() -> None:
    res = client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_responses_carry_api_version_header() -> None:
    res = client.get("/health")
    assert res.headers.get("x-api-version") == "1"


def test_v1_and_root_serve_identical_payloads() -> None:
    assert client.get("/health").json() == client.get("/v1/health").json()


def test_v1_unknown_route_is_404_not_500() -> None:
    res = client.get("/v1/definitely-not-a-route")
    assert res.status_code == 404


# ── RFC 7807 problem+json errors ──────────────────────────────────────────────


def test_404_returns_problem_json() -> None:
    res = client.get("/no-such-route")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert isinstance(body["detail"], str)
    assert body["instance"] == "/no-such-route"
    assert "request_id" in body


def test_problem_detail_remains_string_for_existing_clients() -> None:
    # The frontend reads `payload.detail || payload.message` — keep that contract.
    body = client.get("/no-such-route").json()
    assert isinstance(body["detail"], str) and body["detail"]


def test_422_returns_problem_json_with_errors_extension() -> None:
    # Malformed JSON fails request parsing before any dependency (engine,
    # repo, Teams adapter) is constructed — no investigation is triggered.
    res = client.post(
        "/triggers/azure-alert",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["status"] == 422
    assert body["title"] == "Validation Error"
    assert isinstance(body["detail"], str)
    assert isinstance(body["errors"], list) and body["errors"]


# ── Structured JSON logging ───────────────────────────────────────────────────


def _format_record(message: str, **extra: object) -> dict:
    record = logging.LogRecord(
        name="corvin.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_emits_core_fields() -> None:
    payload = _format_record("hello world")
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "corvin.test"
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_includes_request_id_when_bound() -> None:
    token = set_request_id("req-abc-123")
    try:
        payload = _format_record("inside request")
        assert payload["request_id"] == "req-abc-123"
    finally:
        reset_request_id(token)


def test_json_formatter_omits_request_id_outside_request() -> None:
    assert get_request_id() is None
    payload = _format_record("background task")
    assert "request_id" not in payload


def test_json_formatter_merges_extra_fields() -> None:
    payload = _format_record("access", status_code=200, duration_ms=12.5)
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5


def test_new_request_id_is_unique_and_short() -> None:
    ids = {new_request_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(len(rid) == 16 for rid in ids)


# ── TD-H1 regression guard ────────────────────────────────────────────────────


def test_get_session_is_context_manager_not_iterator() -> None:
    """next(get_session()) was a latent TypeError — ensure the contract is CM-only."""
    from corvin.storage.db import get_session

    cm = get_session()
    assert hasattr(cm, "__enter__") and hasattr(cm, "__exit__")
    assert not hasattr(cm, "__next__")


def test_main_module_does_not_use_iterator_session() -> None:
    import inspect

    import apps.api.main as main_module

    source = inspect.getsource(main_module)
    assert "next(get_session())" not in source

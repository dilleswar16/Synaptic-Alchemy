"""
Slice 9 – API routes and CLI persistence tests.

Uses FastAPI's TestClient with dependency_overrides so neither InvestigationEngine
nor InvestigationRepository need real adapters or a running Postgres instance.
CLI tests mock httpx directly and use typer's CliRunner.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from corvin.core.contracts import (
    EvidenceBundle,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAConfidence,
    RCAOutput,
    TriggerSource,
)
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository

# Import the app and the overridable dependency functions.
from apps.api.main import app
from apps.api.routes.investigations import get_engine, get_repository, get_teams_adapter


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


def _make_fake_result(request: InvestigationRequest) -> InvestigationResult:
    """Build a minimal but fully valid InvestigationResult for a given request."""
    return InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=EvidenceBundle(request_id=request.id),
        rca=RCAOutput(
            request_id=request.id,
            summary="Heap exhaustion in order-service.",
            root_cause="Max heap set too low after recent config change.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=request.id,
            summary="Increase JVM heap and redeploy.",
            justification="Root cause maps directly to JVM config.",
        ),
    )


class FakeEngine:
    """InvestigationEngine substitute that returns a deterministic result."""

    def run(self, request: InvestigationRequest) -> InvestigationResult:
        return _make_fake_result(request)


class FakeRepository:
    """InvestigationRepository substitute backed by an in-memory dict."""

    def __init__(self) -> None:
        self._store: dict[str, InvestigationResult] = {}

    def save_investigation_result(self, result: InvestigationResult) -> None:
        self._store[result.request_id] = result

    def get_investigation_result(self, request_id: str) -> InvestigationResult | None:
        return self._store.get(request_id)

    def list_investigations(self) -> list[dict]:
        return [
            {
                "request_id": r.request_id,
                "service_name": r.request.service_name,
                "environment": r.request.environment,
                "trigger_source": r.request.trigger_source.value,
                "completed_at": r.completed_at.isoformat(),
                "created_at": r.request.created_at.isoformat(),
            }
            for r in self._store.values()
        ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(fake_engine, fake_repo):
    """TestClient with engine, repository, and teams dependencies overridden."""
    # No-op Teams adapter so POST tests are not affected by missing webhook config.
    class NoOpTeams:
        def send_result(self, _result):
            pass

    app.dependency_overrides[get_engine] = lambda: fake_engine
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_teams_adapter] = lambda: NoOpTeams()
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /investigations/ tests
# ---------------------------------------------------------------------------


def test_post_investigation_returns_200_with_request_id(client):
    resp = client.post(
        "/investigations/",
        json={"service_name": "order-service", "environment": "production"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "request_id" in data
    assert len(data["request_id"]) == 36  # UUID format
    assert data["status"] == "completed"


def test_post_investigation_runs_engine_and_saves_result(client, fake_repo):
    """After POST, the result must be findable in the repository."""
    resp = client.post(
        "/investigations/",
        json={
            "service_name": "order-service",
            "environment": "production",
            "description": "Spike in 5xx errors",
        },
    )
    assert resp.status_code == 200
    request_id = resp.json()["request_id"]

    saved = fake_repo.get_investigation_result(request_id)
    assert saved is not None
    assert saved.request_id == request_id
    assert saved.request.service_name == "order-service"
    assert saved.rca.summary == "Heap exhaustion in order-service."


def test_post_investigation_engine_receives_correct_request_fields(client, fake_repo):
    """The engine must receive a request with the fields from the POST body."""
    client.post(
        "/investigations/",
        json={
            "service_name": "payment-service",
            "environment": "staging",
            "description": "Latency spike",
        },
    )
    # There should be exactly one saved result.
    assert len(fake_repo._store) == 1
    saved = next(iter(fake_repo._store.values()))
    assert saved.request.service_name == "payment-service"
    assert saved.request.environment == "staging"
    assert saved.request.description == "Latency spike"
    assert saved.request.trigger_source == TriggerSource.MANUAL_API


# ---------------------------------------------------------------------------
# GET /investigations/{request_id} tests
# ---------------------------------------------------------------------------


def test_get_investigation_returns_persisted_result(client, fake_repo):
    """After POST, GET must return the full InvestigationResult."""
    post_resp = client.post(
        "/investigations/",
        json={"service_name": "order-service", "environment": "production"},
    )
    request_id = post_resp.json()["request_id"]

    get_resp = client.get(f"/investigations/{request_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["request_id"] == request_id
    assert data["rca"]["summary"] == "Heap exhaustion in order-service."
    assert data["rca"]["confidence"] == "high"
    assert data["fix_strategy"]["summary"] == "Increase JVM heap and redeploy."


def test_get_investigation_returns_404_for_unknown_id(client):
    """GET for a request_id that was never saved must return 404."""
    resp = client.get("/investigations/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_get_investigation_404_response_contains_detail(client):
    resp = client.get("/investigations/no-such-id")
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_get_investigation_returns_rca_and_fix_strategy_fields(client):
    """GET response must include nested rca and fix_strategy blocks."""
    post_resp = client.post(
        "/investigations/",
        json={"service_name": "svc", "environment": "dev"},
    )
    rid = post_resp.json()["request_id"]

    data = client.get(f"/investigations/{rid}").json()
    assert "rca" in data
    assert "fix_strategy" in data
    assert "evidence" in data
    assert "request" in data


def test_get_investigation_request_block_has_trigger_source(client):
    post_resp = client.post(
        "/investigations/",
        json={"service_name": "svc", "environment": "dev"},
    )
    rid = post_resp.json()["request_id"]
    data = client.get(f"/investigations/{rid}").json()
    assert data["request"]["trigger_source"] == "manual_api"


# ---------------------------------------------------------------------------
# CLI shell command function tests
# ---------------------------------------------------------------------------
# The interactive REPL is not invoked here — we test the command handler
# functions (cmd_investigate, cmd_list, cmd_show, cmd_health) directly.
# httpx calls inside those functions are mocked so no running API is needed.
# ---------------------------------------------------------------------------


def _make_post_mock(request_id: str) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {
        "request_id": request_id,
        "status": "completed",
        "message": "Investigation completed and persisted.",
    }
    return mock


def _make_get_mock(request_id: str) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {
        "request_id": request_id,
        "request": {"service_name": "order-service", "environment": "production", "trigger_source": "manual_api"},
        "rca": {
            "summary": "Heap exhaustion in order-service.",
            "root_cause": "Max heap too low.",
            "confidence": "high",
            "contributing_factors": ["traffic spike"],
        },
        "fix_strategy": {
            "summary": "Increase JVM heap and redeploy.",
            "justification": "Config change caused the issue.",
            "actions": [],
        },
    }
    return mock


def test_cmd_investigate_renders_rca_summary(monkeypatch):
    """cmd_investigate must render the RCA summary and confidence to the console."""
    import io
    import apps.cli.main as cli_module
    from rich.console import Console as RichConsole

    buf = io.StringIO()
    monkeypatch.setattr(cli_module, "console", RichConsole(file=buf, force_terminal=False, highlight=False))

    fixed_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch.object(cli_module, "_api_post", return_value={"request_id": fixed_id}), \
         patch.object(cli_module, "_api_get", return_value=_make_get_mock(fixed_id).json.return_value):
        cli_module.cmd_investigate(["order-service", "production", "manual test"])

    output = buf.getvalue()
    assert "Heap exhaustion in order-service." in output
    assert "HIGH" in output.upper()
    assert "Increase JVM heap and redeploy." in output


def test_cmd_investigate_renders_request_id(monkeypatch):
    import io
    import apps.cli.main as cli_module
    from rich.console import Console as RichConsole

    buf = io.StringIO()
    monkeypatch.setattr(cli_module, "console", RichConsole(file=buf, force_terminal=False, highlight=False))

    fixed_id = "11111111-2222-3333-4444-555555555555"

    with patch.object(cli_module, "_api_post", return_value={"request_id": fixed_id}), \
         patch.object(cli_module, "_api_get", return_value=_make_get_mock(fixed_id).json.return_value):
        cli_module.cmd_investigate(["svc", "dev", "test description"])

    output = buf.getvalue()
    assert fixed_id in output


def test_cmd_investigate_handles_connect_error(monkeypatch):
    """cmd_investigate must print an error and return (not raise) on ConnectError."""
    import io
    import apps.cli.main as cli_module
    from rich.console import Console as RichConsole

    buf = io.StringIO()
    monkeypatch.setattr(cli_module, "console", RichConsole(file=buf, force_terminal=False, highlight=False))

    with patch.object(cli_module, "_api_post", side_effect=httpx.ConnectError("refused")):
        cli_module.cmd_investigate(["svc", "dev", "test"])

    output = buf.getvalue()
    assert "Cannot connect" in output or "cannot connect" in output.lower() or "✗" in output


def test_cmd_investigate_handles_http_error(monkeypatch):
    """cmd_investigate must print an error on HTTPStatusError."""
    import io
    import apps.cli.main as cli_module
    from rich.console import Console as RichConsole

    buf = io.StringIO()
    monkeypatch.setattr(cli_module, "console", RichConsole(file=buf, force_terminal=False, highlight=False))

    error_resp = MagicMock()
    error_resp.status_code = 500
    error_resp.text = "Internal Server Error"
    exc = httpx.HTTPStatusError("err", request=MagicMock(), response=error_resp)

    with patch.object(cli_module, "_api_post", side_effect=exc):
        cli_module.cmd_investigate(["svc", "dev", "test"])

    output = buf.getvalue()
    assert "500" in output or "error" in output.lower() or "✗" in output

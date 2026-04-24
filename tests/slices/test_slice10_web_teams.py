"""
Slice 10 – Web app list endpoint and Teams delivery tests.

All tests use FastAPI's TestClient with dependency_overrides and/or mocked
httpx. No Postgres instance or real Teams webhook is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from corvin.core.contracts import (
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.delivery.teams_adapter import TeamsAdapter

from apps.api.main import app
from apps.api.routes.investigations import get_engine, get_repository, get_teams_adapter


# ---------------------------------------------------------------------------
# Shared helpers (duplicated from slice 9 to keep slices self-contained)
# ---------------------------------------------------------------------------


def _make_fake_result(request: InvestigationRequest) -> InvestigationResult:
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
            actions=[
                FixAction(
                    title="Increase -Xmx from 512m to 2g",
                    description="Update the JVM_OPTS env var in the deployment.",
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Eliminates OOM errors.",
                    requires_approval=True,
                )
            ],
        ),
    )


class FakeEngine:
    def run(self, request: InvestigationRequest) -> InvestigationResult:
        return _make_fake_result(request)


class FakeRepository:
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


class NoOpTeams:
    def send_result(self, _result: InvestigationResult) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_engine():
    return FakeEngine()


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture
def no_op_teams():
    return NoOpTeams()


@pytest.fixture
def client(fake_engine, fake_repo, no_op_teams):
    app.dependency_overrides[get_engine] = lambda: fake_engine
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_teams_adapter] = lambda: no_op_teams
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /investigations/ – list endpoint
# ---------------------------------------------------------------------------


def test_list_investigations_returns_empty_list_when_none(client):
    resp = client.get("/investigations/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_investigations_returns_summary_after_post(client):
    client.post(
        "/investigations/",
        json={"service_name": "order-service", "environment": "production"},
    )
    resp = client.get("/investigations/")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["service_name"] == "order-service"
    assert items[0]["environment"] == "production"


def test_list_investigations_includes_required_summary_fields(client):
    client.post(
        "/investigations/",
        json={"service_name": "payment-service", "environment": "staging"},
    )
    items = client.get("/investigations/").json()
    item = items[0]
    assert "request_id" in item
    assert "service_name" in item
    assert "environment" in item
    assert "trigger_source" in item
    assert "completed_at" in item
    assert "created_at" in item


def test_list_investigations_trigger_source_is_manual_api(client):
    client.post("/investigations/", json={"service_name": "svc", "environment": "dev"})
    items = client.get("/investigations/").json()
    assert items[0]["trigger_source"] == "manual_api"


def test_list_grows_with_each_post(client):
    client.post("/investigations/", json={"service_name": "svc-a", "environment": "dev"})
    client.post("/investigations/", json={"service_name": "svc-b", "environment": "dev"})
    items = client.get("/investigations/").json()
    assert len(items) == 2
    service_names = {i["service_name"] for i in items}
    assert service_names == {"svc-a", "svc-b"}


# ---------------------------------------------------------------------------
# TeamsAdapter unit tests
# ---------------------------------------------------------------------------


def _make_teams_result() -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="Spike in errors",
    )
    return _make_fake_result(req)


def test_teams_adapter_posts_adaptive_card_to_webhook():
    """send_result must POST to the configured webhook URL."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None

    adapter = TeamsAdapter(config={"enabled": True, "webhook_url": "https://teams.example.com/webhook"})
    result = _make_teams_result()

    with patch("corvin.delivery.teams_adapter.httpx.post", return_value=mock_response) as mock_post:
        adapter.send_result(result)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == "https://teams.example.com/webhook"
    # Payload must be an Adaptive Card envelope
    payload = call_kwargs.kwargs["json"]
    assert payload["type"] == "message"
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_teams_adapter_card_contains_service_and_rca_summary():
    """The Adaptive Card body must include service name and RCA summary."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    adapter = TeamsAdapter(config={"enabled": True, "webhook_url": "https://example.com/wh"})
    result = _make_teams_result()

    with patch("corvin.delivery.teams_adapter.httpx.post", return_value=mock_response) as mock_post:
        adapter.send_result(result)

    payload = mock_post.call_args.kwargs["json"]
    card_body = payload["attachments"][0]["content"]["body"]
    # All body text concatenated for searching
    all_text = str(card_body)
    assert "order-service" in all_text
    assert "Heap exhaustion in order-service." in all_text


def test_teams_adapter_disabled_does_not_call_httpx():
    """When enabled is false, httpx must not be called."""
    adapter = TeamsAdapter(config={"enabled": False, "webhook_url": "https://example.com/wh"})
    result = _make_teams_result()

    with patch("corvin.delivery.teams_adapter.httpx.post") as mock_post:
        adapter.send_result(result)

    mock_post.assert_not_called()


def test_teams_adapter_missing_webhook_url_raises_value_error():
    """A missing or unresolved webhook_url must raise ValueError (not crash silently)."""
    adapter = TeamsAdapter(config={"enabled": True, "webhook_url": ""})
    with pytest.raises(ValueError, match="webhook_url"):
        adapter.send_result(_make_teams_result())


def test_teams_adapter_unresolved_env_placeholder_raises_value_error():
    """An unresolved ${...} placeholder must raise ValueError."""
    adapter = TeamsAdapter(config={"enabled": True, "webhook_url": "${TEAMS_WEBHOOK_URL}"})
    with pytest.raises(ValueError, match="webhook_url"):
        adapter.send_result(_make_teams_result())


# ---------------------------------------------------------------------------
# Route: Teams delivery integration with POST
# ---------------------------------------------------------------------------


def test_post_investigation_calls_teams_send_result(fake_engine, fake_repo):
    """POST /investigations/ must invoke send_result on the teams adapter."""

    class SpyTeams:
        called_with: InvestigationResult | None = None

        def send_result(self, result: InvestigationResult) -> None:
            SpyTeams.called_with = result

    spy = SpyTeams()
    app.dependency_overrides[get_engine] = lambda: fake_engine
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_teams_adapter] = lambda: spy

    try:
        c = TestClient(app)
        c.post("/investigations/", json={"service_name": "svc", "environment": "dev"})
    finally:
        app.dependency_overrides.clear()

    assert SpyTeams.called_with is not None
    assert SpyTeams.called_with.request.service_name == "svc"


def test_post_investigation_succeeds_even_when_teams_raises(fake_engine, fake_repo):
    """A Teams delivery failure must not surface as an HTTP error to the caller."""

    class FailingTeams:
        def send_result(self, _result: InvestigationResult) -> None:
            raise RuntimeError("Teams webhook unreachable")

    app.dependency_overrides[get_engine] = lambda: fake_engine
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_teams_adapter] = lambda: FailingTeams()

    try:
        c = TestClient(app)
        resp = c.post("/investigations/", json={"service_name": "svc", "environment": "dev"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

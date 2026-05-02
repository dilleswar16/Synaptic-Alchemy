"""
H-7 regression: POST /triggers/azure-alert must run the investigation
engine, persist the result, and call the Teams adapter.

Uses FastAPI TestClient with dependency_overrides — no real engine, no
real Postgres, no real Teams.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from corvin.core.contracts import (
    EvidenceBundle,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAOutput,
    TriggerSource,
)
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository
from apps.api.main import app
from apps.api.routes.triggers import (
    get_engine,
    get_repository,
    get_teams_adapter,
)


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeEngine(InvestigationEngine):
    def __init__(self) -> None:  # noqa: D401 — bypass real wiring
        self.calls: list[InvestigationRequest] = []

    def run(self, request: InvestigationRequest) -> InvestigationResult:
        self.calls.append(request)
        return InvestigationResult(
            request_id=request.id,
            request=request,
            evidence=EvidenceBundle(request_id=request.id),
            rca=RCAOutput(
                request_id=request.id,
                summary="fake rca summary",
                root_cause="fake root cause",
            ),
            fix_strategy=FixStrategyOutput(
                request_id=request.id,
                summary="fake fix",
                actions=[],
                justification="fake",
            ),
        )


class FakeRepo(InvestigationRepository):
    def __init__(self) -> None:  # noqa: D401 — bypass real wiring
        self.saved: list[InvestigationResult] = []

    def save_investigation_result(self, result: InvestigationResult) -> None:
        self.saved.append(result)


class FakeTeams(TeamsAdapter):
    def __init__(self) -> None:  # noqa: D401 — bypass real wiring
        self.delivered: list[InvestigationResult] = []

    def send_result(self, result: InvestigationResult) -> None:
        self.delivered.append(result)


# ── Sample Common Alert Schema payload ───────────────────────────────────────


_PAYLOAD: dict[str, Any] = {
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {
        "essentials": {
            "alertId": "/subscriptions/0/providers/Microsoft.AlertsManagement/alerts/abc",
            "alertRule": "High 5xx on order-service",
            "severity": "Sev2",
            "monitorCondition": "Fired",
            "alertTargetIDs": [
                "/subscriptions/0/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks-prod"
            ],
        },
        "alertContext": {
            "properties": {
                "service_name": "order-service",
                "environment": "production",
            }
        },
    },
}


def _override(engine: FakeEngine, repo: FakeRepo, teams: FakeTeams) -> TestClient:
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_teams_adapter] = lambda: teams
    return TestClient(app)


def _cleanup() -> None:
    for dep in (get_engine, get_repository, get_teams_adapter):
        app.dependency_overrides.pop(dep, None)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_azure_alert_runs_engine_persists_and_delivers():
    """Happy path: webhook returns 202 'accepted' immediately, then the
    background task runs the engine, persists, and posts to Teams.

    TestClient runs BackgroundTasks synchronously after the response returns,
    so by the time the context manager exits all side effects have occurred.
    """
    engine, repo, teams = FakeEngine(), FakeRepo(), FakeTeams()
    client = _override(engine, repo, teams)
    try:
        with client:
            resp = client.post("/triggers/azure-alert", json=_PAYLOAD)
            assert resp.status_code == 202
            body = resp.json()
            # Webhook always returns 'accepted' — work happens after the response.
            assert body["status"] == "accepted"
            assert body["trigger_source"] == TriggerSource.AZURE_ALERT.value
            assert body["service_name"]  # normalized non-empty

        # After the TestClient context exits, the BackgroundTask has finished.
        assert len(engine.calls) == 1
        assert len(repo.saved) == 1
        assert len(teams.delivered) == 1
        assert engine.calls[0].id == body["request_id"]
    finally:
        _cleanup()


def test_azure_alert_returns_accepted_when_engine_fails():
    """Engine failure must NOT 5xx back to Azure Monitor — alerts retry forever."""

    class ExplodingEngine(InvestigationEngine):
        def __init__(self) -> None:
            pass

        def run(self, request: InvestigationRequest) -> InvestigationResult:
            raise RuntimeError("LLM unavailable")

    repo, teams = FakeRepo(), FakeTeams()
    client = _override(ExplodingEngine(), repo, teams)
    try:
        with client:
            resp = client.post("/triggers/azure-alert", json=_PAYLOAD)
            assert resp.status_code == 202
            assert resp.json()["status"] == "accepted"
        # Background task swallowed the engine error -> no save, no Teams.
        assert repo.saved == []
        assert teams.delivered == []
    finally:
        _cleanup()


def test_azure_alert_teams_failure_does_not_break_response():
    """Teams delivery failure is non-fatal."""

    class ExplodingTeams(TeamsAdapter):
        def __init__(self) -> None:
            pass

        def send_result(self, result: InvestigationResult) -> None:
            raise RuntimeError("teams webhook down")

    engine, repo = FakeEngine(), FakeRepo()
    client = _override(engine, repo, ExplodingTeams())
    try:
        with client:
            resp = client.post("/triggers/azure-alert", json=_PAYLOAD)
            assert resp.status_code == 202
            assert resp.json()["status"] == "accepted"
        assert len(repo.saved) == 1
    finally:
        _cleanup()


def test_azure_alert_uses_background_tasks_not_inline_execution():
    """H-A regression: verify the route wires engine.run into a BackgroundTask
    rather than calling it inline.

    Starlette's TestClient runs BackgroundTasks synchronously before returning
    from .post(), which masks the async behaviour we're testing. So instead we
    inspect the route signature to confirm it accepts a BackgroundTasks param
    and uses ``background_tasks.add_task``.
    """
    import inspect

    from apps.api.routes import triggers as triggers_module

    sig = inspect.signature(triggers_module.receive_azure_alert)
    param_annotations = {
        name: getattr(p.annotation, "__name__", str(p.annotation))
        for name, p in sig.parameters.items()
    }
    assert "background_tasks" in param_annotations, (
        "receive_azure_alert must accept a BackgroundTasks parameter so the "
        "engine.run call can be queued instead of awaited inline."
    )
    assert param_annotations["background_tasks"] == "BackgroundTasks"

    src = inspect.getsource(triggers_module.receive_azure_alert)
    assert "background_tasks.add_task" in src, (
        "receive_azure_alert must call background_tasks.add_task(...) — "
        "calling engine.run() inline would block the Azure Monitor webhook "
        "and trigger its retry-on-timeout behaviour."
    )

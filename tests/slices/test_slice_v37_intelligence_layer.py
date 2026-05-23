from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.main import app
from apps.api.routes import investigations
from corvin.core.contracts import (
    ActionType,
    ApprovalStatus,
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
from corvin.investigation.topology import build_service_topology
from corvin.storage.models import Base
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.sla import build_sla_countdown
from corvin.triggers.predictive import PredictiveMonitor


@pytest.fixture()
def sqlite_repo():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return InvestigationRepository(session_factory=Session)


def _make_result(
    *,
    service: str = "fundapis",
    env: str = "dev",
    trigger: TriggerSource = TriggerSource.MANUAL_API,
    description: str = "Heap usage climbing steadily — OOM risk detected.",
    approval_status: ApprovalStatus = ApprovalStatus.PENDING,
) -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=trigger,
        service_name=service,
        environment=env,
        description=description,
        approval_status=approval_status,
    )
    evidence = EvidenceBundle(
        request_id=req.id,
        log_analytics_apim=[
            {"ApiId": "funds-api", "BackendId": "funds-backend", "StatusCode": 503},
            {"ApiId": "funds-api", "BackendId": "funds-backend", "StatusCode": 503},
            {"ApiId": "funds-api", "BackendId": "funds-backend", "StatusCode": 200},
            {"ApiId": "partner-api", "BackendId": "partner-backend", "StatusCode": 503},
            {"ApiId": "partner-api", "BackendId": "partner-backend", "StatusCode": 503},
        ],
        aks_context={
            "pods": [
                {"name": f"{service}-0", "restart_count": 2},
                {"name": f"{service}-1", "restart_count": 2},
            ],
            "events": [
                {"reason": "CPUThrottlingHigh", "message": "CPU throttling above threshold"},
            ],
        },
        container_resource_metrics=[
            {"Name": f"{service}-0", "CounterName": "cpuUsageNanoCores", "AvgValue": 220_000_000},
            {"Name": f"{service}-0", "CounterName": "memoryWorkingSetBytes", "AvgValue": 300 * 1024 * 1024},
            {"Name": f"{service}-1", "CounterName": "cpuUsageNanoCores", "AvgValue": 180_000_000},
            {"Name": f"{service}-1", "CounterName": "memoryWorkingSetBytes", "AvgValue": 260 * 1024 * 1024},
        ],
    )
    rca = RCAOutput(
        request_id=req.id,
        summary="Memory pressure and 5xx acceleration detected.",
        root_cause="Heap growth plus restart churn.",
        confidence=RCAConfidence.HIGH,
        contributing_factors=["OOM risk", "Error spike"],
    )
    fix = FixStrategyOutput(
        request_id=req.id,
        summary="Scale and stabilize the deployment.",
        justification="More capacity will relieve pressure.",
        actions=[
            FixAction(
                title="Scale deployment",
                description="Scale fundapis to 5 replicas=5 immediately",
                action_type=ActionType.SCALE_DEPLOYMENT,
                risk_level=RiskLevel.MEDIUM,
                estimated_impact="Restore headroom.",
            )
        ],
    )
    return InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix,
    )


def test_predictive_monitor_generates_multiple_alert_types(sqlite_repo):
    sqlite_repo.save_investigation_result(_make_result())

    alerts = PredictiveMonitor(repo=sqlite_repo).refresh_alerts()

    assert len(alerts) >= 2
    assert any(alert.alert_type == "memory_pressure" for alert in alerts)
    assert any(alert.alert_type == "error_rate" for alert in alerts)


def test_repository_round_trips_predictive_trigger_and_status(sqlite_repo):
    result = _make_result(trigger=TriggerSource.PREDICTIVE, approval_status=ApprovalStatus.APPROVED)
    sqlite_repo.save_investigation_result(result)

    loaded = sqlite_repo.get_investigation_result(result.request_id)
    assert loaded is not None
    assert loaded.request.trigger_source == TriggerSource.PREDICTIVE
    assert loaded.request.approval_status == ApprovalStatus.APPROVED
    assert loaded.request.lookback_minutes == 60


def test_sla_countdown_turns_red_when_budget_is_nearly_burned():
    countdown = build_sla_countdown(
        _make_result(),
        monthly_downtime_seconds=2500,
        policy={
            "sla_target_percent": 99.9,
            "sla_month_minutes": 43200,
            "sla_amber_seconds": 7200,
            "sla_red_seconds": 1800,
        },
    )

    assert countdown.severity == "red"
    assert countdown.estimated_breach_in_seconds is not None


def test_topology_builder_emits_nodes_and_edges():
    topology = build_service_topology([_make_result()])

    assert any(node.kind == "service" for node in topology.nodes)
    assert any(node.kind == "api" for node in topology.nodes)
    assert any(edge.label == "routes" for edge in topology.edges)


def test_topology_builder_pod_node_includes_health_metrics():
    topology = build_service_topology([_make_result()])
    pod_nodes = [node for node in topology.nodes if node.kind == "pod"]

    assert pod_nodes
    assert all(node.restart_count is not None for node in pod_nodes)
    assert all(node.status in {"high", "recovering", "hot"} for node in pod_nodes)
    assert any(node.cpu_mcores is not None for node in pod_nodes)
    assert any(node.memory_mib is not None for node in pod_nodes)


class _FakeEngine:
    def run(self, request: InvestigationRequest) -> InvestigationResult:
        seeded = _make_result(service=request.service_name, env=request.environment, trigger=request.trigger_source, description=request.description)
        seeded.request = request
        seeded.request_id = request.id
        seeded.evidence.request_id = request.id
        seeded.rca.request_id = request.id
        seeded.fix_strategy.request_id = request.id
        return seeded


class _FakeTeams:
    def send_result(self, result: InvestigationResult) -> None:
        return None


def _client_with(sqlite_repo: InvestigationRepository):
    app.dependency_overrides[investigations.get_repository] = lambda: sqlite_repo
    app.dependency_overrides[investigations.get_engine] = lambda: _FakeEngine()
    app.dependency_overrides[investigations.get_teams_adapter] = lambda: _FakeTeams()
    return TestClient(app)


def test_predictive_alerts_endpoint_returns_200(sqlite_repo):
    sqlite_repo.save_investigation_result(_make_result())
    client = _client_with(sqlite_repo)

    response = client.get("/investigations/predictive-alerts?refresh=true")

    assert response.status_code == 200
    assert len(response.json()) >= 1
    app.dependency_overrides.clear()


def test_fix_preview_endpoint_returns_preview(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    client = _client_with(sqlite_repo)

    response = client.get(f"/investigations/{result.request_id}/fix-preview")

    assert response.status_code == 200
    assert response.json()["items"][0]["proposed_command"].startswith("kubectl scale deployment")
    app.dependency_overrides.clear()


def test_sla_endpoint_returns_countdown(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    client = _client_with(sqlite_repo)

    response = client.get(f"/investigations/{result.request_id}/sla")

    assert response.status_code == 200
    assert "severity" in response.json()
    app.dependency_overrides.clear()


def test_topology_endpoint_returns_graph(sqlite_repo):
    sqlite_repo.save_investigation_result(_make_result())
    client = _client_with(sqlite_repo)

    response = client.get("/investigations/topology")

    assert response.status_code == 200
    assert response.json()["nodes"]
    assert response.json()["edges"]
    app.dependency_overrides.clear()


def test_topology_live_endpoint_marks_unhealthy_pod_hot(monkeypatch):
    class _FakeAksAdapter:
        def list_all_pods(self):
            return {
                "services": [
                    {
                        "name": "chad-fundapis",
                        "status": "high",
                        "pods": [
                            {
                                "name": "fundapis-good-12345-abcde",
                                "phase": "Running",
                                "containers": [{"name": "main", "ready": True, "restart_count": 0}],
                            },
                            {
                                "name": "fundapis-bad-12345-zzzzz",
                                "phase": "Pending",
                                "containers": [{"name": "main", "ready": False, "restart_count": 4}],
                            },
                        ],
                    }
                ]
            }

    class _FakeContainerLogsAdapter:
        def get_resource_metrics(self, service_name: str):
            if service_name == "fundapis":
                return [
                    {"Name": "fundapis-good-12345-abcde", "CounterName": "cpuUsageNanoCores", "AvgValue": 250_000_000},
                    {"Name": "fundapis-good-12345-abcde", "CounterName": "memoryWorkingSetBytes", "AvgValue": 320 * 1024 * 1024},
                    {"Name": "fundapis-bad-12345-zzzzz", "CounterName": "cpuUsageNanoCores", "AvgValue": 90_000_000},
                    {"Name": "fundapis-bad-12345-zzzzz", "CounterName": "memoryWorkingSetBytes", "AvgValue": 140 * 1024 * 1024},
                ]
            return []

    monkeypatch.setattr("corvin.evidence.aks_adapter.AKSAdapter", _FakeAksAdapter)
    monkeypatch.setattr("corvin.evidence.container_logs_adapter.ContainerLogsAdapter", _FakeContainerLogsAdapter)

    client = TestClient(app)
    response = client.get("/investigations/topology/live")

    assert response.status_code == 200
    payload = response.json()
    pod_nodes = [n for n in payload["nodes"] if n.get("kind") == "pod"]
    assert any(n.get("status") == "high" for n in pod_nodes)
    assert any(n.get("status") == "hot" for n in pod_nodes)
    assert any("restart_count" in n for n in pod_nodes)
    assert any(n.get("cpu_mcores") is not None for n in pod_nodes)
    assert any(n.get("memory_mib") is not None for n in pod_nodes)


def test_investigate_predictive_alert_runs_pipeline(sqlite_repo):
    sqlite_repo.save_investigation_result(_make_result())
    monitor = PredictiveMonitor(repo=sqlite_repo)
    alerts = monitor.refresh_alerts()
    client = _client_with(sqlite_repo)

    response = client.post(f"/investigations/predictive-alerts/{alerts[0].id}/investigate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    stored = sqlite_repo.get_predictive_alert(alerts[0].id)
    assert stored is not None
    assert stored["status"] == "investigated"
    assert stored["investigation_request_id"] == payload["request_id"]
    app.dependency_overrides.clear()
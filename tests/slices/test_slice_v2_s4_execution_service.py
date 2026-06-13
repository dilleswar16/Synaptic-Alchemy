"""
V2 Slice 4 – ExecutionService wired to AKSAdapter.

Tests cover:
  - ActionType enum presence and values
  - FixAction.action_type field default and override
  - AKSAdapter.restart_pods / rollback_deployment / scale_deployment return shapes
  - ExecutionService.execute gate (PermissionError when not approved)
  - ExecutionService dispatches RESTART_POD, ROLLBACK, SCALE, MANUAL correctly
  - ExecutionResult aggregation (all_succeeded, automatable_count)
  - POST /investigations/{id}/execute route:
      404 when id unknown, 409 when not approved, 200 when approved
  - approval_status transitions to 'executed' after successful execute
  - ExecutionService is injectable in tests (Fake adapter, no real AKS)

No real AKS cluster is required — all unit tests use FakeAKSAdapter subclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from corvin.evidence.aks_adapter import AKSAdapter
from corvin.execution.execution_service import (
    ActionOutcome,
    ExecutionResult,
    ExecutionService,
    _parse_replicas,
)
from corvin.storage.models import Base, InvestigationRequestRow
from corvin.storage.repository import InvestigationRepository

from apps.api.main import app
from apps.api.routes.investigations import (
    get_execution_service,
    get_repository,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sqlite_session_factory():
    engine = sa_create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_request_row(sf, approval_status: str = "pending") -> str:
    with sf() as s:
        rid = "exec-test-1"
        s.add(InvestigationRequestRow(
            id=rid,
            trigger_source="manual_api",
            service_name="order-service",
            environment="production",
            description="test",
            raw_payload={},
            approval_status=approval_status,
            lookback_minutes=60,
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        ))
        s.commit()
    return rid


def _make_result(
    request_id: str = "exec-test-1",
    action_type: ActionType = ActionType.RESTART_POD,
) -> InvestigationResult:
    req = InvestigationRequest(
        id=request_id,
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="test",
    )
    return InvestigationResult(
        request_id=request_id,
        request=req,
        evidence=EvidenceBundle(request_id=request_id),
        rca=RCAOutput(
            request_id=request_id,
            summary="Heap exhaustion.",
            root_cause="JVM heap too low.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=request_id,
            summary="Restart pods.",
            justification="Heap exhaustion requires pod restart.",
            actions=[
                FixAction(
                    title="Restart order-service pods",
                    description="Rolling restart via pod deletion.",
                    action_type=action_type,
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Service recovers within 60s.",
                    requires_approval=True,
                )
            ],
        ),
    )


def _cleanup():
    app.dependency_overrides.clear()


# ── FakeAKSAdapter subclasses ─────────────────────────────────────────────────


class FakeAKSRestart(AKSAdapter):
    """Simulates successful pod restart returning two pod names."""

    def __init__(self) -> None:  # noqa: D107
        pass  # Skip kubeconfig loading

    def restart_pods(self, service_name: str, namespace: str | None = None) -> list[str]:
        return [f"{service_name}-abc123", f"{service_name}-def456"]

    def rollback_deployment(self, service_name: str, namespace: str | None = None, revision: int | None = None) -> bool:
        return False

    def scale_deployment(self, service_name: str, replicas: int, namespace: str | None = None) -> bool:
        return False


class FakeAKSRollback(AKSAdapter):
    def __init__(self) -> None:
        pass

    def restart_pods(self, service_name: str, namespace: str | None = None) -> list[str]:
        return []

    def rollback_deployment(self, service_name: str, namespace: str | None = None, revision: int | None = None) -> bool:
        return True

    def scale_deployment(self, service_name: str, replicas: int, namespace: str | None = None) -> bool:
        return False


class FakeAKSScale(AKSAdapter):
    def __init__(self) -> None:
        pass

    def restart_pods(self, service_name: str, namespace: str | None = None) -> list[str]:
        return []

    def rollback_deployment(self, service_name: str, namespace: str | None = None, revision: int | None = None) -> bool:
        return False

    def scale_deployment(self, service_name: str, replicas: int, namespace: str | None = None) -> bool:
        return True


class FakeAKSFailAll(AKSAdapter):
    def __init__(self) -> None:
        pass

    def restart_pods(self, service_name: str, namespace: str | None = None) -> list[str]:
        return []  # empty = failure

    def rollback_deployment(self, service_name: str, namespace: str | None = None, revision: int | None = None) -> bool:
        return False

    def scale_deployment(self, service_name: str, replicas: int, namespace: str | None = None) -> bool:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


# ── ActionType enum ───────────────────────────────────────────────────────────


def test_action_type_has_restart_pod():
    assert ActionType.RESTART_POD == "restart_pod"


def test_action_type_has_rollback_deployment():
    assert ActionType.ROLLBACK_DEPLOYMENT == "rollback_deployment"


def test_action_type_has_scale_deployment():
    assert ActionType.SCALE_DEPLOYMENT == "scale_deployment"


def test_action_type_has_manual():
    assert ActionType.MANUAL == "manual"


# ── FixAction.action_type field ───────────────────────────────────────────────


def test_fix_action_default_action_type_is_manual():
    action = FixAction(
        title="Do something",
        description="desc",
        risk_level=RiskLevel.LOW,
        estimated_impact="none",
    )
    assert action.action_type == ActionType.MANUAL


def test_fix_action_accepts_restart_pod():
    action = FixAction(
        title="Restart",
        description="desc",
        action_type=ActionType.RESTART_POD,
        risk_level=RiskLevel.LOW,
        estimated_impact="pods restart",
    )
    assert action.action_type == ActionType.RESTART_POD


# ── AKS adapter new methods return correct shapes ─────────────────────────────


def test_fake_aks_restart_returns_list_of_pod_names():
    adapter = FakeAKSRestart()
    result = adapter.restart_pods("order-service")
    assert isinstance(result, list)
    assert len(result) == 2
    assert all("order-service" in name for name in result)


def test_fake_aks_rollback_returns_bool():
    adapter = FakeAKSRollback()
    assert adapter.rollback_deployment("order-service") is True


def test_fake_aks_scale_returns_bool():
    adapter = FakeAKSScale()
    assert adapter.scale_deployment("order-service", replicas=3) is True


def _make_unconfigured_adapter() -> AKSAdapter:
    """Build an AKSAdapter with no Kubernetes clients, bypassing __init__.

    _ensure_clients is stubbed out so the execution methods see the
    clients-are-None state without attempting a real kubeconfig load.
    """
    adapter = AKSAdapter.__new__(AKSAdapter)
    adapter._core_v1 = None
    adapter._apps_v1 = None
    adapter._client_mode = None
    adapter._config = {"default_namespace": "default"}
    adapter._ensure_clients = lambda cfg: None
    return adapter


def test_aks_adapter_restart_pods_unconfigured_returns_empty():
    """When clients are None, restart_pods returns [] without raising."""
    adapter = _make_unconfigured_adapter()
    result = adapter.restart_pods("svc")
    assert result == []


def test_aks_adapter_rollback_unconfigured_returns_false():
    adapter = _make_unconfigured_adapter()
    assert adapter.rollback_deployment("svc") is False


def test_aks_adapter_scale_unconfigured_returns_false():
    adapter = _make_unconfigured_adapter()
    assert adapter.scale_deployment("svc", replicas=2) is False


# ── ExecutionService gate ─────────────────────────────────────────────────────


def test_execution_service_raises_permission_error_when_pending():
    svc = ExecutionService(aks=FakeAKSRestart())
    result = _make_result()
    with pytest.raises(PermissionError, match="approval_status"):
        svc.execute(result, approval_status="pending")


def test_execution_service_raises_permission_error_when_rejected():
    svc = ExecutionService(aks=FakeAKSRestart())
    result = _make_result()
    with pytest.raises(PermissionError):
        svc.execute(result, approval_status="rejected")


def test_execution_service_raises_permission_error_when_executed():
    svc = ExecutionService(aks=FakeAKSRestart())
    result = _make_result()
    with pytest.raises(PermissionError):
        svc.execute(result, approval_status="executed")


# ── ExecutionService dispatch — RESTART_POD ───────────────────────────────────


def test_execution_service_restart_pod_succeeds():
    svc = ExecutionService(aks=FakeAKSRestart())
    result = _make_result(action_type=ActionType.RESTART_POD)
    exec_result = svc.execute(result, approval_status="approved")

    assert exec_result.all_succeeded is True
    assert len(exec_result.outcomes) == 1
    outcome = exec_result.outcomes[0]
    assert outcome.action_type == ActionType.RESTART_POD
    assert outcome.success is True
    assert "order-service-abc123" in outcome.detail


def test_execution_service_restart_pod_fail_when_no_pods():
    svc = ExecutionService(aks=FakeAKSFailAll())
    result = _make_result(action_type=ActionType.RESTART_POD)
    exec_result = svc.execute(result, approval_status="approved")

    assert exec_result.all_succeeded is False
    assert exec_result.outcomes[0].success is False


# ── ExecutionService dispatch — ROLLBACK_DEPLOYMENT ──────────────────────────


def test_execution_service_rollback_succeeds():
    svc = ExecutionService(aks=FakeAKSRollback())
    result = _make_result(action_type=ActionType.ROLLBACK_DEPLOYMENT)
    exec_result = svc.execute(result, approval_status="approved")

    assert exec_result.all_succeeded is True
    assert exec_result.outcomes[0].action_type == ActionType.ROLLBACK_DEPLOYMENT


def test_execution_service_rollback_fails():
    svc = ExecutionService(aks=FakeAKSFailAll())
    result = _make_result(action_type=ActionType.ROLLBACK_DEPLOYMENT)
    exec_result = svc.execute(result, approval_status="approved")
    assert exec_result.all_succeeded is False


# ── ExecutionService dispatch — SCALE_DEPLOYMENT ─────────────────────────────


def test_execution_service_scale_succeeds_with_replicas_in_description():
    svc = ExecutionService(aks=FakeAKSScale())
    req = InvestigationRequest(
        id="scale-test",
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="test",
    )
    result = InvestigationResult(
        request_id="scale-test",
        request=req,
        evidence=EvidenceBundle(request_id="scale-test"),
        rca=RCAOutput(
            request_id="scale-test",
            summary="HPA not scaling.",
            root_cause="HPA config.",
            confidence=RCAConfidence.MEDIUM,
        ),
        fix_strategy=FixStrategyOutput(
            request_id="scale-test",
            summary="Scale up.",
            justification="Need more replicas.",
            actions=[
                FixAction(
                    title="Scale to 5 replicas",
                    description="Scale order-service replicas=5 to handle load.",
                    action_type=ActionType.SCALE_DEPLOYMENT,
                    risk_level=RiskLevel.MEDIUM,
                    estimated_impact="Handles load spike.",
                )
            ],
        ),
    )
    exec_result = svc.execute(result, approval_status="approved")
    assert exec_result.all_succeeded is True
    assert "5" in exec_result.outcomes[0].detail


def test_execution_service_scale_fails_when_no_replicas_in_description():
    svc = ExecutionService(aks=FakeAKSScale())
    req = InvestigationRequest(
        id="scale-fail",
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="test",
    )
    result = InvestigationResult(
        request_id="scale-fail",
        request=req,
        evidence=EvidenceBundle(request_id="scale-fail"),
        rca=RCAOutput(
            request_id="scale-fail", summary=".", root_cause=".", confidence=RCAConfidence.LOW
        ),
        fix_strategy=FixStrategyOutput(
            request_id="scale-fail",
            summary="Scale.",
            justification=".",
            actions=[
                FixAction(
                    title="Scale up",
                    description="No replica count specified here.",
                    action_type=ActionType.SCALE_DEPLOYMENT,
                    risk_level=RiskLevel.LOW,
                    estimated_impact="unknown",
                )
            ],
        ),
    )
    exec_result = svc.execute(result, approval_status="approved")
    assert exec_result.all_succeeded is False
    assert "replica count" in exec_result.outcomes[0].detail


# ── ExecutionService dispatch — MANUAL ────────────────────────────────────────


def test_execution_service_manual_action_is_skipped_and_succeeds():
    svc = ExecutionService(aks=FakeAKSFailAll())
    result = _make_result(action_type=ActionType.MANUAL)
    exec_result = svc.execute(result, approval_status="approved")

    assert exec_result.all_succeeded is True
    outcome = exec_result.outcomes[0]
    assert outcome.action_type == ActionType.MANUAL
    assert outcome.success is True
    assert "skipped" in outcome.detail.lower()


def test_execution_service_manual_action_not_counted_in_automatable_count():
    svc = ExecutionService(aks=FakeAKSFailAll())
    result = _make_result(action_type=ActionType.MANUAL)
    exec_result = svc.execute(result, approval_status="approved")
    assert exec_result.automatable_count == 0


# ── ExecutionResult properties ────────────────────────────────────────────────


def test_execution_result_all_succeeded_false_when_any_outcome_fails():
    exec_result = ExecutionResult(
        request_id="r1",
        outcomes=[
            ActionOutcome(ActionType.RESTART_POD, "Restart", True, "ok"),
            ActionOutcome(ActionType.ROLLBACK_DEPLOYMENT, "Rollback", False, "fail"),
        ],
    )
    assert exec_result.all_succeeded is False


def test_execution_result_all_succeeded_true_when_all_succeed():
    exec_result = ExecutionResult(
        request_id="r1",
        outcomes=[
            ActionOutcome(ActionType.RESTART_POD, "Restart", True, "ok"),
        ],
    )
    assert exec_result.all_succeeded is True


# ── _parse_replicas helper ────────────────────────────────────────────────────


def test_parse_replicas_extracts_integer():
    assert _parse_replicas("Scale replicas=5 to handle load.") == 5


def test_parse_replicas_case_insensitive():
    assert _parse_replicas("Set REPLICAS=3") == 3


def test_parse_replicas_returns_none_when_absent():
    assert _parse_replicas("No replica count here.") is None


# ── POST /execute route — 404 ─────────────────────────────────────────────────


def test_execute_route_404_unknown_id():
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        resp = client.post("/investigations/no-such-id/execute")
        assert resp.status_code == 404
    finally:
        _cleanup()


# ── POST /execute route — 409 when not approved ───────────────────────────────


def test_execute_route_409_when_pending():
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf, approval_status="pending")
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        resp = client.post(f"/investigations/{rid}/execute")
        assert resp.status_code == 409
        assert "approved" in resp.json()["detail"]
    finally:
        _cleanup()


def test_execute_route_409_when_rejected():
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf, approval_status="rejected")
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        resp = client.post(f"/investigations/{rid}/execute")
        assert resp.status_code == 409
    finally:
        _cleanup()


# ── POST /execute route — 200 when approved ───────────────────────────────────

def _make_full_result_in_repo(sf) -> str:
    """Save a full InvestigationResult to the SQLite repo and return its request_id."""
    from corvin.storage.repository import InvestigationRepository as Repo
    rid = "exec-full-1"
    repo = Repo(session_factory=sf)

    req = InvestigationRequest(
        id=rid,
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="test",
    )
    result = InvestigationResult(
        request_id=rid,
        request=req,
        evidence=EvidenceBundle(request_id=rid),
        rca=RCAOutput(
            request_id=rid,
            summary="Heap exhaustion.",
            root_cause="JVM heap too low.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=rid,
            summary="Restart pods.",
            justification="Heap exhaustion requires pod restart.",
            actions=[
                FixAction(
                    title="Restart order-service pods",
                    description="Rolling restart via pod deletion.",
                    action_type=ActionType.RESTART_POD,
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Service recovers within 60s.",
                )
            ],
        ),
    )
    repo.save_investigation_result(result)
    repo.update_approval_status(rid, ApprovalStatus.APPROVED)
    return rid


def test_execute_route_200_when_approved():
    sf = _sqlite_session_factory()
    rid = _make_full_result_in_repo(sf)
    repo = InvestigationRepository(session_factory=sf)
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        resp = client.post(f"/investigations/{rid}/execute")
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval_status"] == "executed"
        assert body["all_succeeded"] is True
        assert len(body["outcomes"]) == 1
        assert body["outcomes"][0]["action_type"] == "restart_pod"
    finally:
        _cleanup()


def test_execute_route_persists_executed_status():
    """After a successful execute, approval_status must be 'executed' in the DB."""
    sf = _sqlite_session_factory()
    rid = _make_full_result_in_repo(sf)
    repo = InvestigationRepository(session_factory=sf)
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        client.post(f"/investigations/{rid}/execute")
    finally:
        _cleanup()

    assert repo.get_approval_status(rid) == "executed"


def test_execute_route_409_when_already_executed():
    """A second execute attempt after status=executed must return 409."""
    sf = _sqlite_session_factory()
    rid = _make_full_result_in_repo(sf)
    repo = InvestigationRepository(session_factory=sf)
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        client.post(f"/investigations/{rid}/execute")  # first — succeeds
        resp = client.post(f"/investigations/{rid}/execute")  # second — 409
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_execute_route_message_on_success():
    sf = _sqlite_session_factory()
    rid = _make_full_result_in_repo(sf)
    repo = InvestigationRepository(session_factory=sf)
    svc = ExecutionService(aks=FakeAKSRestart())

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_execution_service] = lambda: svc

    try:
        client = TestClient(app)
        resp = client.post(f"/investigations/{rid}/execute")
        body = resp.json()
        assert "message" in body
        assert "success" in body["message"].lower()
    finally:
        _cleanup()

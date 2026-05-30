import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from apps.api.main import app
from corvin.core.contracts import TriggerSource

def get_fake_repo():
    from corvin.storage.repository import InvestigationRepository
    repo = MagicMock(spec=InvestigationRepository)
    return repo

def get_fake_engine():
    from corvin.investigation.engine import InvestigationEngine
    engine = MagicMock(spec=InvestigationEngine)
    return engine

@pytest.fixture
def client():
    from apps.api.routes.triggers import get_repository, get_engine
    app.dependency_overrides[get_repository] = get_fake_repo
    app.dependency_overrides[get_engine] = get_fake_engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_chaos_monkey_trigger(client):
    # Mock the underlying ChaosMonkey adapter call to avoid actual kubernetes usage
    from corvin.execution.chaos_monkey import ChaosMonkey
    original_inject = ChaosMonkey.inject_fault
    ChaosMonkey.inject_fault = MagicMock(return_value={"status": "success", "message": "Simulated kill"})
    
    resp = client.post("/triggers/chaos-monkey", json={
        "service_name": "fundapis",
        "environment": "prod",
        "fault_type": "kill_pod"
    })
    
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["chaos_status"] == "success"
    
    # Restore
    ChaosMonkey.inject_fault = original_inject

def test_chaos_monkey_inject_fault():
    from corvin.execution.chaos_monkey import ChaosMonkey
    from corvin.evidence.aks_adapter import AKSAdapter
    
    fake_aks = MagicMock(spec=AKSAdapter)
    fake_aks.restart_pods.return_value = ["pod-1"]
    
    cm = ChaosMonkey(aks_adapter=fake_aks)
    res = cm.inject_fault("test-svc", "dev", "kill_pod")
    
    assert res["status"] == "success"
    fake_aks.restart_pods.assert_called_once_with(service_name="test-svc")

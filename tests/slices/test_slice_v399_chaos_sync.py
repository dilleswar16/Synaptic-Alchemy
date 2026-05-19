import pytest
from unittest.mock import patch
from corvin.core.contracts import InvestigationResult, InvestigationRequest, RCAOutput, FixStrategyOutput, TriggerSource, ApprovalStatus, EvidenceBundle
from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter, _classify_incident, _pick_assignee
from apps.api.main import app
from fastapi.testclient import TestClient

@pytest.fixture
def mock_result():
    request = InvestigationRequest(
        id="test-123",
        service_name="auth-service",
        environment="prod",
        trigger_source=TriggerSource.MANUAL_API,
        description="Test incident",
        approval_status=ApprovalStatus.PENDING
    )
    rca = RCAOutput(
        request_id="test-123",
        summary="Test summary",
        root_cause="Database timeout",
        confidence="high"
    )
    fix = FixStrategyOutput(
        request_id="test-123",
        summary="Restart DB",
        justification="Timeout detected",
        actions=[]
    )
    evidence = EvidenceBundle(request_id="test-123")
    return InvestigationResult(
        request_id="test-123",
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix,
        completed_at="2026-05-16T12:00:00Z"
    )

def test_azure_devops_adapter_create_incident(mock_result):
    config = {
        "enabled": True,
        "org_name": "test-org",
        "project_name": "test-proj",
        "pat": "test-pat",
        "work_item_type": "Issue"
    }
    adapter = AzureDevOpsAdapter(config)
    
    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"id": 99}
        
        wi_id = adapter.create_incident(mock_result)
        
        assert wi_id == "99"
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert "test-org" in args[0]
        assert "test-proj" in args[0]
        assert kwargs["headers"]["Authorization"].startswith("Basic")

def test_sync_endpoints_exist():
    client = TestClient(app)
    resp_ado = client.post("/investigations/missing-id/sync/azure-boards")
    assert resp_ado.status_code == 404
    
    resp_snow = client.post("/investigations/missing-id/sync/servicenow")
    assert resp_snow.status_code == 404


# ── Auto-assign routing tests ─────────────────────────────────────────────

_ROUTING = {
    "code": {
        "keywords": ["exception", "database", "timeout", "heap"],
        "assignees": ["dilleswar.dilleswararao@metlife.com"],
    },
    "devops": {
        "keywords": ["pod", "aks", "kubernetes", "container", "cpu"],
        "assignees": ["chaitanyakumar.pendyala@metlife.com"],
    },
    "default_assignee": "priya.kinker@metlife.com",
}

def test_classify_incident_code():
    assert _classify_incident("NullPointerException in database query", _ROUTING) == "code"

def test_classify_incident_devops():
    assert _classify_incident("AKS pod evicted due to cpu pressure", _ROUTING) == "devops"

def test_classify_incident_default():
    assert _classify_incident("Something unusual happened", _ROUTING) == "default"

def test_pick_assignee_code():
    assert _pick_assignee("code", _ROUTING) == "dilleswar.dilleswararao@metlife.com"

def test_pick_assignee_devops():
    assert _pick_assignee("devops", _ROUTING) == "chaitanyakumar.pendyala@metlife.com"

def test_pick_assignee_default():
    assert _pick_assignee("default", _ROUTING) == "priya.kinker@metlife.com"

def test_create_incident_sets_assignee(mock_result):
    """create_incident should include System.AssignedTo when routing is configured."""
    config = {
        "enabled": True,
        "org_name": "test-org",
        "project_name": "test-proj",
        "pat": "test-pat",
        "work_item_type": "Issue",
        "assignment_routing": _ROUTING,
    }
    # root_cause is "Database timeout" → should classify as 'code'
    adapter = AzureDevOpsAdapter(config)

    captured_payload = []

    def fake_post(url, json, headers):
        captured_payload.extend(json)
        class FakeResp:
            status_code = 201
            def raise_for_status(self): pass
            def json(self): return {"id": 42}
        return FakeResp()

    with patch("httpx.Client.post", side_effect=fake_post):
        wi_id = adapter.create_incident(mock_result)

    assert wi_id == "42"
    assigned = [op for op in captured_payload if op.get("path") == "/fields/System.AssignedTo"]
    assert len(assigned) == 1
    assert assigned[0]["value"] == "dilleswar.dilleswararao@metlife.com"


# ── DORA endpoint test ────────────────────────────────────────────────────

def test_dora_endpoint_returns_200():
    client = TestClient(app)
    resp = client.get("/investigations/dora")
    assert resp.status_code == 200
    data = resp.json()
    assert "mttr_minutes" in data
    assert "mttr_trend" in data
    assert "change_failure_rate_pct" in data
    assert "deployment_frequency" in data

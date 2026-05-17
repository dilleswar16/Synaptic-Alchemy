import pytest
from unittest.mock import patch
from corvin.core.contracts import InvestigationResult, InvestigationRequest, RCAOutput, FixStrategyOutput, TriggerSource, ApprovalStatus, EvidenceBundle
from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter
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

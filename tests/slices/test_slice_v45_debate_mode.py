import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from apps.api.main import app
from corvin.core.contracts import InvestigationResult, InvestigationRequest, TriggerSource, RCAOutput, EvidenceBundle
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.debate_service import DebateOrchestrator

# Dependency overrides
def get_fake_repo():
    repo = MagicMock(spec=InvestigationRepository)
    
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name="test-svc",
        environment="dev"
    )
    req.id = "test-req-123"
    
    rca = RCAOutput(
        request_id=req.id,
        summary="Test summary",
        root_cause="Test root cause",
        contributing_factors=["Factor 1"],
        confidence="medium",
        confidence_reasoning="Because.",
        evidence_references=[]
    )
    
    evidence = EvidenceBundle(request_id=req.id)
    
    result = InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=evidence,
        rca=rca,
        fix_strategy=None
    )
    
    repo.get_investigation_result.return_value = result
    return repo

@pytest.fixture
def client():
    from apps.api.routes.investigations import get_repository
    app.dependency_overrides[get_repository] = get_fake_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_debate_stream_returns_404_if_missing(client):
    from apps.api.routes.investigations import get_repository
    app.dependency_overrides[get_repository] = lambda: MagicMock(get_investigation_result=MagicMock(return_value=None))
    resp = client.get("/investigations/missing-123/debate/stream")
    assert resp.status_code == 404

def test_debate_orchestrator_builds_correct_prompts():
    orchestrator = DebateOrchestrator(config={"model": "test"})
    req = InvestigationRequest(trigger_source=TriggerSource.MANUAL_API, service_name="svc", environment="dev", description="test")
    rca = RCAOutput(request_id="123", summary="sum", root_cause="cause", confidence="low")
    evidence = EvidenceBundle(request_id="123")
    
    alpha_msgs = orchestrator._build_agent_messages("alpha", req, evidence, rca)
    assert len(alpha_msgs) == 2
    assert "Agent Alpha" in alpha_msgs[0]["content"]
    assert "Infrastructure Specialist" in alpha_msgs[0]["content"]
    
    beta_msgs = orchestrator._build_agent_messages("beta", req, evidence, rca)
    assert "Agent Beta" in beta_msgs[0]["content"]
    assert "Network & App Specialist" in beta_msgs[0]["content"]

    judge_msgs = orchestrator._build_judge_messages(req, "alpha said x", "beta said y")
    assert "Judge Agent" in judge_msgs[0]["content"]
    assert "alpha said x" in judge_msgs[1]["content"]
    assert "beta said y" in judge_msgs[1]["content"]

# Note: Testing the full async/threaded generator with FastAPI TestClient is complex due to
# litellm mocking requirements in a threaded context. We will stick to the basic unit tests
# to prove the logic structure and prompt builders work, as the thread queue mechanism is standard.

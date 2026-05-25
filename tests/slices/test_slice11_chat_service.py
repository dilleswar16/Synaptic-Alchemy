import pytest
from unittest.mock import patch, MagicMock

from corvin.strategy.chat_service import ChatService
from corvin.core.contracts import (
    InvestigationResult, InvestigationRequest, RCAOutput, EvidenceBundle, 
    RCAConfidence, FixStrategyOutput, FixAction, ActionType, RiskLevel
)

@pytest.fixture
def mock_investigation_result():
    request = InvestigationRequest(
        id="test-req-123",
        service_name="auth-service",
        environment="prod",
        trigger_source="manual_api",
        description="High error rate"
    )
    rca = RCAOutput(
        request_id=request.id,
        summary="DB connection pool exhausted",
        root_cause="Spike in logins",
        confidence=RCAConfidence.HIGH,
        confidence_reasoning="Metrics show connections maxed out",
        contributing_factors=["No rate limiting"],
        evidence_references=[]
    )
    evidence = EvidenceBundle(
        request_id="test-req-123",
        elastic_logs=[],
        elastic_metrics=[],
        log_analytics_apim=[],
        aks_context={},
    )
    fix_strategy = FixStrategyOutput(
        request_id=request.id,
        summary="Restart service",
        justification="Clears pool",
        actions=[FixAction(
            title="Restart", 
            description="Restart pods",
            action_type=ActionType.MANUAL,
            risk_level=RiskLevel.LOW,
            estimated_impact="None"
        )]
    )
    return InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix_strategy,
        completed_at="2026-05-15T00:00:00Z"
    )

def test_chat_service_loads_runbook_correctly(mock_investigation_result):
    """Test that chat_service correctly uses load_matching_runbooks instead of get_runbook."""
    svc = ChatService()
    
    # Mock knowledge.load_matching_runbooks to return a fake runbook
    svc.knowledge.load_matching_runbooks = MagicMock(return_value=["# Auth Service Runbook\nRestart the pods."])
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock litellm.completion to return a fake stream
    class FakeChunk:
        class Choices:
            class Delta:
                content = "Hi there!"
            delta = Delta()
        choices = [Choices()]

    with patch("corvin.strategy.chat_service.litellm.completion") as mock_completion:
        mock_completion.return_value = [FakeChunk()]
        
        # Act
        generator = svc.stream_chat(mock_investigation_result, messages)
        chunks = list(generator)
        
        # Assert
        svc.knowledge.load_matching_runbooks.assert_called_once_with("auth-service")
        
        assert len(chunks) == 2
        assert 'data: {"type": "text", "text": "Hi there!"}\n\n' in chunks[0]
        assert 'data: [DONE]\n\n' in chunks[1]

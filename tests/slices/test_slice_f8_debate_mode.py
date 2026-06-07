import pytest
from pydantic import ValidationError
from corvin.core.contracts import RCAHypothesis

def test_rca_hypothesis_model():
    """Verify RCAHypothesis requires correct fields and respects constraints."""
    h = RCAHypothesis(
        id="h1",
        title="Network Partition",
        root_cause="A switch failed.",
        evidence_ids=["elastic_logs"],
        confidence_score=0.85,
        evidence_strength_pct=85,
        supporting_signals=["Ping failed"],
        refuting_signals=[],
    )
    assert h.id == "h1"
    assert h.title == "Network Partition"
    assert h.confidence_score == 0.85
    assert h.evidence_strength_pct == 85

def test_rca_hypothesis_invalid_confidence():
    """Verify validation on confidence bounds."""
    with pytest.raises(ValidationError):
        RCAHypothesis(
            id="h2",
            title="Invalid",
            root_cause="Cause",
            confidence_score=1.5,  # Too high, must be <= 1.0
            evidence_strength_pct=50,
        )

def test_rca_hypothesis_invalid_strength():
    """Verify validation on evidence strength bounds."""
    with pytest.raises(ValidationError):
        RCAHypothesis(
            id="h3",
            title="Invalid",
            root_cause="Cause",
            confidence_score=0.5,
            evidence_strength_pct=150,  # Too high, must be <= 100
        )

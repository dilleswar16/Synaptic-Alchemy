"""
Slice 7 – RCA and fix strategy contract validation tests.

Validates that:
  - RCAOutput and FixStrategyOutput accept well-formed payloads and preserve
    enum values, auto-populated timestamps, and default fields correctly.
  - Both models reject structurally invalid payloads with ValidationError.
  - RCAGenerator and FixStrategyGenerator surface ValidationError (not swallow it)
    when LiteLLM returns malformed JSON that cannot be coerced into the output shape.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from corvin.core.contracts import (
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_RCA_PAYLOAD = {
    "request_id": "req-001",
    "summary": "Backend exceptions caused elevated 5xx responses.",
    "root_cause": "The order-service returned unhandled NPEs.",
    "contributing_factors": ["traffic spike", "missing null-guard"],
    "confidence": "high",
    "evidence_references": ["elastic_logs[0]", "aks_context.events[1]"],
}

_VALID_FIX_PAYLOAD = {
    "request_id": "req-001",
    "summary": "Roll back and add null-guard.",
    "justification": "NPE root cause maps directly to the recent deployment.",
    "actions": [
        {
            "title": "Roll back deployment",
            "description": "Return to the previous stable image.",
            "risk_level": "medium",
            "estimated_impact": "Restores service health within minutes.",
            "requires_approval": True,
        }
    ],
}


def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description="APIM gateway 5xx spike",
    )


def _make_evidence(request_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        request_id=request_id,
        elastic_logs=[{"message": "NullPointerException"}],
    )


def _text_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload), parsed=None))
        ]
    )


# ---------------------------------------------------------------------------
# RCAOutput – valid payload acceptance
# ---------------------------------------------------------------------------


def test_rca_output_accepts_valid_payload_and_preserves_enums():
    rca = RCAOutput.model_validate(_VALID_RCA_PAYLOAD)

    assert rca.request_id == "req-001"
    assert rca.summary == "Backend exceptions caused elevated 5xx responses."
    assert rca.root_cause == "The order-service returned unhandled NPEs."
    assert rca.confidence is RCAConfidence.HIGH
    assert rca.contributing_factors == ["traffic spike", "missing null-guard"]
    assert rca.evidence_references == ["elastic_logs[0]", "aks_context.events[1]"]


def test_rca_output_confidence_medium_is_default():
    rca = RCAOutput(
        request_id="req-001",
        summary="Summary.",
        root_cause="Root cause.",
    )
    assert rca.confidence is RCAConfidence.MEDIUM


def test_rca_output_confidence_low_accepted():
    rca = RCAOutput.model_validate({**_VALID_RCA_PAYLOAD, "confidence": "low"})
    assert rca.confidence is RCAConfidence.LOW


def test_rca_output_generated_at_auto_populated():
    rca = RCAOutput(request_id="req-001", summary="S.", root_cause="R.")
    assert isinstance(rca.generated_at, datetime)


def test_rca_output_contributing_factors_defaults_empty():
    rca = RCAOutput(request_id="req-001", summary="S.", root_cause="R.")
    assert rca.contributing_factors == []


def test_rca_output_evidence_references_defaults_empty():
    rca = RCAOutput(request_id="req-001", summary="S.", root_cause="R.")
    assert rca.evidence_references == []


# ---------------------------------------------------------------------------
# RCAOutput – invalid payload rejection
# ---------------------------------------------------------------------------


def test_rca_output_rejects_missing_summary():
    payload = {k: v for k, v in _VALID_RCA_PAYLOAD.items() if k != "summary"}
    with pytest.raises(ValidationError) as exc_info:
        RCAOutput.model_validate(payload)
    assert "summary" in str(exc_info.value)


def test_rca_output_rejects_missing_root_cause():
    payload = {k: v for k, v in _VALID_RCA_PAYLOAD.items() if k != "root_cause"}
    with pytest.raises(ValidationError) as exc_info:
        RCAOutput.model_validate(payload)
    assert "root_cause" in str(exc_info.value)


def test_rca_output_rejects_missing_request_id():
    payload = {k: v for k, v in _VALID_RCA_PAYLOAD.items() if k != "request_id"}
    with pytest.raises(ValidationError):
        RCAOutput.model_validate(payload)


def test_rca_output_rejects_invalid_confidence_value():
    with pytest.raises(ValidationError):
        RCAOutput.model_validate({**_VALID_RCA_PAYLOAD, "confidence": "critical"})


# ---------------------------------------------------------------------------
# FixStrategyOutput – valid payload acceptance
# ---------------------------------------------------------------------------


def test_fix_strategy_output_accepts_valid_payload_with_action():
    fix = FixStrategyOutput.model_validate(_VALID_FIX_PAYLOAD)

    assert fix.request_id == "req-001"
    assert fix.summary == "Roll back and add null-guard."
    assert fix.justification == "NPE root cause maps directly to the recent deployment."
    assert len(fix.actions) == 1
    action = fix.actions[0]
    assert action.title == "Roll back deployment"
    assert action.risk_level is RiskLevel.MEDIUM
    assert action.requires_approval is True


def test_fix_strategy_output_accepts_empty_actions_list():
    fix = FixStrategyOutput.model_validate(
        {**_VALID_FIX_PAYLOAD, "actions": []}
    )
    assert fix.actions == []


def test_fix_strategy_output_generated_at_auto_populated():
    fix = FixStrategyOutput(
        request_id="req-001",
        summary="S.",
        justification="J.",
    )
    assert isinstance(fix.generated_at, datetime)


def test_fix_action_requires_approval_defaults_true():
    action = FixAction(
        title="Check logs",
        description="Review the error logs.",
        risk_level=RiskLevel.LOW,
        estimated_impact="Low",
    )
    assert action.requires_approval is True


def test_fix_action_requires_approval_can_be_set_false():
    action = FixAction(
        title="Check logs",
        description="Review the error logs.",
        risk_level=RiskLevel.LOW,
        estimated_impact="Low",
        requires_approval=False,
    )
    assert action.requires_approval is False


# ---------------------------------------------------------------------------
# FixStrategyOutput – invalid payload rejection
# ---------------------------------------------------------------------------


def test_fix_strategy_output_rejects_missing_summary():
    payload = {k: v for k, v in _VALID_FIX_PAYLOAD.items() if k != "summary"}
    with pytest.raises(ValidationError) as exc_info:
        FixStrategyOutput.model_validate(payload)
    assert "summary" in str(exc_info.value)


def test_fix_strategy_output_rejects_missing_justification():
    payload = {k: v for k, v in _VALID_FIX_PAYLOAD.items() if k != "justification"}
    with pytest.raises(ValidationError) as exc_info:
        FixStrategyOutput.model_validate(payload)
    assert "justification" in str(exc_info.value)


def test_fix_action_rejects_invalid_risk_level():
    with pytest.raises(ValidationError):
        FixAction(
            title="Act",
            description="Desc.",
            risk_level="critical",  # type: ignore[arg-type]
            estimated_impact="Unknown.",
        )


def test_fix_action_rejects_missing_title():
    with pytest.raises(ValidationError):
        FixAction(
            description="Desc.",
            risk_level=RiskLevel.LOW,
            estimated_impact="Low.",
        )


# ---------------------------------------------------------------------------
# Generator-level validation: malformed LiteLLM responses raise ValidationError
# ---------------------------------------------------------------------------


def test_rca_generator_raises_validation_error_on_malformed_response(monkeypatch):
    """
    When LiteLLM returns JSON that is structurally invalid for RCAOutput
    (missing required fields), model_validate must raise ValidationError.
    The generator must not swallow it.
    """
    request = _make_request()
    evidence = _make_evidence(request.id)

    def fake_completion(**kwargs):
        # Missing required 'root_cause' and 'summary'
        return _text_response({"request_id": request.id, "confidence": "high"})

    monkeypatch.setattr("corvin.strategy.rca_generator.litellm.completion", fake_completion)

    generator = RCAGenerator(
        config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"require_evidence_before_rca": True},
    )

    with pytest.raises(ValidationError):
        generator.generate(request, evidence)


def test_fix_strategy_generator_raises_validation_error_on_malformed_response(monkeypatch):
    """
    When LiteLLM returns JSON that is structurally invalid for FixStrategyOutput
    (missing required fields), model_validate must raise ValidationError.
    The generator must not swallow it.
    """
    request = _make_request()
    rca = RCAOutput(
        request_id=request.id,
        summary="Backend errors detected.",
        root_cause="Unhandled exception.",
    )

    def fake_completion(**kwargs):
        # Missing required 'summary' and 'justification'
        return _text_response({"request_id": request.id, "actions": []})

    monkeypatch.setattr(
        "corvin.strategy.fix_strategy_generator.litellm.completion", fake_completion
    )

    generator = FixStrategyGenerator(
        model_config={"model": "primary-model", "temperature": 0.1, "max_tokens": 512},
        policy_config={"fix_strategy_max_actions": 5, "fix_execution_mode": "review_only"},
    )

    with pytest.raises(ValidationError):
        generator.generate(request, rca)

"""
Contract model tests.

Validates that the shared Pydantic contracts behave as expected:
correct defaults, required fields enforced, enums accepted, etc.

These tests have no external dependencies and should run in any environment.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from corvin.core.contracts import (
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


# ── InvestigationRequest ──────────────────────────────────────────────────────


def test_investigation_request_generates_id():
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="Manual check",
    )
    assert req.id
    assert len(req.id) == 36  # UUID4 format


def test_investigation_request_sets_created_at():
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="dev",
        description="API trigger",
    )
    assert req.created_at is not None


def test_investigation_request_preserves_raw_payload():
    payload = {"foo": "bar", "nested": {"x": 1}}
    req = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="svc",
        environment="prod",
        description="alert",
        raw_payload=payload,
    )
    assert req.raw_payload == payload


def test_investigation_request_rejects_invalid_trigger_source():
    with pytest.raises(ValidationError):
        InvestigationRequest(
            trigger_source="not_a_valid_source",  # type: ignore[arg-type]
            service_name="svc",
            environment="dev",
            description="test",
        )


def test_two_requests_have_different_ids():
    make = lambda: InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="svc",
        environment="dev",
        description="t",
    )
    assert make().id != make().id


# ── EvidenceBundle ────────────────────────────────────────────────────────────


def test_evidence_bundle_empty_defaults():
    bundle = EvidenceBundle(request_id="test-request-id")
    assert bundle.elastic_logs == []
    assert bundle.elastic_metrics == []
    assert bundle.log_analytics_apim == []
    assert bundle.aks_context == {}


# ── FixAction ─────────────────────────────────────────────────────────────────


def test_fix_action_requires_approval_by_default():
    action = FixAction(
        title="Restart pod",
        description="Rolling restart of the deployment",
        risk_level=RiskLevel.LOW,
        estimated_impact="30s degradation",
    )
    assert action.requires_approval is True


def test_fix_action_risk_level_enum():
    action = FixAction(
        title="Scale up",
        description="Increase replica count",
        risk_level="medium",
        estimated_impact="None expected",
    )
    assert action.risk_level == RiskLevel.MEDIUM


# ── RCAOutput ─────────────────────────────────────────────────────────────────


def test_rca_output_default_confidence():
    rca = RCAOutput(
        request_id="req-1",
        summary="DB connection pool exhausted",
        root_cause="Connection leak in release 2.4",
    )
    assert rca.confidence == RCAConfidence.MEDIUM


def test_rca_output_contributing_factors_default_empty():
    rca = RCAOutput(
        request_id="req-1",
        summary="summary",
        root_cause="cause",
    )
    assert rca.contributing_factors == []

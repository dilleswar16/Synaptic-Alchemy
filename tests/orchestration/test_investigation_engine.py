"""
Investigation engine tests.

Validates that the engine correctly chains enrichment -> RCA -> fix strategy
when real (fake) implementations are injected, and that the real RCA generator
honors the no-evidence policy path without calling an LLM.
"""

from __future__ import annotations

from typing import Any

from corvin.core.contracts import (
    EvidenceBundle,
    FixStrategyOutput,
    InvestigationRequest,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.investigation.engine import InvestigationEngine
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator


# ── Fake implementations ──────────────────────────────────────────────────────


class FakeElastic(ElasticAdapter):
    def get_logs(self, service_name: str, time_range_minutes: int | None = None) -> list[dict[str, Any]]:
        return [{"message": "OOM error", "service": service_name}]

    def get_metrics(self, service_name: str, time_range_minutes: int | None = None) -> list[dict[str, Any]]:
        return [{"metric": "memory", "value": 99}]


class FakeRCAGenerator(RCAGenerator):
    def generate(
        self,
        request: InvestigationRequest,
        evidence: EvidenceBundle,
        system_prompt: str | None = None,
    ) -> RCAOutput:
        return RCAOutput(
            request_id=request.id,
            summary="Memory exhaustion detected",
            root_cause="JVM heap not sized correctly",
            contributing_factors=["traffic spike", "no autoscaling"],
            confidence=RCAConfidence.HIGH,
        )


class FakeFixStrategyGenerator(FixStrategyGenerator):
    def generate(self, request: InvestigationRequest, rca: RCAOutput) -> FixStrategyOutput:
        return FixStrategyOutput(
            request_id=request.id,
            summary="Increase JVM heap and add HPA",
            actions=[],
            justification="Based on RCA: " + rca.root_cause,
        )


def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="OOM suspected",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_engine_produces_investigation_result_with_fakes():
    engine = InvestigationEngine(
        enrichment=EnrichmentService(elastic=FakeElastic(config={})),
        rca=FakeRCAGenerator(config={}),
        fix_strategy=FakeFixStrategyGenerator(model_config={}, policy_config={}),
    )
    req = _make_request()
    result = engine.run(req)

    assert result.request_id == req.id
    assert result.rca.confidence == RCAConfidence.HIGH
    assert result.rca.root_cause == "JVM heap not sized correctly"
    assert "JVM heap" in result.fix_strategy.justification


def test_engine_result_request_id_matches_rca_and_fix_strategy():
    engine = InvestigationEngine(
        enrichment=EnrichmentService(elastic=FakeElastic(config={})),
        rca=FakeRCAGenerator(config={}),
        fix_strategy=FakeFixStrategyGenerator(model_config={}, policy_config={}),
    )
    result = engine.run(_make_request())

    assert result.rca.request_id == result.request_id
    assert result.fix_strategy.request_id == result.request_id


def test_engine_real_rca_returns_low_confidence_when_no_evidence():
    """Real RCAGenerator should return deterministic low-confidence RCA with no evidence."""
    engine = InvestigationEngine(
        enrichment=EnrichmentService(),  # all stubs, returns empty bundle
        rca=RCAGenerator(config={}, policy_config={"require_evidence_before_rca": True}),
        fix_strategy=FakeFixStrategyGenerator(model_config={}, policy_config={}),
    )
    result = engine.run(_make_request())

    assert result.rca.confidence == RCAConfidence.LOW
    assert "Insufficient evidence" in result.rca.summary

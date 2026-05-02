"""
Enrichment service tests.

Validates that EnrichmentService returns a partial EvidenceBundle when
all adapters are still stubs (NotImplementedError), and that it correctly
accumulates data when adapters are replaced with fakes.
"""

from __future__ import annotations

from typing import Any

from corvin.core.contracts import InvestigationRequest, TriggerSource
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.evidence.aks_adapter import AKSAdapter
from corvin.evidence.elastic_adapter import ElasticAdapter
from corvin.evidence.log_analytics_adapter import LogAnalyticsAdapter


# ── Fake adapters used in tests ───────────────────────────────────────────────


class FakeElastic(ElasticAdapter):
    def get_logs(self, service_name: str, time_range_minutes: int | None = None) -> list[dict[str, Any]]:
        return [{"message": "test log", "service": service_name}]

    def get_metrics(self, service_name: str, time_range_minutes: int | None = None) -> list[dict[str, Any]]:
        return [{"metric": "cpu", "value": 85}]


class FakeLogAnalytics(LogAnalyticsAdapter):
    def get_apim_logs(self, service_name: str, time_range_minutes: int | None = None) -> list[dict[str, Any]]:
        return [{"apim_event": "timeout", "service": service_name}]


class FakeAKS(AKSAdapter):
    def get_pod_context(self, service_name: str, environment: str) -> dict[str, Any]:
        return {"pods": [{"name": f"{service_name}-abc"}], "status": "running"}


def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="test investigation",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_enrichment_with_all_stubs_returns_empty_bundle():
    """Remaining stubs return empty collections; wired adapters return dicts/lists."""
    service = EnrichmentService()
    bundle = service.enrich(_make_request())
    assert bundle.elastic_logs == []
    assert bundle.elastic_metrics == []
    assert bundle.log_analytics_apim == []
    # AKS adapter is now wired — returns a dict (may be empty or contain keys
    # depending on cluster availability; we only assert it is a dict).
    assert isinstance(bundle.aks_context, dict)


def test_enrichment_with_fake_adapters_populates_bundle():
    service = EnrichmentService(
        elastic=FakeElastic(config={}),
        log_analytics=FakeLogAnalytics(config={}),
        aks=FakeAKS(config={}),
    )
    bundle = service.enrich(_make_request())
    assert len(bundle.elastic_logs) == 1
    assert bundle.elastic_logs[0]["service"] == "order-service"
    assert len(bundle.elastic_metrics) == 1
    assert len(bundle.log_analytics_apim) == 1
    assert "pods" in bundle.aks_context


def test_enrichment_bundle_has_correct_request_id():
    req = _make_request()
    service = EnrichmentService()
    bundle = service.enrich(req)
    assert bundle.request_id == req.id


# -- H-5 regression: defensive enrichment -------------------------------------


class ExplodingElastic(ElasticAdapter):
    def get_logs(self, service_name: str, time_range_minutes: int | None = None):
        raise RuntimeError("elastic offline")

    def get_metrics(self, service_name: str, time_range_minutes: int | None = None):
        raise RuntimeError("elastic offline")


class ExplodingLogAnalytics(LogAnalyticsAdapter):
    def get_apim_logs(self, service_name: str, time_range_minutes: int | None = None):
        raise RuntimeError("log analytics offline")


class ExplodingAKS(AKSAdapter):
    def get_pod_context(self, service_name: str, environment: str):
        raise RuntimeError("aks offline")


def test_enrichment_swallows_real_adapter_exceptions(caplog):
    """H-5: any non-NotImplementedError raised by an adapter must be caught,
    logged, and not propagate to the caller. The bundle should still come
    back with default empty values for the failing slots."""
    import logging

    service = EnrichmentService(
        elastic=ExplodingElastic(config={}),
        log_analytics=ExplodingLogAnalytics(config={}),
        aks=ExplodingAKS(config={}),
    )
    with caplog.at_level(logging.WARNING, logger="corvin.enrich.enrichment_service"):
        bundle = service.enrich(_make_request())

    assert bundle.elastic_logs == []
    assert bundle.elastic_metrics == []
    assert bundle.log_analytics_apim == []
    assert bundle.aks_context == {}
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "elastic offline" in msgs
    assert "log analytics offline" in msgs
    assert "aks offline" in msgs

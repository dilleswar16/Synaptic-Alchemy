"""
V3.5 Slice Tests — Corvin Score, Blast Radius, Alert Simulator

Covers:
1. BlastRadiusEstimate — pure calculation, various evidence shapes
2. get_service_score — repository method with no data and with data
3. Triggers /simulate endpoint — correct request shape + background task
4. Investigations /score endpoint — route registration and response
5. Investigations /{id}/blast-radius endpoint — route registration
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from corvin.core.contracts import (
    EvidenceBundle,
    InvestigationRequest,
    InvestigationResult,
    TriggerSource,
)
from corvin.strategy.blast_radius import BlastRadiusEstimate, estimate_blast_radius
from corvin.storage.repository import InvestigationRepository

# ── helpers ───────────────────────────────────────────────────────────────────


def _minimal_evidence(
    pods: int = 3,
    apim_rows: int = 0,
) -> EvidenceBundle:
    """Build a minimal EvidenceBundle for blast radius tests."""
    return EvidenceBundle(
        request_id="00000000-0000-0000-0000-000000000001",
        elastic_logs=[],
        elastic_metrics=[],
        log_analytics_apim=[
            {"ApiId": f"api-{i}", "StatusCode": 503}
            for i in range(apim_rows)
        ],
        aks_context={
            "pods": [{"name": f"pod-{i}", "status": "Running"} for i in range(pods)]
        },
        azure_activity_changes=[],
    )


def _default_policy() -> dict:
    return {
        "blast_radius_users_per_replica": 400,
        "blast_radius_revenue_per_user_per_min": 0.003,
        "blast_radius_currency": "GBP",
    }


# ── BlastRadiusEstimate — unit tests ─────────────────────────────────────────


class TestBlastRadiusEstimator:
    def test_basic_pod_count(self):
        evidence = _minimal_evidence(pods=4)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert isinstance(result, BlastRadiusEstimate)
        assert result.replica_count == 4
        assert result.estimated_users == 4 * 400  # 1600
        assert result.service_name == "fundapis"
        assert result.environment == "dev"

    def test_revenue_calculation(self):
        evidence = _minimal_evidence(pods=10)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        expected = round(10 * 400 * 0.003, 2)
        assert result.revenue_risk_per_min == expected
        assert result.currency == "GBP"

    def test_affected_services_includes_primary(self):
        evidence = _minimal_evidence(pods=2, apim_rows=3)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert "fundapis" in result.affected_services

    def test_downstream_api_count(self):
        evidence = _minimal_evidence(pods=2, apim_rows=5)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        # Each APIM row has a different ApiId (api-0 through api-4)
        assert result.downstream_api_count == 5

    def test_no_pods_falls_back_to_apim_count(self):
        evidence = _minimal_evidence(pods=0, apim_rows=3)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert result.replica_count == 0
        # Falls back: max(3, 1) * 400 = 1200
        assert result.estimated_users == 3 * 400

    def test_no_pods_no_apim_uses_min_one(self):
        evidence = _minimal_evidence(pods=0, apim_rows=0)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert result.replica_count == 0
        assert result.estimated_users == 1 * 400  # max(0, 1) * 400

    def test_rationale_mentions_pods_when_available(self):
        evidence = _minimal_evidence(pods=3)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert "3 pod" in result.rationale

    def test_rationale_mentions_apim_when_no_pods(self):
        evidence = _minimal_evidence(pods=0, apim_rows=2)
        result = estimate_blast_radius("fundapis", "dev", evidence, _default_policy())
        assert "APIM" in result.rationale or "apim" in result.rationale.lower() or "consumer" in result.rationale

    def test_custom_policy_values(self):
        policy = {
            "blast_radius_users_per_replica": 1000,
            "blast_radius_revenue_per_user_per_min": 0.01,
            "blast_radius_currency": "USD",
        }
        evidence = _minimal_evidence(pods=2)
        result = estimate_blast_radius("svc", "prod", evidence, policy)
        assert result.estimated_users == 2000
        assert result.currency == "USD"
        assert result.revenue_risk_per_min == round(2000 * 0.01, 2)


# ── Repository.get_service_score — unit tests ─────────────────────────────────


class TestRepositoryServiceScore:
    def test_returns_100_when_no_data(self):
        """Service with no history should return score=100 and green."""
        repo = InvestigationRepository()
        result = repo.get_service_score("nonexistent-service-xyz", "dev")
        assert result["score"] == 100
        assert result["color"] == "green"
        assert result["total"] == 0
        assert result["last_incident_at"] is None

    def test_no_data_label_is_no_data(self):
        repo = InvestigationRepository()
        result = repo.get_service_score("no-such-service", "prod")
        assert result["label"] == "No Data"

    def test_score_keys_present(self):
        repo = InvestigationRepository()
        result = repo.get_service_score("any-service", "dev")
        expected_keys = {"score", "label", "color", "total", "high_conf", "avg_mttr_minutes", "days_since_last", "last_incident_at"}
        assert expected_keys.issubset(result.keys())

    def test_score_within_bounds(self):
        """Score must always be between 0 and 100."""
        repo = InvestigationRepository()
        result = repo.get_service_score("any-service", "dev")
        assert 0 <= result["score"] <= 100


# ── API route tests — Alert Simulator ────────────────────────────────────────


class TestSimulateEndpoint:
    def _get_client(self):
        from apps.api.main import app
        return TestClient(app)

    def test_simulate_returns_202(self):
        client = self._get_client()
        response = client.post("/triggers/simulate", json={
            "service_name": "fundapis",
            "environment": "dev",
            "scenario": "hpa_failure",
        })
        assert response.status_code == 202

    def test_simulate_returns_request_id(self):
        client = self._get_client()
        response = client.post("/triggers/simulate", json={
            "service_name": "partnerapis",
            "environment": "dev",
            "scenario": "auth_errors",
        })
        data = response.json()
        assert "request_id" in data
        assert data["status"] == "accepted"
        assert data["scenario"] == "auth_errors"
        assert data["service_name"] == "partnerapis"

    def test_simulate_with_custom_description(self):
        client = self._get_client()
        response = client.post("/triggers/simulate", json={
            "service_name": "fundsso",
            "environment": "dev",
            "scenario": "memory_leak",
            "description": "Custom test description",
        })
        assert response.status_code == 202

    def test_simulate_missing_service_name_is_422(self):
        client = self._get_client()
        response = client.post("/triggers/simulate", json={
            "environment": "dev",
            "scenario": "hpa_failure",
        })
        assert response.status_code == 422

    def test_simulate_missing_scenario_is_422(self):
        client = self._get_client()
        response = client.post("/triggers/simulate", json={
            "service_name": "fundapis",
            "environment": "dev",
        })
        assert response.status_code == 422


# ── API route tests — Corvin Score ───────────────────────────────────────────


class TestScoreEndpoint:
    def _get_client(self):
        from apps.api.main import app
        return TestClient(app)

    def test_score_returns_200(self):
        client = self._get_client()
        response = client.get("/investigations/score", params={
            "service_name": "fundapis",
            "environment": "dev",
        })
        assert response.status_code == 200

    def test_score_response_has_score_key(self):
        client = self._get_client()
        response = client.get("/investigations/score", params={
            "service_name": "fundapis",
            "environment": "dev",
        })
        data = response.json()
        assert "score" in data
        assert "color" in data
        assert "label" in data

    def test_score_missing_service_name_is_422(self):
        client = self._get_client()
        response = client.get("/investigations/score", params={"environment": "dev"})
        assert response.status_code == 422

    def test_score_no_data_returns_100(self):
        client = self._get_client()
        response = client.get("/investigations/score", params={
            "service_name": "completely-unknown-service-zzz",
            "environment": "prod",
        })
        assert response.status_code == 200
        assert response.json()["score"] == 100


# ── API route tests — Blast Radius ───────────────────────────────────────────


class TestBlastRadiusEndpoint:
    def _get_client(self):
        from apps.api.main import app
        return TestClient(app)

    def test_blast_radius_404_for_unknown(self):
        client = self._get_client()
        response = client.get("/investigations/00000000-0000-0000-0000-000000000000/blast-radius")
        assert response.status_code == 404

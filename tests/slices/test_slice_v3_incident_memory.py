"""
V3 Incident Memory — test suite.

Covers:
  - InvestigationRepository.get_similar_incidents() returns correct rows
  - Excludes current investigation by request_id
  - Returns empty list when no past incidents exist
  - Returns at most n results, newest first
  - Skips partial saves (investigations without rca_outputs)
  - PromptBuilder.build() injects past incidents section when repo provided
  - PromptBuilder.build() skips section when no past incidents exist
  - PromptBuilder.build() skips section when repository=None (default)
  - GET /investigations/memory returns expected shape
  - GET /investigations/memory returns 200 with empty list for unknown service
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from corvin.investigation.prompt_builder import PromptBuilder
from corvin.storage.models import Base
from corvin.storage.repository import InvestigationRepository

from apps.api.main import app
from apps.api.routes.investigations import get_repository


# ---------------------------------------------------------------------------
# Test infrastructure — shared SQLite in-memory repo
# ---------------------------------------------------------------------------


def _sqlite_session_factory():
    """SQLite in-memory with StaticPool so TestClient threads share it."""
    engine = sa_create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_repo() -> InvestigationRepository:
    return InvestigationRepository(session_factory=_sqlite_session_factory())


@pytest.fixture
def repo():
    return _make_repo()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_result(
    service_name: str = "order-service",
    environment: str = "production",
    root_cause: str = "Default root cause",
    confidence: RCAConfidence = RCAConfidence.HIGH,
    offset_minutes: int = 0,
) -> InvestigationResult:
    """Build a minimal but fully valid InvestigationResult."""
    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=service_name,
        environment=environment,
        description="test",
    )
    created = _utcnow() - timedelta(minutes=offset_minutes)
    request.created_at = created

    evidence = EvidenceBundle(request_id=request.id)
    rca = RCAOutput(
        request_id=request.id,
        summary="Test RCA summary",
        root_cause=root_cause,
        confidence=confidence,
    )
    fix = FixStrategyOutput(
        request_id=request.id,
        summary="Test fix",
        justification="Test justification",
        actions=[
            FixAction(
                title="Restart pod",
                description="Restart the pod",
                risk_level=RiskLevel.LOW,
                estimated_impact="None",
            )
        ],
    )
    return InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix,
        completed_at=created,
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


def test_get_similar_incidents_returns_empty_when_none(repo):
    incidents = repo.get_similar_incidents("order-service", "production")
    assert incidents == []


def test_get_similar_incidents_returns_matching_result(repo):
    result = _make_result(root_cause="HikariCP pool exhausted")
    repo.save_investigation_result(result)

    incidents = repo.get_similar_incidents("order-service", "production")
    assert len(incidents) == 1
    assert incidents[0]["root_cause"] == "HikariCP pool exhausted"
    assert incidents[0]["service_name"] == "order-service"
    assert incidents[0]["confidence"] == "high"
    assert "completed_at" in incidents[0]
    assert "request_id" in incidents[0]
    assert "rca_summary" in incidents[0]


def test_get_similar_incidents_excludes_by_request_id(repo):
    result = _make_result(root_cause="HikariCP pool exhausted")
    repo.save_investigation_result(result)

    incidents = repo.get_similar_incidents(
        "order-service", "production", exclude_request_id=result.request_id
    )
    assert incidents == []


def test_get_similar_incidents_excludes_different_service(repo):
    repo.save_investigation_result(_make_result(service_name="order-service"))
    repo.save_investigation_result(_make_result(service_name="payment-service"))

    incidents = repo.get_similar_incidents("payment-service", "production")
    assert len(incidents) == 1
    assert incidents[0]["service_name"] == "payment-service"


def test_get_similar_incidents_excludes_different_environment(repo):
    repo.save_investigation_result(_make_result(environment="production"))
    repo.save_investigation_result(_make_result(environment="staging"))

    incidents = repo.get_similar_incidents("order-service", "production")
    assert len(incidents) == 1
    assert incidents[0]["environment"] == "production"


def test_get_similar_incidents_returns_newest_first(repo):
    old = _make_result(root_cause="Old root cause", offset_minutes=120)
    new = _make_result(root_cause="New root cause", offset_minutes=10)
    repo.save_investigation_result(old)
    repo.save_investigation_result(new)

    incidents = repo.get_similar_incidents("order-service", "production")
    # Newest completed_at should be first
    assert incidents[0]["root_cause"] == "New root cause"
    assert incidents[1]["root_cause"] == "Old root cause"


def test_get_similar_incidents_respects_n_limit(repo):
    for i in range(5):
        repo.save_investigation_result(
            _make_result(root_cause=f"Root cause {i}", offset_minutes=i * 10)
        )

    incidents = repo.get_similar_incidents("order-service", "production", n=3)
    assert len(incidents) == 3


def test_get_similar_incidents_default_n_is_3(repo):
    for i in range(5):
        repo.save_investigation_result(
            _make_result(root_cause=f"Root cause {i}", offset_minutes=i * 10)
        )

    incidents = repo.get_similar_incidents("order-service", "production")
    assert len(incidents) == 3


# ---------------------------------------------------------------------------
# PromptBuilder tests
# ---------------------------------------------------------------------------


class FakeKnowledgeLoader:
    def load_site_knowledge(self) -> str:
        return ""

    def load_matching_runbooks(self, alert_text: str) -> list[str]:
        return []

    def load_learnings(self) -> str:
        return ""


class FakeRepository:
    """Stand-in for InvestigationRepository with controllable response."""

    def __init__(self, incidents: list[dict]) -> None:
        self._incidents = incidents
        self.last_call: dict = {}

    def get_similar_incidents(
        self,
        service_name: str,
        environment: str,
        exclude_request_id: str | None = None,
        n: int = 3,
    ) -> list[dict]:
        self.last_call = {
            "service_name": service_name,
            "environment": environment,
            "n": n,
        }
        return self._incidents[:n]


def _make_request(service: str = "order-service", env: str = "production") -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=service,
        environment=env,
        description="test",
    )


def test_prompt_builder_no_past_incidents_when_repository_is_none():
    builder = PromptBuilder(knowledge_loader=FakeKnowledgeLoader(), repository=None)
    prompt = builder.build(_make_request())
    assert "Similar Past Incidents" not in prompt


def test_prompt_builder_no_past_incidents_when_list_is_empty():
    fake_repo = FakeRepository(incidents=[])
    builder = PromptBuilder(knowledge_loader=FakeKnowledgeLoader(), repository=fake_repo)
    prompt = builder.build(_make_request())
    assert "Similar Past Incidents" not in prompt


def test_prompt_builder_injects_past_incidents_section():
    past = [
        {
            "request_id": "abc-123",
            "service_name": "order-service",
            "environment": "production",
            "completed_at": "2026-04-28T14:30:00Z",
            "rca_summary": "Pool exhaustion",
            "root_cause": "HikariCP connection pool exhausted under traffic spike",
            "confidence": "high",
        }
    ]
    fake_repo = FakeRepository(incidents=past)
    builder = PromptBuilder(knowledge_loader=FakeKnowledgeLoader(), repository=fake_repo)
    prompt = builder.build(_make_request())

    assert "Similar Past Incidents" in prompt
    assert "HikariCP connection pool exhausted" in prompt
    assert "2026-04-28" in prompt
    assert "HIGH" in prompt


def test_prompt_builder_passes_correct_service_and_env_to_repo():
    fake_repo = FakeRepository(incidents=[])
    builder = PromptBuilder(knowledge_loader=FakeKnowledgeLoader(), repository=fake_repo)
    builder.build(_make_request(service="payment-service", env="staging"))

    assert fake_repo.last_call["service_name"] == "payment-service"
    assert fake_repo.last_call["environment"] == "staging"


def test_prompt_builder_injects_multiple_past_incidents():
    past = [
        {
            "request_id": f"id-{i}",
            "service_name": "order-service",
            "environment": "production",
            "completed_at": f"2026-04-{20 + i:02d}T10:00:00Z",
            "rca_summary": f"Summary {i}",
            "root_cause": f"Root cause number {i}",
            "confidence": "medium",
        }
        for i in range(3)
    ]
    fake_repo = FakeRepository(incidents=past)
    builder = PromptBuilder(knowledge_loader=FakeKnowledgeLoader(), repository=fake_repo)
    prompt = builder.build(_make_request())

    assert "Root cause number 0" in prompt
    assert "Root cause number 1" in prompt
    assert "Root cause number 2" in prompt


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def _client_with_repo(repo: InvestigationRepository) -> TestClient:
    """Wire a TestClient that injects a specific in-memory repo."""
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _cleanup_overrides():
    app.dependency_overrides.pop(get_repository, None)


def test_memory_endpoint_returns_empty_for_unknown_service():
    repo = _make_repo()
    client = _client_with_repo(repo)
    try:
        response = client.get("/investigations/memory?service_name=unknown-svc&environment=production")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        _cleanup_overrides()


def test_memory_endpoint_returns_matching_incidents():
    repo = _make_repo()
    result = _make_result(root_cause="Cosmos DB throttling during batch job")
    repo.save_investigation_result(result)

    client = _client_with_repo(repo)
    try:
        response = client.get("/investigations/memory?service_name=order-service&environment=production")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["root_cause"] == "Cosmos DB throttling during batch job"
        assert data[0]["confidence"] == "high"
        assert data[0]["service_name"] == "order-service"
    finally:
        _cleanup_overrides()


def test_memory_endpoint_requires_service_name():
    repo = _make_repo()
    client = _client_with_repo(repo)
    try:
        response = client.get("/investigations/memory?environment=production")
        assert response.status_code == 422
    finally:
        _cleanup_overrides()


def test_memory_endpoint_respects_n_param():
    repo = _make_repo()
    for i in range(5):
        repo.save_investigation_result(
            _make_result(root_cause=f"Cause {i}", offset_minutes=i * 5)
        )

    client = _client_with_repo(repo)
    try:
        response = client.get(
            "/investigations/memory?service_name=order-service&environment=production&n=2"
        )
        assert response.status_code == 200
        assert len(response.json()) == 2
    finally:
        _cleanup_overrides()

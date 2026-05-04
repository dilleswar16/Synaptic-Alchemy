"""
V3 Tests — Post-Mortem Auto-Generator & SRE Health Stats.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from corvin.core.contracts import (
    ActionType,
    ApprovalStatus,
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    PostMortemOutput,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.storage.models import Base
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.postmortem_service import PostMortemService


# ── Shared SQLite fixture ─────────────────────────────────────────────────────


@pytest.fixture()
def sqlite_repo():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return InvestigationRepository(session_factory=Session)


def _make_result(
    service: str = "order-service",
    env: str = "production",
    confidence: RCAConfidence = RCAConfidence.HIGH,
) -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name=service,
        environment=env,
        description="OOM crash detected on order-service",
    )
    evidence = EvidenceBundle(request_id=req.id)
    rca = RCAOutput(
        request_id=req.id,
        summary="Pod OOMKilled due to heap exhaustion under sustained load.",
        root_cause="JVM heap limit set too low for peak traffic.",
        contributing_factors=["Missing HPA autoscaling", "No heap alerting"],
        confidence=confidence,
        evidence_references=["ContainerLog row 142", "KubePodInventory row 7"],
    )
    fix = FixStrategyOutput(
        request_id=req.id,
        summary="Restart pod and raise JVM heap limit.",
        justification="Immediate restart recovers service; heap bump prevents recurrence.",
        actions=[
            FixAction(
                title="Restart failing pod",
                description="kubectl rollout restart",
                action_type=ActionType.RESTART_POD,
                risk_level=RiskLevel.LOW,
                estimated_impact="Service back in <60s",
            ),
            FixAction(
                title="Scale deployment to handle load",
                description="Scale replicas from 2 to 4",
                action_type=ActionType.SCALE_DEPLOYMENT,
                risk_level=RiskLevel.MEDIUM,
                estimated_impact="Distributes load to prevent OOM",
            ),
        ],
    )
    return InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix,
    )


# ── FakePostMortemService (no LLM call in tests) ──────────────────────────────


class FakePostMortemService(PostMortemService):
    """Returns a real PostMortemOutput with a canned prevention section."""

    def _generate_prevention(self, result: InvestigationResult) -> str:
        return (
            "1. Add JVM heap alerting.\n"
            "2. Configure HPA autoscaling.\n"
            "3. Add runbook for OOM incidents."
        )


# ══════════════════════════════════════════════════════════════════════════════
# Post-Mortem contract
# ══════════════════════════════════════════════════════════════════════════════


def test_postmortem_output_contract_has_required_fields():
    pm = PostMortemOutput(
        request_id="x",
        service_name="svc",
        environment="prod",
        incident_summary="summary",
        detection_timeline="timeline",
        investigation_findings="findings",
        actions_taken="actions",
        prevention_recommendations="recommendations",
        markdown="# md",
    )
    assert pm.request_id == "x"
    assert pm.markdown == "# md"
    assert pm.approved_by is None  # optional field defaults to None


# ══════════════════════════════════════════════════════════════════════════════
# PostMortemService.generate()
# ══════════════════════════════════════════════════════════════════════════════


def test_postmortem_service_generates_all_sections():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result, approved_by="alice@example.com")

    assert pm.request_id == result.request_id
    assert pm.service_name == "order-service"
    assert pm.environment == "production"
    assert pm.approved_by == "alice@example.com"


def test_postmortem_markdown_contains_all_required_headings():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result)

    md = pm.markdown
    assert "# Blameless Post-Mortem" in md
    assert "## 1. Incident Summary" in md
    assert "## 2. Detection & Investigation Timeline" in md
    assert "## 3. Root Cause & Investigation Findings" in md
    assert "## 4. Actions Taken" in md
    assert "## 5. Prevention & Future Actions" in md


def test_postmortem_markdown_includes_service_name():
    svc = FakePostMortemService()
    result = _make_result(service="checkout-service")
    pm = svc.generate(result)
    assert "checkout-service" in pm.markdown


def test_postmortem_markdown_includes_rca_root_cause():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result)
    assert "JVM heap limit" in pm.markdown


def test_postmortem_markdown_includes_fix_action_table():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result)
    assert "restart_pod" in pm.markdown
    assert "scale_deployment" in pm.markdown


def test_postmortem_detection_timeline_has_timestamps():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result)
    # ISO timestamps should appear in the table
    assert "202" in pm.detection_timeline  # year prefix


def test_postmortem_investigation_findings_has_contributing_factors():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result)
    assert "Missing HPA autoscaling" in pm.investigation_findings


def test_postmortem_approved_by_appears_in_markdown():
    svc = FakePostMortemService()
    result = _make_result()
    pm = svc.generate(result, approved_by="bob@example.com")
    assert "bob@example.com" in pm.markdown


def test_postmortem_no_actions_shows_friendly_message():
    svc = FakePostMortemService()
    result = _make_result()
    # Clear actions
    result.fix_strategy.actions = []
    pm = svc.generate(result)
    assert "No automated fix actions" in pm.actions_taken


# ══════════════════════════════════════════════════════════════════════════════
# Repository — save/get post-mortem
# ══════════════════════════════════════════════════════════════════════════════


def test_repo_save_and_get_post_mortem(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    svc = FakePostMortemService()
    pm = svc.generate(result, approved_by="alice")
    sqlite_repo.save_post_mortem(pm)

    loaded = sqlite_repo.get_post_mortem(result.request_id)
    assert loaded is not None
    assert loaded.request_id == result.request_id
    assert loaded.service_name == "order-service"
    assert loaded.approved_by == "alice"
    assert "# Blameless Post-Mortem" in loaded.markdown


def test_repo_get_post_mortem_returns_none_when_missing(sqlite_repo):
    assert sqlite_repo.get_post_mortem("nonexistent") is None


def test_repo_save_post_mortem_replaces_existing(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    svc = FakePostMortemService()
    pm1 = svc.generate(result, approved_by="v1")
    sqlite_repo.save_post_mortem(pm1)

    pm2 = svc.generate(result, approved_by="v2")
    sqlite_repo.save_post_mortem(pm2)

    loaded = sqlite_repo.get_post_mortem(result.request_id)
    assert loaded.approved_by == "v2"  # should have the updated value


# ══════════════════════════════════════════════════════════════════════════════
# API route — POST/GET /investigations/{id}/postmortem
# ══════════════════════════════════════════════════════════════════════════════


def _make_api_client(repo: InvestigationRepository, pm_svc: PostMortemService) -> TestClient:
    from apps.api.main import app
    from apps.api.routes.investigations import (
        get_postmortem_service,
        get_repository,
    )

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_postmortem_service] = lambda: pm_svc
    return TestClient(app)


def _cleanup_api():
    from apps.api.main import app
    from apps.api.routes.investigations import (
        get_postmortem_service,
        get_repository,
    )
    app.dependency_overrides.pop(get_repository, None)
    app.dependency_overrides.pop(get_postmortem_service, None)


def test_api_postmortem_returns_404_for_unknown(sqlite_repo):
    client = _make_api_client(sqlite_repo, FakePostMortemService())
    try:
        resp = client.post("/investigations/nonexistent/postmortem")
        assert resp.status_code == 404
    finally:
        _cleanup_api()


def test_api_postmortem_generates_and_returns_document(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    client = _make_api_client(sqlite_repo, FakePostMortemService())
    try:
        resp = client.post(f"/investigations/{result.request_id}/postmortem")
        assert resp.status_code == 200
        body = resp.json()
        assert body["request_id"] == result.request_id
        assert "# Blameless Post-Mortem" in body["markdown"]
        assert body["service_name"] == "order-service"
    finally:
        _cleanup_api()


def test_api_postmortem_second_call_returns_cached(sqlite_repo):
    """Second POST must return cached — not re-invoke LLM."""
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    call_count = 0

    class CountingService(FakePostMortemService):
        def generate(self, r, approved_by=None):
            nonlocal call_count
            call_count += 1
            return super().generate(r, approved_by=approved_by)

    client = _make_api_client(sqlite_repo, CountingService())
    try:
        client.post(f"/investigations/{result.request_id}/postmortem")
        client.post(f"/investigations/{result.request_id}/postmortem")
        assert call_count == 1  # second call must NOT re-generate
    finally:
        _cleanup_api()


def test_api_get_postmortem_returns_404_when_not_generated(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    client = _make_api_client(sqlite_repo, FakePostMortemService())
    try:
        resp = client.get(f"/investigations/{result.request_id}/postmortem")
        assert resp.status_code == 404
    finally:
        _cleanup_api()


def test_api_get_postmortem_returns_cached_after_generation(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    client = _make_api_client(sqlite_repo, FakePostMortemService())
    try:
        client.post(f"/investigations/{result.request_id}/postmortem")
        resp = client.get(f"/investigations/{result.request_id}/postmortem")
        assert resp.status_code == 200
        assert resp.json()["request_id"] == result.request_id
    finally:
        _cleanup_api()


# ══════════════════════════════════════════════════════════════════════════════
# SRE Health Stats — Repository
# ══════════════════════════════════════════════════════════════════════════════


def test_stats_empty_db_returns_zeros(sqlite_repo):
    stats = sqlite_repo.get_investigation_stats()
    assert stats["total_investigations"] == 0
    assert stats["today_count"] == 0
    assert stats["avg_mttr_minutes"] is None
    assert stats["auto_resolved_rate"] == 0.0
    assert stats["recent_services"] == []


def test_stats_counts_investigations(sqlite_repo):
    r1 = _make_result(service="svc-a")
    r2 = _make_result(service="svc-b")
    sqlite_repo.save_investigation_result(r1)
    sqlite_repo.save_investigation_result(r2)

    stats = sqlite_repo.get_investigation_stats()
    assert stats["total_investigations"] == 2


def test_stats_today_count_includes_current_investigations(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    stats = sqlite_repo.get_investigation_stats()
    # Investigations created right now should count as today
    assert stats["today_count"] >= 1


def test_stats_approval_distribution_counts_correctly(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    sqlite_repo.update_approval_status(result.request_id, ApprovalStatus.EXECUTED)

    stats = sqlite_repo.get_investigation_stats()
    assert stats["approval_distribution"]["executed"] == 1
    assert stats["auto_resolved_rate"] == 1.0


def test_stats_confidence_distribution_counts_rca_rows(sqlite_repo):
    r1 = _make_result(confidence=RCAConfidence.HIGH)
    r2 = _make_result(confidence=RCAConfidence.LOW)
    sqlite_repo.save_investigation_result(r1)
    sqlite_repo.save_investigation_result(r2)

    stats = sqlite_repo.get_investigation_stats()
    assert stats["confidence_distribution"]["high"] == 1
    assert stats["confidence_distribution"]["low"] == 1


def test_stats_recent_services_deduplicated(sqlite_repo):
    r1 = _make_result(service="alpha")
    r2 = _make_result(service="alpha")
    r3 = _make_result(service="beta")
    for r in [r1, r2, r3]:
        sqlite_repo.save_investigation_result(r)

    stats = sqlite_repo.get_investigation_stats()
    # alpha should appear only once
    assert stats["recent_services"].count("alpha") == 1
    assert "beta" in stats["recent_services"]


def test_stats_avg_mttr_is_computed(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    stats = sqlite_repo.get_investigation_stats()
    # MTTR should be a non-negative number (investigations created & completed "now")
    assert stats["avg_mttr_minutes"] is not None
    assert stats["avg_mttr_minutes"] >= 0.0


# ══════════════════════════════════════════════════════════════════════════════
# SRE Health Stats — API route
# ══════════════════════════════════════════════════════════════════════════════


def test_api_stats_returns_200(sqlite_repo):
    from apps.api.main import app
    from apps.api.routes.investigations import get_repository

    app.dependency_overrides[get_repository] = lambda: sqlite_repo
    try:
        client = TestClient(app)
        resp = client.get("/investigations/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_investigations" in body
        assert "avg_mttr_minutes" in body
        assert "confidence_distribution" in body
        assert "approval_distribution" in body
    finally:
        app.dependency_overrides.pop(get_repository, None)


def test_api_stats_reflects_real_data(sqlite_repo):
    from apps.api.main import app
    from apps.api.routes.investigations import get_repository

    result = _make_result(service="my-service")
    sqlite_repo.save_investigation_result(result)
    app.dependency_overrides[get_repository] = lambda: sqlite_repo
    try:
        client = TestClient(app)
        resp = client.get("/investigations/stats")
        body = resp.json()
        assert body["total_investigations"] == 1
        assert "my-service" in body["recent_services"]
    finally:
        app.dependency_overrides.pop(get_repository, None)

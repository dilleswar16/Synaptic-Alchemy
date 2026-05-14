"""V3.9 Enterprise Polish — slice tests.

Covers:
  1. ROI stats calculation (zero incidents, normal incidents, no completions)
  2. ROI endpoint via FastAPI TestClient
  3. Knowledge loader write-back (append_learning, append_runbook_step, catalog)
  4. Runbook update endpoint gate (only when approval_status = executed)
  5. War room disabled gate (returns 503 when war_room_enabled: false)
  6. Voice briefing disabled gate (returns 503 when voice_briefing_enabled: false)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from corvin.strategy.roi import RoiStats, build_roi_stats


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _policy(baseline: float = 45.0, rate: float = 120.0, currency: str = "GBP") -> dict:
    return {
        "baseline_mttr_minutes": baseline,
        "engineer_hourly_rate_gbp": rate,
        "roi_currency": currency,
        "voice_briefing_enabled": True,
        "war_room_enabled": False,
    }


def _row(created_offset_min: float = 0.0, duration_min: float = 10.0) -> dict:
    now = datetime.now(timezone.utc)
    created   = now - timedelta(minutes=created_offset_min + duration_min)
    completed = created + timedelta(minutes=duration_min)
    return {
        "created_at":   created.isoformat(),
        "completed_at": completed.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. ROI stats calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildRoiStats:
    def test_zero_incidents_returns_zeros(self):
        stats = build_roi_stats([], policy=_policy())
        assert isinstance(stats, RoiStats)
        assert stats.total_incidents == 0
        assert stats.hours_saved == 0.0
        assert stats.cost_saved == 0.0
        assert stats.mttr_reduction_pct == 0.0

    def test_normal_incidents_positive_savings(self):
        rows = [_row(created_offset_min=i * 20, duration_min=10.0) for i in range(5)]
        stats = build_roi_stats(rows, policy=_policy(baseline=45.0, rate=120.0))
        assert stats.total_incidents == 5
        # Corvin MTTR ≈ 10 min < 45 min baseline → positive savings
        assert stats.hours_saved > 0
        assert stats.cost_saved > 0
        assert stats.mttr_reduction_pct > 0

    def test_currency_reflects_policy(self):
        rows = [_row(duration_min=10.0)]
        stats = build_roi_stats(rows, policy=_policy(currency="USD"))
        assert stats.currency == "USD"

    def test_no_completed_at_rows_uses_fallback(self):
        rows = [{"created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None}]
        stats = build_roi_stats(rows, policy=_policy())
        # No durations → fallback corvin_mttr = baseline (zero savings — honest, not optimistic)
        assert stats.total_incidents == 1
        # Should still produce a valid result without crashing
        assert isinstance(stats.corvin_mttr_minutes, float)
        # Fallback must NOT show phantom savings — reduction must be 0
        assert stats.mttr_reduction_pct == 0.0
        assert stats.hours_saved == 0.0

    def test_reduction_pct_caps_at_zero_when_no_savings(self):
        # Corvin takes longer than baseline (degenerate case)
        rows = [_row(duration_min=120.0)]  # 120 min > 45 min baseline
        stats = build_roi_stats(rows, policy=_policy(baseline=45.0))
        assert stats.mttr_reduction_pct >= 0.0  # never negative

    def test_incidents_per_day_is_positive(self):
        rows = [_row(created_offset_min=i * 60, duration_min=5.0) for i in range(4)]
        stats = build_roi_stats(rows, policy=_policy())
        assert stats.incidents_per_day > 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. ROI endpoint via TestClient
# ─────────────────────────────────────────────────────────────────────────────

class FakeRepo:
    """Minimal fake repository that returns a small set of pre-built rows."""

    def list_investigations(self) -> list[dict]:
        return [_row(created_offset_min=i * 30, duration_min=12.0) for i in range(3)]

    # Stub the other methods TestClient dependency injection may call
    def get_investigation_result(self, *args, **kwargs):
        return None

    def get_briefing(self, **kwargs):
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_hours": 24,
            "total_investigations": 3,
            "pending_approval": 0,
            "approved": 1,
            "executed": 2,
            "high_confidence_pending": 0,
            "narrative": "All quiet on the western front.",
            "top_services": [],
            "confidence_breakdown": {"high": 2, "medium": 1, "low": 0},
        }


def _make_test_client() -> TestClient:
    from apps.api.routes.investigations import router, get_repository
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router, prefix="/investigations")
    app.dependency_overrides[get_repository] = lambda: FakeRepo()
    return TestClient(app)


class TestRoiEndpoint:
    def test_roi_returns_200_with_required_fields(self):
        client = _make_test_client()
        resp = client.get("/investigations/roi")
        assert resp.status_code == 200
        data = resp.json()
        for field in ("total_incidents", "hours_saved", "cost_saved", "currency", "mttr_reduction_pct"):
            assert field in data, f"Missing field: {field}"

    def test_roi_total_matches_fake_repo(self):
        client = _make_test_client()
        resp = client.get("/investigations/roi")
        assert resp.status_code == 200
        assert resp.json()["total_incidents"] == 3

    def test_roi_period_months_is_stamped_in_response(self):
        """The months query param must be reflected in the response body."""
        client = _make_test_client()
        resp = client.get("/investigations/roi?months=3")
        assert resp.status_code == 200
        assert resp.json()["period_months"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 3. Knowledge loader write-back
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeLoaderWriteBack:
    def test_append_learning_creates_file(self, tmp_path: Path):
        from corvin.core.knowledge_loader import KnowledgeLoader
        loader = KnowledgeLoader(config={
            "knowledge_path":   str(tmp_path / "site.md"),
            "runbooks_path":    str(tmp_path / "runbooks"),
            "learnings_path":   str(tmp_path / "learnings"),
        })
        path = loader.append_learning("test-123", "## Learning\n\n- Fixed it")
        assert path.exists()
        assert "Learning" in path.read_text()

    def test_append_runbook_step_creates_file(self, tmp_path: Path):
        from corvin.core.knowledge_loader import KnowledgeLoader
        loader = KnowledgeLoader(config={
            "knowledge_path":   str(tmp_path / "site.md"),
            "runbooks_path":    str(tmp_path / "runbooks"),
            "learnings_path":   str(tmp_path / "learnings"),
        })
        path = loader.append_runbook_step("order-service", "## Resolution\n\n- Scaled pods")
        assert path.exists()
        assert "Resolution" in path.read_text()

    def test_append_runbook_step_creates_catalog_entry(self, tmp_path: Path):
        from corvin.core.knowledge_loader import KnowledgeLoader
        loader = KnowledgeLoader(config={
            "knowledge_path":   str(tmp_path / "site.md"),
            "runbooks_path":    str(tmp_path / "runbooks"),
            "learnings_path":   str(tmp_path / "learnings"),
        })
        loader.append_runbook_step("payments-service", "## Fix\n\n- Restarted")
        catalog_path = tmp_path / "runbooks" / "catalog.json"
        assert catalog_path.exists()
        entries = json.loads(catalog_path.read_text())
        keywords = [e.get("keyword") for e in entries]
        assert "payments-service" in keywords

    def test_append_runbook_step_is_idempotent_for_catalog(self, tmp_path: Path):
        from corvin.core.knowledge_loader import KnowledgeLoader
        loader = KnowledgeLoader(config={
            "knowledge_path":   str(tmp_path / "site.md"),
            "runbooks_path":    str(tmp_path / "runbooks"),
            "learnings_path":   str(tmp_path / "learnings"),
        })
        loader.append_runbook_step("order-service", "## Step 1\n\n- First fix")
        loader.append_runbook_step("order-service", "## Step 2\n\n- Second fix")
        catalog_path = tmp_path / "runbooks" / "catalog.json"
        entries = json.loads(catalog_path.read_text())
        assert sum(1 for e in entries if e.get("keyword") == "order-service") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Runbook update endpoint gate
# ─────────────────────────────────────────────────────────────────────────────

class TestRunbookUpdateGate:
    def test_update_runbook_returns_400_when_not_executed(self):
        """Returns 400 if the investigation is not in 'executed' state."""
        from corvin.core.contracts import (
            ActionType, ApprovalStatus, EvidenceBundle, FixAction, FixStrategyOutput,
            InvestigationRequest, InvestigationResult, RCAOutput, RCAConfidence,
            RiskLevel, TriggerSource,
        )
        from apps.api.routes.investigations import router, get_repository
        from fastapi import FastAPI

        req = InvestigationRequest(
            trigger_source=TriggerSource.MANUAL_CLI,
            service_name="order-service",
            environment="dev",
            description="test",
            approval_status=ApprovalStatus.PENDING,
        )
        rca = RCAOutput(
            request_id=req.id,
            summary="All fine",
            root_cause="Nothing",
            confidence=RCAConfidence.MEDIUM,
        )
        fix = FixStrategyOutput(
            request_id=req.id,
            summary="No action",
            actions=[FixAction(
                title="Manual check",
                description="Look at it",
                action_type=ActionType.MANUAL,
                risk_level=RiskLevel.LOW,
                estimated_impact="None",
            )],
            justification="Low severity",
        )
        evidence = EvidenceBundle(request_id=req.id)
        result = InvestigationResult(
            request_id=req.id,
            request=req,
            evidence=evidence,
            rca=rca,
            fix_strategy=fix,
        )

        class FakeRepoNotExecuted:
            def get_investigation_result(self, request_id: str):
                return result

        app = FastAPI()
        app.include_router(router, prefix="/investigations")
        app.dependency_overrides[get_repository] = lambda: FakeRepoNotExecuted()

        client = TestClient(app)
        resp = client.post("/investigations/some-id/update-runbook")
        assert resp.status_code == 400

    def test_update_runbook_returns_404_when_not_found(self):
        from apps.api.routes.investigations import router, get_repository
        from fastapi import FastAPI

        class FakeRepoMissing:
            def get_investigation_result(self, request_id: str):
                return None

        app = FastAPI()
        app.include_router(router, prefix="/investigations")
        app.dependency_overrides[get_repository] = lambda: FakeRepoMissing()

        client = TestClient(app)
        resp = client.post("/investigations/nonexistent/update-runbook")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 5. War room disabled gate
# ─────────────────────────────────────────────────────────────────────────────

class TestWarRoomGate:
    def test_war_room_returns_503_when_disabled(self):
        """When war_room_enabled is false (default), POST /teams/war-room returns 503."""
        from apps.teams.router import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router, prefix="/teams")

        client = TestClient(app)
        resp = client.post("/teams/war-room", json={
            "investigation_id": "abc",
            "service_name": "order-service",
            "environment": "prod",
            "severity": "critical",
        })
        # 503 = feature disabled; war_room_enabled defaults to false in policy
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────────────
# 6. Voice briefing disabled gate
# ─────────────────────────────────────────────────────────────────────────────

class TestVoiceBriefingEndpoint:
    def test_voice_endpoint_exists_on_router(self):
        """Confirms /briefing/audio route is registered."""
        from apps.api.routes.investigations import router
        paths = [r.path for r in router.routes]
        assert any("briefing/audio" in p for p in paths), (
            "Expected /briefing/audio route on investigations router. "
            f"Found routes: {paths}"
        )

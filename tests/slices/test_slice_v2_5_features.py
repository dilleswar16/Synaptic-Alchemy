"""
V2.5 Tests — Investigation Replay, Audit Log, and Confidence Threshold Gate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from corvin.core.contracts import (
    ApprovalStatus,
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAConfidence,
    RCAOutput,
    TriggerSource,
    ActionType,
    RiskLevel,
)
from corvin.storage.models import Base
from corvin.storage.repository import InvestigationRepository


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
    repo = InvestigationRepository(session_factory=Session)
    return repo


def _make_result(
    service: str = "partnerapis",
    env: str = "chad",
    confidence: RCAConfidence = RCAConfidence.HIGH,
) -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name=service,
        environment=env,
        description="test",
    )
    evidence = EvidenceBundle(request_id=req.id)
    rca = RCAOutput(
        request_id=req.id,
        summary="Test RCA summary",
        root_cause="Something failed",
        confidence=confidence,
    )
    fix_strategy = FixStrategyOutput(
        request_id=req.id,
        summary="Fix strategy summary",
        justification="Because reasons",
        actions=[
            FixAction(
                title="Restart pod",
                description="Restart the failing pod",
                action_type=ActionType.RESTART_POD,
                risk_level=RiskLevel.LOW,
                estimated_impact="Service back in 30s",
            )
        ],
    )
    return InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix_strategy,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1: Investigation Replay
# ══════════════════════════════════════════════════════════════════════════════


def test_replay_returns_none_for_unknown_id(sqlite_repo):
    assert sqlite_repo.get_investigation_replay("does-not-exist") is None


def test_replay_returns_full_transparency_payload(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    payload = sqlite_repo.get_investigation_replay(result.request_id)
    assert payload is not None

    # Top-level keys
    assert payload["request_id"] == result.request_id

    # Trigger section
    assert payload["trigger"]["service_name"] == "partnerapis"
    assert payload["trigger"]["environment"] == "chad"
    assert payload["trigger"]["trigger_source"] == "manual_cli"
    assert payload["trigger"]["lookback_minutes"] == 60

    # Evidence summary
    assert "elastic_log_count" in payload["evidence_summary"]
    assert "aks_context_keys" in payload["evidence_summary"]

    # RCA section
    assert payload["rca"]["summary"] == "Test RCA summary"
    assert payload["rca"]["confidence"] == "high"

    # Fix strategy section
    assert payload["fix_strategy"]["action_count"] == 1
    assert payload["fix_strategy"]["actions"][0]["title"] == "Restart pod"


def test_replay_approval_section_initially_null(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    payload = sqlite_repo.get_investigation_replay(result.request_id)
    assert payload["approval"]["status"] == "pending"
    assert payload["approval"]["approved_by"] is None
    assert payload["approval"]["approved_at"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Feature 2: SRE Audit Log
# ══════════════════════════════════════════════════════════════════════════════


def test_audit_log_is_captured_on_approve(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    sqlite_repo.update_approval_status(
        result.request_id,
        ApprovalStatus.APPROVED,
        approved_by="alice@example.com",
    )

    payload = sqlite_repo.get_investigation_replay(result.request_id)
    assert payload["approval"]["status"] == "approved"
    assert payload["approval"]["approved_by"] == "alice@example.com"
    assert payload["approval"]["approved_at"] is not None


def test_audit_log_is_captured_on_reject(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    sqlite_repo.update_approval_status(
        result.request_id,
        ApprovalStatus.REJECTED,
        approved_by="bob@example.com",
    )

    payload = sqlite_repo.get_investigation_replay(result.request_id)
    assert payload["approval"]["status"] == "rejected"
    assert payload["approval"]["approved_by"] == "bob@example.com"


def test_audit_log_none_approved_by_leaves_column_null(sqlite_repo):
    """Calling update without approved_by must NOT erase a previous value."""
    result = _make_result()
    sqlite_repo.save_investigation_result(result)

    # First approve with a name
    sqlite_repo.update_approval_status(
        result.request_id, ApprovalStatus.APPROVED, approved_by="alice@example.com"
    )
    # Execute without approved_by — should leave the column intact
    sqlite_repo.update_approval_status(result.request_id, ApprovalStatus.EXECUTED)

    payload = sqlite_repo.get_investigation_replay(result.request_id)
    assert payload["approval"]["approved_by"] == "alice@example.com"
    assert payload["approval"]["status"] == "executed"


def test_list_investigations_includes_audit_fields(sqlite_repo):
    result = _make_result()
    sqlite_repo.save_investigation_result(result)
    sqlite_repo.update_approval_status(
        result.request_id, ApprovalStatus.APPROVED, approved_by="carol@example.com"
    )

    rows = sqlite_repo.list_investigations()
    assert len(rows) == 1
    assert rows[0]["approval_status"] == "approved"
    assert rows[0]["approved_by"] == "carol@example.com"
    assert rows[0]["approved_at"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# Feature 3: Confidence Threshold Gate
# ══════════════════════════════════════════════════════════════════════════════


from corvin.investigation.engine import _confidence_below_threshold


def test_confidence_below_threshold_low_vs_medium():
    assert _confidence_below_threshold(RCAConfidence.LOW, "medium") is True


def test_confidence_below_threshold_medium_vs_medium():
    assert _confidence_below_threshold(RCAConfidence.MEDIUM, "medium") is False


def test_confidence_below_threshold_high_vs_medium():
    assert _confidence_below_threshold(RCAConfidence.HIGH, "medium") is False


def test_confidence_below_threshold_low_vs_low():
    assert _confidence_below_threshold(RCAConfidence.LOW, "low") is False


def test_confidence_below_threshold_high_vs_high():
    assert _confidence_below_threshold(RCAConfidence.HIGH, "high") is False


def test_confidence_below_threshold_medium_vs_high():
    assert _confidence_below_threshold(RCAConfidence.MEDIUM, "high") is True


def test_confidence_below_threshold_invalid_uses_medium():
    # Invalid threshold falls back to 'medium'; HIGH is not below medium
    assert _confidence_below_threshold(RCAConfidence.HIGH, "very_sure") is False
    assert _confidence_below_threshold(RCAConfidence.LOW, "very_sure") is True


def test_investigation_result_confidence_warning_defaults_false():
    result = _make_result(confidence=RCAConfidence.HIGH)
    assert result.confidence_warning is False


def test_investigation_result_confidence_warning_can_be_set():
    result = _make_result(confidence=RCAConfidence.LOW)
    result.confidence_warning = True
    assert result.confidence_warning is True

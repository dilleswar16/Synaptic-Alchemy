"""
Slice 8 – Postgres persistence tests.

Uses a SQLite in-memory database so no running Postgres instance is required.
JSONB_COMPAT columns resolve to JSON on SQLite, giving real ORM round-trip
coverage without any production-behaviour change (Postgres still uses JSONB).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
from corvin.storage.models import Base
from corvin.storage.repository import InvestigationRepository


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_session_factory(engine):
    """Return a context-manager-yielding callable backed by *engine*."""

    @contextmanager
    def session_factory():
        session = Session(engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return session_factory


@pytest.fixture
def repo():
    """InvestigationRepository backed by a fresh SQLite in-memory database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return InvestigationRepository(session_factory=_make_session_factory(engine))


def _make_full_result() -> InvestigationResult:
    request = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name="order-service",
        environment="production",
        description="APIM 5xx spike on order endpoint",
        raw_payload={"data": {"essentials": {"alertRule": "APIM 5xx"}}},
    )
    evidence = EvidenceBundle(
        request_id=request.id,
        elastic_logs=[{"message": "NullPointerException in OrderController", "level": "ERROR"}],
        elastic_metrics=[{"metric": "jvm.heap.used", "value": 3072}],
        log_analytics_apim=[{"ResponseCode": 500, "ApiId": "/orders/checkout"}],
        aks_context={
            "pods": [{"name": "order-svc-abc", "status": "CrashLoopBackOff", "restarts": 5}]
        },
    )
    rca = RCAOutput(
        request_id=request.id,
        summary="NPE in order processing caused elevated 5xx responses.",
        root_cause="Missing null-guard on discount code field after recent deploy.",
        contributing_factors=["recent deployment", "traffic spike"],
        confidence=RCAConfidence.HIGH,
        evidence_references=["elastic_logs[0]", "aks_context[0]"],
    )
    fix_strategy = FixStrategyOutput(
        request_id=request.id,
        summary="Add null-guard and roll back if NPE recurs.",
        justification="NPE root cause maps directly to the recent code change.",
        actions=[
            FixAction(
                title="Add null-guard to discount code field",
                description="Patch the null reference in OrderController.processDiscount().",
                risk_level=RiskLevel.LOW,
                estimated_impact="Eliminates NPE and restores normal 5xx rate.",
                requires_approval=True,
            )
        ],
    )
    return InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix_strategy,
    )


# ---------------------------------------------------------------------------
# save_investigation_result
# ---------------------------------------------------------------------------


def test_save_investigation_result_persists_without_error(repo):
    """save_investigation_result must not raise for a well-formed result."""
    result = _make_full_result()
    repo.save_investigation_result(result)  # must not raise


def test_save_is_idempotent(repo):
    """Calling save twice for the same request_id must not raise or duplicate rows."""
    result = _make_full_result()
    repo.save_investigation_result(result)
    repo.save_investigation_result(result)  # second call must be a no-error upsert

    loaded = repo.get_investigation_result(result.request_id)
    assert loaded is not None
    assert loaded.request_id == result.request_id


# ---------------------------------------------------------------------------
# get_investigation_result – success path
# ---------------------------------------------------------------------------


def test_get_investigation_result_returns_correct_request_id(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)

    assert loaded is not None
    assert loaded.request_id == result.request_id
    assert loaded.request.id == result.request.id


def test_get_investigation_result_reconstructs_request_fields(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)

    assert loaded.request.service_name == "order-service"
    assert loaded.request.environment == "production"
    assert loaded.request.trigger_source == TriggerSource.AZURE_ALERT
    assert loaded.request.description == "APIM 5xx spike on order endpoint"
    assert loaded.request.raw_payload == result.request.raw_payload


def test_get_investigation_result_reconstructs_rca_fields(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)

    assert loaded.rca.request_id == result.request_id
    assert loaded.rca.summary == result.rca.summary
    assert loaded.rca.root_cause == result.rca.root_cause
    assert loaded.rca.confidence == RCAConfidence.HIGH
    assert loaded.rca.contributing_factors == ["recent deployment", "traffic spike"]
    assert loaded.rca.evidence_references == ["elastic_logs[0]", "aks_context[0]"]


def test_get_investigation_result_reconstructs_fix_strategy_fields(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)

    assert loaded.fix_strategy.request_id == result.request_id
    assert loaded.fix_strategy.summary == result.fix_strategy.summary
    assert loaded.fix_strategy.justification == result.fix_strategy.justification
    assert len(loaded.fix_strategy.actions) == 1
    action = loaded.fix_strategy.actions[0]
    assert action.title == "Add null-guard to discount code field"
    assert action.risk_level == RiskLevel.LOW
    assert action.requires_approval is True


# ---------------------------------------------------------------------------
# get_investigation_result – missing id
# ---------------------------------------------------------------------------


def test_get_investigation_result_returns_none_for_unknown_id(repo):
    """A request_id that was never saved must produce None."""
    result = repo.get_investigation_result("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_get_investigation_result_returns_none_after_different_id_saved(repo):
    """Saving one result must not make an unrelated ID findable."""
    result = _make_full_result()
    repo.save_investigation_result(result)

    other = repo.get_investigation_result("aaaaaaaa-0000-0000-0000-000000000000")
    assert other is None


# ---------------------------------------------------------------------------
# EvidenceBundle JSON/list/dict field round-trip
# ---------------------------------------------------------------------------


def test_evidence_bundle_list_fields_round_trip(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)
    ev = loaded.evidence

    assert ev.elastic_logs == [{"message": "NullPointerException in OrderController", "level": "ERROR"}]
    assert ev.elastic_metrics == [{"metric": "jvm.heap.used", "value": 3072}]
    assert ev.log_analytics_apim == [{"ResponseCode": 500, "ApiId": "/orders/checkout"}]
    assert ev.azure_activity_changes == []


def test_evidence_bundle_dict_field_round_trips(repo):
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)

    assert loaded.evidence.aks_context == {
        "pods": [{"name": "order-svc-abc", "status": "CrashLoopBackOff", "restarts": 5}]
    }


def test_evidence_bundle_empty_fields_round_trip(repo):
    """An EvidenceBundle with all empty collections must round-trip cleanly."""
    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="svc",
        environment="dev",
        description="manual check",
    )
    evidence = EvidenceBundle(request_id=request.id)
    rca = RCAOutput(
        request_id=request.id,
        summary="No evidence RCA.",
        root_cause="Unknown root cause.",
        confidence=RCAConfidence.LOW,
    )
    fix_strategy = FixStrategyOutput(
        request_id=request.id,
        summary="No-op fix.",
        justification="Insufficient evidence.",
    )
    result = InvestigationResult(
        request_id=request.id,
        request=request,
        evidence=evidence,
        rca=rca,
        fix_strategy=fix_strategy,
    )

    repo.save_investigation_result(result)
    loaded = repo.get_investigation_result(result.request_id)

    assert loaded is not None
    assert loaded.evidence.elastic_logs == []
    assert loaded.evidence.elastic_metrics == []
    assert loaded.evidence.log_analytics_apim == []
    assert loaded.evidence.aks_context == {}
    assert loaded.evidence.azure_activity_changes == []
    assert loaded.fix_strategy.actions == []


def test_evidence_bundle_collected_at_is_datetime(repo):
    """collected_at must survive the round-trip as a datetime instance."""
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)
    assert isinstance(loaded.evidence.collected_at, datetime)


# ---------------------------------------------------------------------------
# Finding fix: completed_at round-trip
# ---------------------------------------------------------------------------


def test_completed_at_is_persisted_and_reloaded(repo):
    """completed_at must survive the round-trip unchanged, not get a new timestamp."""
    result = _make_full_result()
    original_completed_at = result.completed_at

    repo.save_investigation_result(result)
    loaded = repo.get_investigation_result(result.request_id)

    assert loaded.completed_at == original_completed_at


def test_completed_at_is_a_datetime(repo):
    """completed_at loaded from the DB must be a datetime instance."""
    result = _make_full_result()
    repo.save_investigation_result(result)

    loaded = repo.get_investigation_result(result.request_id)
    assert isinstance(loaded.completed_at, datetime)


def test_save_updates_completed_at_on_second_save(repo):
    """A second save with a different completed_at must overwrite the stored value."""
    result = _make_full_result()
    repo.save_investigation_result(result)

    later = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    updated = result.model_copy(update={"completed_at": later})
    repo.save_investigation_result(updated)

    loaded = repo.get_investigation_result(result.request_id)
    assert loaded.completed_at == later


# ---------------------------------------------------------------------------
# Finding fix: request-ID invariant enforcement
# ---------------------------------------------------------------------------


def _make_mismatched_result(field: str) -> InvestigationResult:
    """Build an InvestigationResult where one nested field has a wrong request_id."""
    result = _make_full_result()
    wrong_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    if field == "request":
        bad_request = result.request.model_copy(update={"id": wrong_id})
        return result.model_copy(update={"request": bad_request})
    if field == "evidence":
        bad_evidence = result.evidence.model_copy(update={"request_id": wrong_id})
        return result.model_copy(update={"evidence": bad_evidence})
    if field == "rca":
        bad_rca = result.rca.model_copy(update={"request_id": wrong_id})
        return result.model_copy(update={"rca": bad_rca})
    if field == "fix_strategy":
        bad_fix = result.fix_strategy.model_copy(update={"request_id": wrong_id})
        return result.model_copy(update={"fix_strategy": bad_fix})
    raise ValueError(f"Unknown field: {field}")


def test_save_raises_on_mismatched_request_id(repo):
    """save must raise ValueError when result.request.id != result.request_id."""
    with pytest.raises(ValueError, match="request_id mismatch"):
        repo.save_investigation_result(_make_mismatched_result("request"))


def test_save_raises_on_mismatched_evidence_request_id(repo):
    """save must raise ValueError when evidence.request_id != result.request_id."""
    with pytest.raises(ValueError, match="request_id mismatch"):
        repo.save_investigation_result(_make_mismatched_result("evidence"))


def test_save_raises_on_mismatched_rca_request_id(repo):
    """save must raise ValueError when rca.request_id != result.request_id."""
    with pytest.raises(ValueError, match="request_id mismatch"):
        repo.save_investigation_result(_make_mismatched_result("rca"))


def test_save_raises_on_mismatched_fix_strategy_request_id(repo):
    """save must raise ValueError when fix_strategy.request_id != result.request_id."""
    with pytest.raises(ValueError, match="request_id mismatch"):
        repo.save_investigation_result(_make_mismatched_result("fix_strategy"))


def test_save_does_not_partially_persist_on_mismatch(repo):
    """A mismatched save must not write any rows to the database."""
    bad = _make_mismatched_result("rca")
    with pytest.raises(ValueError):
        repo.save_investigation_result(bad)

    # Neither the top-level request_id nor any nested id should be findable.
    assert repo.get_investigation_result(bad.request_id) is None

"""
V2 Slice 6 — Streaming RCA: InvestigationStreamer + GET /investigations/stream

Tests are written with the canonical Corvin fake-adapter pattern:
  - Subclass the real service and override only what is needed.
  - No unittest.mock.patch.
  - No real Azure calls.
  - FastAPI TestClient is used for route-level tests.

Coverage
--------
Backend (InvestigationStreamer):
  1.  Evidence-started event is emitted.
  2.  Evidence-complete event includes a ``sources`` list.
  3.  RCA-started event is emitted.
  4.  RCA-complete event includes summary, root_cause, confidence.
  5.  Fix-strategy-started event is emitted.
  6.  Fix-strategy-complete event includes summary and action_count.
  7.  Complete event includes request_id.
  8.  Every event is valid JSON.
  9.  Every event string ends with ``\\n\\n`` (SSE delimiter).
  10. Error event emitted on pipeline failure — generator does NOT raise.
  11. Error event is valid JSON with a ``detail`` field.
  12. Result is persisted via repository when one is provided.
  13. Result is NOT persisted when no repository is provided.
  14. Stage order: evidence before rca before fix_strategy before complete.

Route (GET /investigations/stream):
  15. Returns HTTP 200.
  16. Content-Type is text/event-stream.
  17. Response body contains SSE-formatted data.
  18. Response contains a ``complete`` stage event.
  19. Stage order is correct in the streamed response.
  20. Missing service_name query param returns HTTP 422.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.main import app
from apps.api.routes.investigations import get_repository, get_streamer
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
from corvin.enrich.enrichment_service import EnrichmentService
from corvin.investigation.stream import InvestigationStreamer
from corvin.storage.models import Base, InvestigationRequestRow
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
from corvin.strategy.rca_generator import RCAGenerator


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="streaming slice test",
    )


def _make_evidence(request_id: str) -> EvidenceBundle:
    return EvidenceBundle(
        request_id=request_id,
        elastic_logs=[{"msg": "OOM"}],
        aks_context={"pods": ["pod-abc"]},
    )


def _make_rca(request_id: str) -> RCAOutput:
    return RCAOutput(
        request_id=request_id,
        summary="Memory pressure caused OOM",
        root_cause="Heap limit too low",
        contributing_factors=["traffic spike"],
        confidence=RCAConfidence.HIGH,
    )


def _make_fix(request_id: str) -> FixStrategyOutput:
    return FixStrategyOutput(
        request_id=request_id,
        summary="Scale up pods and raise heap limit",
        actions=[
            FixAction(
                title="Restart pods",
                description="restart_pod pods",
                risk_level=RiskLevel.LOW,
                estimated_impact="brief disruption",
            )
        ],
        justification="Restarting frees heap immediately",
    )


# ── Fake services ─────────────────────────────────────────────────────────────


class FakeEnrichment(EnrichmentService):
    """Returns canned evidence without touching Azure."""

    def enrich(self, request: InvestigationRequest) -> EvidenceBundle:
        return _make_evidence(request.id)


class FakeRCA(RCAGenerator):
    """Returns canned RCA without calling an LLM."""

    def generate(self, request: InvestigationRequest, evidence: EvidenceBundle, **kwargs) -> RCAOutput:
        return _make_rca(request.id)

    def generate_stream(self, request: InvestigationRequest, evidence: EvidenceBundle, **kwargs):
        yield (None, _make_rca(request.id))


class FakeFixStrategy(FixStrategyGenerator):
    """Returns canned fix strategy without calling an LLM."""

    def generate(self, request: InvestigationRequest, rca: RCAOutput) -> FixStrategyOutput:
        return _make_fix(request.id)

    def generate_stream(self, request: InvestigationRequest, rca: RCAOutput):
        yield (None, _make_fix(request.id))


class FailingEnrichment(EnrichmentService):
    """Always raises — used to test error-event path."""

    def enrich(self, request: InvestigationRequest) -> EvidenceBundle:
        raise RuntimeError("simulated evidence failure")


def _make_streamer(repo=None) -> InvestigationStreamer:
    return InvestigationStreamer(
        enrichment=FakeEnrichment(),
        rca=FakeRCA(),
        fix_strategy=FakeFixStrategy(),
        repository=repo,
    )


def _all_events(streamer: InvestigationStreamer, request: InvestigationRequest) -> list[dict]:
    """Consume the generator and parse all SSE events into dicts."""
    events = []
    for sse_str in streamer.stream(request):
        assert sse_str.startswith("data: "), f"Expected 'data: ' prefix, got: {sse_str!r}"
        json_part = sse_str[len("data: "):].rstrip("\n")
        events.append(json.loads(json_part))
    return events


# ── SQLite in-memory test database ────────────────────────────────────────────


@pytest.fixture()
def test_repo():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    repo = InvestigationRepository.__new__(InvestigationRepository)
    repo._session_factory = session_factory
    return repo, session_factory


# ── Backend tests — InvestigationStreamer ─────────────────────────────────────


def test_streamer_emits_evidence_started_event():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    stages = [e["stage"] for e in events]
    assert "evidence" in stages
    evidence_started = next(e for e in events if e["stage"] == "evidence" and e["status"] == "started")
    assert evidence_started["message"]  # non-empty


def test_streamer_emits_evidence_complete_event_with_sources():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    ev = next(e for e in events if e["stage"] == "evidence" and e["status"] == "complete")
    assert "sources" in ev
    assert isinstance(ev["sources"], list)
    # FakeEnrichment returns elastic_logs + aks_context → 2 sources
    assert "elastic_logs" in ev["sources"]
    assert "aks_context" in ev["sources"]


def test_streamer_emits_rca_started_event():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    rca_started = next(e for e in events if e["stage"] == "rca" and e["status"] == "started")
    assert rca_started["message"]


def test_streamer_emits_rca_complete_event_with_fields():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    ev = next(e for e in events if e["stage"] == "rca" and e["status"] == "complete")
    assert ev["summary"]
    assert ev["root_cause"]
    assert ev["confidence"] == "high"


def test_streamer_emits_fix_strategy_started_event():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    ev = next(e for e in events if e["stage"] == "fix_strategy" and e["status"] == "started")
    assert ev["message"]


def test_streamer_emits_fix_strategy_complete_event_with_action_count():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    ev = next(e for e in events if e["stage"] == "fix_strategy" and e["status"] == "complete")
    assert ev["summary"]
    assert ev["action_count"] == 1


def test_streamer_emits_complete_event_with_request_id():
    streamer = _make_streamer()
    request = _make_request()
    events = _all_events(streamer, request)
    ev = next(e for e in events if e["stage"] == "complete" and e["status"] == "complete")
    assert ev["request_id"] == request.id


def test_streamer_events_are_valid_json():
    streamer = _make_streamer()
    # Generator must not raise — parse all raw strings.
    for sse_str in streamer.stream(_make_request()):
        assert sse_str.startswith("data: ")
        json_part = sse_str[len("data: "):].rstrip("\n")
        data = json.loads(json_part)   # will raise if not valid JSON
        assert isinstance(data, dict)


def test_streamer_events_are_sse_formatted():
    streamer = _make_streamer()
    for sse_str in streamer.stream(_make_request()):
        assert sse_str.startswith("data: "), f"Expected SSE data: prefix: {sse_str!r}"
        assert sse_str.endswith("\n\n"), f"Expected double-newline terminator: {sse_str!r}"


def test_streamer_stage_order():
    streamer = _make_streamer()
    events = _all_events(streamer, _make_request())
    # Extract unique stages in first-seen order.
    seen: list[str] = []
    for e in events:
        if e["stage"] not in seen:
            seen.append(e["stage"])
    expected_order = ["evidence", "rca", "fix_strategy", "complete"]
    for expected, actual in zip(expected_order, seen):
        assert expected == actual, f"Expected stage {expected!r} at position, got {actual!r}"


def test_streamer_emits_error_event_on_failure():
    streamer = InvestigationStreamer(
        enrichment=FailingEnrichment(),
        rca=FakeRCA(),
        fix_strategy=FakeFixStrategy(),
    )
    events = _all_events(streamer, _make_request())
    error_events = [e for e in events if e["stage"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["status"] == "error"
    assert "detail" in error_events[0]


def test_streamer_error_does_not_raise():
    streamer = InvestigationStreamer(
        enrichment=FailingEnrichment(),
        rca=FakeRCA(),
        fix_strategy=FakeFixStrategy(),
    )
    # Must not raise — consuming the generator should succeed.
    result = list(streamer.stream(_make_request()))
    assert len(result) >= 1  # at minimum the error event


def test_streamer_error_event_has_detail_field():
    streamer = InvestigationStreamer(
        enrichment=FailingEnrichment(),
        rca=FakeRCA(),
        fix_strategy=FakeFixStrategy(),
    )
    events = _all_events(streamer, _make_request())
    error_ev = next(e for e in events if e["stage"] == "error")
    assert "simulated evidence failure" in error_ev["detail"]


def test_streamer_persists_result_when_repository_provided(test_repo):
    repo, session_factory = test_repo
    streamer = _make_streamer(repo=repo)
    request = _make_request()
    list(streamer.stream(request))  # exhaust generator

    with session_factory() as session:
        row = session.query(InvestigationRequestRow).filter_by(id=request.id).first()
    assert row is not None
    assert row.service_name == "order-service"


def test_streamer_does_not_persist_without_repository():
    """No repository → stream completes without calling any DB layer."""
    streamer = _make_streamer(repo=None)
    events = _all_events(streamer, _make_request())
    complete = [e for e in events if e["stage"] == "complete"]
    assert len(complete) == 1  # stream still finishes normally


# ── Route tests — GET /investigations/stream ──────────────────────────────────


def _make_test_client_with_fake_streamer(repo=None):
    """Wire a TestClient that uses the fake streamer (no real Azure calls)."""
    fake_streamer = _make_streamer(repo=repo)

    app.dependency_overrides[get_streamer] = lambda: fake_streamer
    client = TestClient(app, raise_server_exceptions=False)
    return client, fake_streamer


def test_stream_route_returns_200():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        resp = client.get("/investigations/stream?service_name=test-svc")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_streamer, None)


def test_stream_route_content_type_is_sse():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        resp = client.get("/investigations/stream?service_name=test-svc")
        assert "text/event-stream" in resp.headers["content-type"]
    finally:
        app.dependency_overrides.pop(get_streamer, None)


def test_stream_route_body_contains_sse_events():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        resp = client.get("/investigations/stream?service_name=test-svc")
        # Every line that starts with "data: " must be valid JSON.
        lines = resp.text.splitlines()
        data_lines = [l[len("data: "):] for l in lines if l.startswith("data: ")]
        assert len(data_lines) > 0
        for dl in data_lines:
            parsed = json.loads(dl)
            assert "stage" in parsed
    finally:
        app.dependency_overrides.pop(get_streamer, None)


def test_stream_route_contains_complete_event():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        resp = client.get("/investigations/stream?service_name=test-svc")
        lines = resp.text.splitlines()
        events = [json.loads(l[len("data: "):]) for l in lines if l.startswith("data: ")]
        complete_events = [e for e in events if e["stage"] == "complete"]
        assert len(complete_events) == 1
    finally:
        app.dependency_overrides.pop(get_streamer, None)


def test_stream_route_stage_order():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        resp = client.get("/investigations/stream?service_name=test-svc")
        lines = resp.text.splitlines()
        events = [json.loads(l[len("data: "):]) for l in lines if l.startswith("data: ")]
        seen: list[str] = []
        for e in events:
            if e["stage"] not in seen:
                seen.append(e["stage"])
        expected = ["evidence", "rca", "fix_strategy", "complete"]
        assert seen == expected
    finally:
        app.dependency_overrides.pop(get_streamer, None)


def test_stream_route_missing_service_name_returns_422():
    client, _ = _make_test_client_with_fake_streamer()
    try:
        # service_name is a required Query param — omitting it → 422
        resp = client.get("/investigations/stream")
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_streamer, None)

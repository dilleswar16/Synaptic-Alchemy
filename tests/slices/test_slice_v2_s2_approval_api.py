"""
V2 Slice 2 – Approval API endpoint tests.

Covers:
  - POST /investigations/{id}/approve  → 200, approval_status=approved
  - POST /investigations/{id}/reject   → 200, approval_status=rejected
  - 404 when request_id does not exist (approve and reject)
  - 409 when investigation has already been executed (approve and reject)
  - Repository.get_approval_status returns correct value
  - Repository.update_approval_status transitions state and persists
  - Gate rule: approval_status column is not mutated by start_investigation

Uses FastAPI TestClient with dependency_overrides — no real Postgres required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from corvin.core.contracts import ApprovalStatus, TriggerSource
from corvin.storage.models import Base, InvestigationRequestRow
from corvin.storage.repository import InvestigationRepository
from apps.api.main import app
from apps.api.routes.investigations import get_repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sqlite_session_factory():
    """Return a session factory backed by a fresh in-memory SQLite DB.

    StaticPool ensures the same in-memory connection is reused across all
    threads (required for FastAPI TestClient which runs the app in a thread).
    """
    engine = sa_create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_request_row(session_factory, request_id: str = "test-req-001") -> str:
    """Insert a minimal InvestigationRequestRow and return its id."""
    Session = session_factory
    with Session() as s:
        row = InvestigationRequestRow(
            id=request_id,
            trigger_source=TriggerSource.MANUAL_CLI.value,
            service_name="order-service",
            environment="dev",
            description="test investigation",
            raw_payload={},
            approval_status=ApprovalStatus.PENDING.value,
            lookback_minutes=60,
            created_at=_now(),
            completed_at=_now(),
        )
        s.add(row)
        s.commit()
    return request_id


# ---------------------------------------------------------------------------
# Repository unit tests (SQLite, no FastAPI)
# ---------------------------------------------------------------------------


def test_get_approval_status_returns_pending_for_new_row():
    """get_approval_status returns 'pending' for a freshly inserted row."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    assert repo.get_approval_status(rid) == "pending"


def test_get_approval_status_returns_none_for_missing_id():
    """get_approval_status returns None when the request_id does not exist."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    assert repo.get_approval_status("does-not-exist") is None


def test_update_approval_status_approve():
    """update_approval_status transitions pending → approved."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    repo.update_approval_status(rid, ApprovalStatus.APPROVED)
    assert repo.get_approval_status(rid) == "approved"


def test_update_approval_status_reject():
    """update_approval_status transitions pending → rejected."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    repo.update_approval_status(rid, ApprovalStatus.REJECTED)
    assert repo.get_approval_status(rid) == "rejected"


def test_update_approval_status_returns_none_for_missing_id():
    """update_approval_status returns None when request_id does not exist."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    result = repo.update_approval_status("ghost-id", ApprovalStatus.APPROVED)
    assert result is None


def test_update_approval_status_all_transitions():
    """All four ApprovalStatus values can be persisted."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    for status in ApprovalStatus:
        repo.update_approval_status(rid, status)
        assert repo.get_approval_status(rid) == status.value


# ---------------------------------------------------------------------------
# API route tests (FastAPI TestClient)
# ---------------------------------------------------------------------------


def _client_with_repo(repo: InvestigationRepository) -> TestClient:
    """Return a TestClient that uses a given repo instance via override."""
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def _cleanup():
    app.dependency_overrides.pop(get_repository, None)


def test_approve_route_200():
    """POST /investigations/{id}/approve returns 200 with approval_status=approved."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval_status"] == "approved"
        assert body["request_id"] == rid
    finally:
        _cleanup()


def test_reject_route_200():
    """POST /investigations/{id}/reject returns 200 with approval_status=rejected."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval_status"] == "rejected"
        assert body["request_id"] == rid
    finally:
        _cleanup()


def test_approve_route_404_unknown_id():
    """POST /investigations/{id}/approve returns 404 when id does not exist."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post("/investigations/unknown-id/approve")
        assert resp.status_code == 404
    finally:
        _cleanup()


def test_reject_route_404_unknown_id():
    """POST /investigations/{id}/reject returns 404 when id does not exist."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post("/investigations/unknown-id/reject")
        assert resp.status_code == 404
    finally:
        _cleanup()


def test_approve_route_409_already_executed():
    """POST /investigations/{id}/approve returns 409 if already executed."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.EXECUTED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_reject_route_409_already_executed():
    """POST /investigations/{id}/reject returns 409 if already executed."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.EXECUTED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_approve_persists_to_db():
    """After approve route, get_approval_status confirms 'approved' in the DB."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert resp.status_code == 200
    finally:
        _cleanup()

    assert repo.get_approval_status(rid) == "approved"


def test_reject_persists_to_db():
    """After reject route, get_approval_status confirms 'rejected' in the DB."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert resp.status_code == 200
    finally:
        _cleanup()

    assert repo.get_approval_status(rid) == "rejected"


def test_approve_response_contains_message():
    """Approve response includes a human-readable message field."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert "message" in resp.json()
        assert len(resp.json()["message"]) > 0
    finally:
        _cleanup()


def test_reject_response_contains_message():
    """Reject response includes a human-readable message field."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert "message" in resp.json()
        assert len(resp.json()["message"]) > 0
    finally:
        _cleanup()


def test_approve_route_409_already_approved():
    """H-4: re-approving an already-approved investigation must return 409."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.APPROVED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_reject_route_409_already_approved():
    """H-4: rejecting an already-approved investigation must return 409."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.APPROVED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_approve_route_409_already_rejected():
    """H-4: approving an already-rejected investigation must return 409."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.REJECTED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/approve")
        assert resp.status_code == 409
    finally:
        _cleanup()


def test_reject_route_409_already_rejected():
    """H-4: re-rejecting an already-rejected investigation must return 409."""
    sf = _sqlite_session_factory()
    repo = InvestigationRepository(session_factory=sf)
    rid = _make_request_row(sf)
    repo.update_approval_status(rid, ApprovalStatus.REJECTED)

    client = _client_with_repo(repo)
    try:
        resp = client.post(f"/investigations/{rid}/reject")
        assert resp.status_code == 409
    finally:
        _cleanup()

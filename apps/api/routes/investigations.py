"""
Investigations REST routes.

V1: POST /investigations/ runs the full engine pipeline, persists the result,
    and delivers a Teams card when the Teams adapter is enabled.
    GET  /investigations/       returns a lightweight list of all investigations.
    GET  /investigations/{id}   loads and returns a full persisted result.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from corvin.core.contracts import InvestigationRequest, InvestigationResult, TriggerSource
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository

router = APIRouter()
_log = logging.getLogger(__name__)


# ── Dependency providers (overridable in tests) ───────────────────────────────


def get_engine() -> InvestigationEngine:
    return InvestigationEngine()


def get_repository() -> InvestigationRepository:
    return InvestigationRepository()


def get_teams_adapter() -> TeamsAdapter:
    return TeamsAdapter()


# ── Request / response schemas ────────────────────────────────────────────────


class StartInvestigationRequest(BaseModel):
    service_name: str
    environment: str
    description: str = "Manual investigation"


class InvestigationAccepted(BaseModel):
    request_id: str
    status: str
    message: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[dict])
def list_investigations(
    repo: InvestigationRepository = Depends(get_repository),
) -> list[dict]:
    """Return a lightweight summary list of all investigations, newest first."""
    return repo.list_investigations()


@router.post("/", response_model=InvestigationAccepted, status_code=200)
def start_investigation(
    body: StartInvestigationRequest,
    engine: InvestigationEngine = Depends(get_engine),
    repo: InvestigationRepository = Depends(get_repository),
    teams: TeamsAdapter = Depends(get_teams_adapter),
) -> InvestigationAccepted:
    """Run the full investigation pipeline, persist, and deliver via Teams."""
    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=body.service_name,
        environment=body.environment,
        description=body.description,
    )
    result = engine.run(request)
    repo.save_investigation_result(result)

    try:
        teams.send_result(result)
    except Exception as exc:  # Teams failure must never break the investigation response
        _log.warning("Teams delivery failed (non-fatal): %s", exc)

    return InvestigationAccepted(
        request_id=result.request_id,
        status="completed",
        message="Investigation completed and persisted.",
    )


@router.get("/{request_id}", response_model=InvestigationResult)
def get_investigation(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> InvestigationResult:
    """Return a persisted InvestigationResult by request id."""
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    return result

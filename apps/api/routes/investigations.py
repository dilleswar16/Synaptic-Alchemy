"""
Investigations REST routes.

V1: POST /investigations/ runs the full engine pipeline, persists the result,
    and delivers a Teams card when the Teams adapter is enabled.
    GET  /investigations/       returns a lightweight list of all investigations.
    GET  /investigations/{id}   loads and returns a full persisted result.

V2: POST /investigations/{id}/approve  sets approval_status → approved.
    POST /investigations/{id}/reject   sets approval_status → rejected.
    POST /investigations/{id}/execute  runs the approved fix strategy.
    Gate rule: no ExecutionService call is permitted without ApprovalStatus.APPROVED.

V2.5: GET /investigations/{id}/replay  returns full transparency payload.
      approved_by accepted as optional query param on approve/reject.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, InvestigationResult, TriggerSource
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.execution.execution_service import ExecutionService
from corvin.investigation.engine import InvestigationEngine
from corvin.investigation.stream import InvestigationStreamer
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


def get_execution_service() -> ExecutionService:
    return ExecutionService()


def get_streamer() -> InvestigationStreamer:
    return InvestigationStreamer(repository=InvestigationRepository())


# ── Request / response schemas ────────────────────────────────────────────────


class StartInvestigationRequest(BaseModel):
    service_name: str
    environment: str
    description: str = "Manual investigation"


class InvestigationAccepted(BaseModel):
    request_id: str
    status: str
    message: str


class ApprovalResponse(BaseModel):
    request_id: str
    approval_status: str
    message: str


class ExecutionResponse(BaseModel):
    request_id: str
    approval_status: str
    all_succeeded: bool
    outcomes: list[dict]
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


@router.get("/stream")
def stream_investigation(
    service_name: str = Query(..., description="Service to investigate"),
    environment: str = Query(default="production", description="Target environment"),
    description: str = Query(default="Streaming investigation", description="Optional description"),
    streamer: InvestigationStreamer = Depends(get_streamer),
) -> StreamingResponse:
    """Run a new investigation and stream stage events as Server-Sent Events (SSE).

    Query parameters
    ----------------
    service_name:  Required.  The service to investigate.
    environment:   Optional.  Defaults to ``production``.
    description:   Optional.  Freeform context string.

    SSE event shape
    ---------------
    Each event is a JSON object emitted as ``data: {json}\\n\\n``::

        { "stage": "evidence|rca|fix_strategy|complete|error",
          "status": "started|complete|error",
          "message": "<human text>",
          ...stage-specific extra fields... }

    The ``complete`` event signals the end of the stream.
    The ``error`` event signals a pipeline failure.
    """
    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=service_name,
        environment=environment,
        description=description,
    )

    return StreamingResponse(
        streamer.stream(request),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
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


@router.post("/{request_id}/approve", response_model=ApprovalResponse, status_code=200)
def approve_investigation(
    request_id: str,
    approved_by: Optional[str] = Query(default=None, description="SRE name/email for audit log"),
    repo: InvestigationRepository = Depends(get_repository),
) -> ApprovalResponse:
    """Approve an investigation's fix strategy for execution.

    Transitions approval_status: pending → approved.
    Optionally records *approved_by* (display name or email) and timestamp
    for the SRE audit trail.
    Returns 404 if the investigation does not exist.
    Returns 409 if the current state is not ``pending``.
    """
    row = repo.get_approval_status(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    if row != ApprovalStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Investigation {request_id!r} is in state {row!r}; "
                f"only investigations in 'pending' can be approved."
            ),
        )
    repo.update_approval_status(request_id, ApprovalStatus.APPROVED, approved_by=approved_by)
    return ApprovalResponse(
        request_id=request_id,
        approval_status=ApprovalStatus.APPROVED.value,
        message="Investigation approved. Fix strategy is ready for execution.",
    )


@router.post("/{request_id}/reject", response_model=ApprovalResponse, status_code=200)
def reject_investigation(
    request_id: str,
    approved_by: Optional[str] = Query(default=None, description="SRE name/email for audit log"),
    repo: InvestigationRepository = Depends(get_repository),
) -> ApprovalResponse:
    """Reject an investigation's fix strategy.

    Transitions approval_status: pending → rejected.
    Optionally records *approved_by* (the rejecting SRE) for the audit trail.
    Returns 404 if the investigation does not exist.
    Returns 409 if the current state is not ``pending``.
    """
    row = repo.get_approval_status(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    if row != ApprovalStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Investigation {request_id!r} is in state {row!r}; "
                f"only investigations in 'pending' can be rejected."
            ),
        )
    repo.update_approval_status(request_id, ApprovalStatus.REJECTED, approved_by=approved_by)
    return ApprovalResponse(
        request_id=request_id,
        approval_status=ApprovalStatus.REJECTED.value,
        message="Investigation rejected. No fix will be executed.",
    )


@router.post("/{request_id}/execute", response_model=ExecutionResponse, status_code=200)
def execute_investigation(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
    svc: ExecutionService = Depends(get_execution_service),
) -> ExecutionResponse:
    """Execute the approved fix strategy for an investigation.

    Gate rules (enforced here and defensively inside ExecutionService):
      - Returns 404 if the investigation does not exist.
      - Returns 409 if approval_status is not 'approved' (pending / rejected / already executed).

    On success transitions approval_status → executed and returns per-action outcomes.
    """
    # ── 1. Verify investigation exists ────────────────────────────────────────
    approval_status = repo.get_approval_status(request_id)
    if approval_status is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    # ── 2. Gate: must be approved ─────────────────────────────────────────────
    if approval_status != ApprovalStatus.APPROVED.value:
        status_label = approval_status or "unknown"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Investigation {request_id!r} cannot be executed: "
                f"approval_status is '{status_label}', expected 'approved'."
            ),
        )

    # ── 3. Load full result for fix strategy ──────────────────────────────────
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation {request_id!r} result not found in persistence store.",
        )

    # ── 4. Execute ────────────────────────────────────────────────────────────
    exec_result = svc.execute(result, approval_status=approval_status)

    # ── 5. Transition to EXECUTED ─────────────────────────────────────────────
    repo.update_approval_status(request_id, ApprovalStatus.EXECUTED)

    outcomes_payload = [
        {
            "action_type": o.action_type.value,
            "title": o.title,
            "success": o.success,
            "detail": o.detail,
        }
        for o in exec_result.outcomes
    ]

    _log.info(
        "ExecutionService completed for request_id=%s all_succeeded=%s",
        request_id,
        exec_result.all_succeeded,
    )

    return ExecutionResponse(
        request_id=request_id,
        approval_status=ApprovalStatus.EXECUTED.value,
        all_succeeded=exec_result.all_succeeded,
        outcomes=outcomes_payload,
        message=(
            "All actions executed successfully."
            if exec_result.all_succeeded
            else "Execution completed with one or more failures — review outcomes."
        ),
    )


@router.get("/{request_id}/replay", response_model=dict, status_code=200)
def replay_investigation(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return a full transparency / explainability payload for a completed investigation.

    Includes what triggered it, what evidence was gathered, who approved it and when,
    and the full RCA + fix strategy with all fields. Useful for audit trails, demo
    walkthroughs, and LLM explainability reviews.

    Returns 404 if the investigation is not found or incomplete.
    """
    payload = repo.get_investigation_replay(request_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation {request_id!r} not found or incomplete.",
        )
    return payload

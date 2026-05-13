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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, InvestigationResult, TriggerSource
from corvin.delivery.rca_notification import send_rca_email_if_enabled
from corvin.delivery.rca_pdf import build_rca_pdf
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.execution.execution_service import ExecutionService
from corvin.execution.preview import build_remediation_preview
from corvin.investigation.engine import InvestigationEngine
from corvin.investigation.stream import InvestigationStreamer
from corvin.investigation.topology import build_service_topology
from corvin.storage.repository import InvestigationRepository
from corvin.strategy.sla import build_sla_countdown
from corvin.strategy.postmortem_service import PostMortemService
from corvin.strategy.blast_radius import estimate_blast_radius, BlastRadiusEstimate
from corvin.core.config_loader import get_env, load_config
from corvin.triggers.predictive import PredictiveMonitor

router = APIRouter()
_log = logging.getLogger(__name__)


# ── Dependency providers (overridable in tests) ───────────────────────────────


def get_engine() -> InvestigationEngine:
    return InvestigationEngine(repository=InvestigationRepository())


def get_repository() -> InvestigationRepository:
    return InvestigationRepository()


def get_teams_adapter() -> TeamsAdapter:
    return TeamsAdapter()


def get_execution_service() -> ExecutionService:
    return ExecutionService()


def get_streamer() -> InvestigationStreamer:
    repo = InvestigationRepository()
    return InvestigationStreamer(repository=repo)


def get_postmortem_service() -> PostMortemService:
    return PostMortemService()


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


class BriefingServiceEntry(BaseModel):
    service: str
    environment: str
    count: int


class ConfidenceBreakdown(BaseModel):
    high: int
    medium: int
    low: int


class BriefingResponse(BaseModel):
    generated_at: str
    period_hours: int
    total_investigations: int
    pending_approval: int
    approved: int
    executed: int
    rejected: int
    high_confidence_pending: int
    confidence_breakdown: ConfidenceBreakdown
    top_services: List[BriefingServiceEntry]
    narrative: str


class RcaEmailRequest(BaseModel):
    recipients: list[str] | None = None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[dict])
def list_investigations(
    repo: InvestigationRepository = Depends(get_repository),
) -> list[dict]:
    """Return a lightweight summary list of all investigations, newest first."""
    return repo.list_investigations()


@router.get("/stats", response_model=dict)
def get_investigation_stats(
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return aggregated SRE health metrics from real Postgres data.

    Includes total investigation count, today's count, MTTR, confidence
    distribution, approval/execution distribution, and recent services.
    """
    return repo.get_investigation_stats()


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

    # Optional and non-fatal: auto-send RCA PDF email when configured.
    send_rca_email_if_enabled(result)

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


@router.get("/memory", response_model=list[dict])
def get_incident_memory(
    service_name: str = Query(..., description="Service to look up past incidents for"),
    environment: str = Query(default="production", description="Target environment"),
    n: int = Query(default=3, ge=1, le=10, description="Max number of past incidents to return"),
    repo: InvestigationRepository = Depends(get_repository),
) -> list[dict]:
    """Return up to *n* past completed investigations for the same service and environment.

    Used by the UI to render the 'Similar Past Incidents' card on the detail page,
    and by the LLM prompt builder to inject historical context before RCA generation.

    Each item contains:
      request_id, service_name, environment, completed_at,
      rca_summary, root_cause, confidence
    """
    return repo.get_similar_incidents(
        service_name=service_name,
        environment=environment,
        n=n,
    )


@router.get("/briefing", response_model=BriefingResponse)
def get_briefing(
    hours: int = Query(default=24, ge=1, le=168, description="Look-back window in hours"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return a Jarvis-style SRE briefing payload for the dashboard Morning Briefing widget."""
    return repo.get_briefing(hours=hours)


@router.get("/predictive-alerts", response_model=list[dict])
def get_predictive_alerts(
    refresh: bool = Query(default=True, description="Refresh predictive detections before returning."),
    repo: InvestigationRepository = Depends(get_repository),
) -> list[dict]:
    if refresh:
        monitor = PredictiveMonitor(repo=repo)
        return [alert.model_dump(mode="json") for alert in monitor.refresh_alerts()]
    return repo.list_predictive_alerts()


@router.post("/predictive-alerts/{alert_id}/investigate", response_model=InvestigationAccepted, status_code=200)
def investigate_predictive_alert(
    alert_id: str,
    engine: InvestigationEngine = Depends(get_engine),
    repo: InvestigationRepository = Depends(get_repository),
    teams: TeamsAdapter = Depends(get_teams_adapter),
) -> InvestigationAccepted:
    alert = repo.get_predictive_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Predictive alert {alert_id!r} not found.")

    request = InvestigationRequest(
        trigger_source=TriggerSource.PREDICTIVE,
        service_name=alert["service_name"],
        environment=alert["environment"],
        description=f"[PREDICTIVE] {alert['title']} — {alert['summary']}",
        raw_payload=alert,
    )
    result = engine.run(request)
    repo.save_investigation_result(result)
    repo.mark_predictive_alert_investigated(alert_id, result.request_id)

    try:
        teams.send_result(result)
    except Exception as exc:
        _log.warning("Teams delivery failed (non-fatal): %s", exc)

    send_rca_email_if_enabled(result)

    return InvestigationAccepted(
        request_id=result.request_id,
        status="completed",
        message="Predictive investigation completed and persisted.",
    )


@router.get("/topology", response_model=dict)
def get_topology(
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    topology = build_service_topology(repo.list_recent_results(limit=30))
    return topology.model_dump()


@router.get("/score", response_model=dict)
def get_service_score(
    service_name: str = Query(..., description="Service name to score"),
    environment: str = Query(default="dev", description="Target environment"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return the Corvin Score (0–100) for a specific service/environment.

    Score is calculated from incident frequency, RCA confidence, MTTR, and
    days since the last incident.  Used to render health gauges on the Dashboard.
    """
    return repo.get_service_score(service_name=service_name, environment=environment)


@router.get("/{request_id}/blast-radius", response_model=dict)
def get_blast_radius(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return a blast radius estimate for a completed investigation.

    Pulls the stored evidence bundle and computes: affected services,
    estimated users, revenue risk per minute.  No LLM call — pure calculation.
    """
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    policy = load_config("policies/investigation", get_env())
    estimate = estimate_blast_radius(
        service_name=result.request.service_name,
        environment=result.request.environment,
        evidence=result.evidence,
        policy=policy,
    )
    return estimate.model_dump()


@router.get("/{request_id}/sla", response_model=dict)
def get_sla_countdown(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    policy = load_config("policies/investigation", get_env())
    countdown = build_sla_countdown(
        result,
        monthly_downtime_seconds=repo.get_monthly_downtime_seconds(
            service_name=result.request.service_name,
            environment=result.request.environment,
        ),
        policy=policy,
    )
    return countdown.model_dump()


@router.get("/{request_id}/fix-preview", response_model=dict)
def get_fix_preview(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    return build_remediation_preview(result).model_dump()


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


@router.get("/{request_id}/rca.pdf", response_class=Response)
def get_rca_pdf(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> Response:
    """Generate and return a structured RCA report as PDF."""
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    pdf_bytes = build_rca_pdf(result)
    filename = f"corvin-rca-{request_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{request_id}/rca/email", response_model=dict, status_code=200)
def email_rca_pdf(
    request_id: str,
    body: RcaEmailRequest = Body(default=RcaEmailRequest()),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Send the RCA PDF report by email (best-effort, config-driven SMTP)."""
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    sent = send_rca_email_if_enabled(result, recipients=body.recipients, force=True)
    if not sent:
        return {
            "request_id": request_id,
            "sent": False,
            "message": "Email not sent. Check email integration config and recipients.",
        }

    return {
        "request_id": request_id,
        "sent": True,
        "message": "RCA PDF emailed successfully.",
    }


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


@router.post("/{request_id}/postmortem", response_model=dict, status_code=200)
def generate_postmortem(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
    pm_service: PostMortemService = Depends(get_postmortem_service),
) -> dict:
    """Generate (or return cached) a blameless post-mortem for a completed investigation.

    On first call: invokes the LLM to generate prevention recommendations,
    assembles the full Markdown document, persists to the ``post_mortems`` table,
    and returns the structured payload.

    On subsequent calls: returns the cached version without re-invoking the LLM.

    Returns 404 if the investigation is not found or incomplete.
    """
    # Return cached version if it exists
    cached = repo.get_post_mortem(request_id)
    if cached is not None:
        return cached.model_dump(mode="json")

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation {request_id!r} not found or incomplete.",
        )

    # Pull approved_by from approval audit trail for inclusion in document
    replay = repo.get_investigation_replay(request_id)
    approved_by = replay["approval"]["approved_by"] if replay else None

    pm = pm_service.generate(result, approved_by=approved_by)
    repo.save_post_mortem(pm)

    _log.info("Post-mortem generated and cached for request_id=%s", request_id)
    return pm.model_dump(mode="json")


@router.get("/{request_id}/postmortem", response_model=dict, status_code=200)
def get_postmortem(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return a previously generated post-mortem for an investigation.

    Returns 404 if no post-mortem has been generated yet (call POST first).
    """
    cached = repo.get_post_mortem(request_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"No post-mortem found for {request_id!r}. Generate one first via POST.",
        )
    return cached.model_dump(mode="json")

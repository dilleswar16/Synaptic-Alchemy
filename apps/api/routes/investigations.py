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
import os

import litellm
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
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
from corvin.strategy.roi import build_roi_stats
from corvin.core.config_loader import get_env, load_config
from corvin.core.knowledge_loader import KnowledgeLoader
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
    service_name: str = Field(..., min_length=1, max_length=255)
    environment: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="Manual investigation", max_length=2000)


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


@router.get("/briefing/audio")
def get_briefing_audio(
    hours: int = Query(default=24, ge=1, le=168),
    repo: InvestigationRepository = Depends(get_repository),
) -> Response:
    """Stream the morning briefing narrative as MP3 audio via Azure TTS.

    Requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables.
    Returns 503 when TTS is not configured or the policy flag is disabled.
    """
    policy = load_config("policies/investigation", get_env())
    if not policy.get("voice_briefing_enabled", True):
        raise HTTPException(status_code=503, detail="Voice briefing is disabled in policy config.")

    speech_key    = os.environ.get("AZURE_SPEECH_KEY", "")
    speech_region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not speech_key or not speech_region:
        raise HTTPException(status_code=503, detail="AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not configured.")

    briefing = repo.get_briefing(hours=hours)
    narrative: str = briefing.get("narrative", "No briefing available.")
    voice_name = policy.get("voice_name", "en-GB-RyanNeural")

    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore

        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        speech_config.speech_synthesis_voice_name = voice_name

        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        result = synthesizer.speak_text_async(narrative).get()

        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {result.reason}")

        audio_bytes = result.audio_data

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="azure-cognitiveservices-speech SDK not installed. Run: pip install azure-cognitiveservices-speech",
        )

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="briefing.mp3"'},
    )

@router.get("/roi", response_model=dict)
def get_roi(
    months: int = Query(default=1, ge=1, le=12, description="Look-back window in months"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return ROI stats for the dashboard — hours saved, cost saved vs baseline MTTR."""
    from datetime import datetime, timedelta, timezone
    from corvin.strategy.roi import _parse_dt

    investigations = repo.list_investigations()
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    filtered = [
        row for row in investigations
        if (dt := _parse_dt(row.get("completed_at") or row.get("created_at"))) and dt >= cutoff
    ]
    policy = load_config("policies/investigation", get_env())
    stats = build_roi_stats(filtered, policy=policy)
    # Stamp the requested period so the frontend can label it correctly
    stats.period_months = months
    return stats.model_dump()


@router.get("/dora", response_model=dict)
def get_dora_metrics(
    days: int = Query(default=30, ge=1, le=365, description="Look-back window in days"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return DORA four-key engineering metrics computed from Corvin investigation data.

    Metrics returned:
      - deployment_frequency:   investigations per day (proxy for change frequency)
      - lead_time_minutes:      avg time from trigger to RCA complete (Corvin MTTR)
      - change_failure_rate:    % of investigations that were HIGH confidence (real incidents)
      - mttr_minutes:           mean time to resolve (avg investigation duration)
      - mttr_trend:             'improving' | 'stable' | 'degrading' vs prior period
      - total_investigations:   count in window
      - high_confidence_count:  count with confidence=high
    """
    from datetime import datetime, timedelta, timezone
    from corvin.strategy.roi import _parse_dt

    all_rows = repo.list_investigations()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    prior_cutoff = cutoff - timedelta(days=days)

    def in_window(row: dict, start, end) -> bool:
        dt = _parse_dt(row.get("completed_at") or row.get("created_at"))
        return dt is not None and start <= dt < end

    current = [r for r in all_rows if in_window(r, cutoff, now)]
    prior   = [r for r in all_rows if in_window(r, prior_cutoff, cutoff)]

    def avg_duration(rows: list[dict]) -> float:
        durations = []
        for row in rows:
            try:
                t0 = _parse_dt(row["created_at"])
                t1 = _parse_dt(row["completed_at"])
                if t0 and t1 and t1 > t0:
                    durations.append((t1 - t0).total_seconds() / 60.0)
            except (KeyError, TypeError):
                pass
        return round(sum(durations) / len(durations), 1) if durations else 0.0

    total = len(current)
    high_conf = sum(1 for r in current if str(r.get("rca_confidence", "")).lower() == "high"
                    or str(r.get("confidence", "")).lower() == "high")

    mttr_current = avg_duration(current)
    mttr_prior   = avg_duration(prior)

    if mttr_prior == 0 or mttr_current == 0:
        trend = "stable"
    elif mttr_current < mttr_prior * 0.95:
        trend = "improving"
    elif mttr_current > mttr_prior * 1.05:
        trend = "degrading"
    else:
        trend = "stable"

    # Change failure rate: fraction that needed investigation = 100% (all are real incidents in Corvin)
    # More meaningful: % that were HIGH confidence (signal vs noise)
    cfr = round(high_conf / total * 100, 1) if total > 0 else 0.0

    return {
        "period_days": days,
        "total_investigations": total,
        "high_confidence_count": high_conf,
        "deployment_frequency": round(total / days, 2),
        "lead_time_minutes": mttr_current,
        "mttr_minutes": mttr_current,
        "mttr_prior_minutes": mttr_prior,
        "mttr_trend": trend,
        "change_failure_rate_pct": cfr,
    }


@router.get("/predictive-alerts", response_model=list[dict])
def get_predictive_alerts(
    refresh: bool = Query(default=False, description="Refresh predictive detections before returning. Defaults to False to avoid slow heuristic scan on every dashboard load."),
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


@router.get("/topology/live", response_model=dict)
def get_topology_live() -> dict:
    """Return live pod state from AKS, grouped by service, in ServiceTopology format.

    Unlike /topology (which is built from past DB investigations), this endpoint
    calls the AKS API directly so it always reflects the current running state.

    Even when AKS is unreachable, the known CHAD service architecture (APIM gateway,
    fundapis, partnerapis, fundsso with correct routing) is always included as static
    nodes so the canvas is never blank.
    """
    from corvin.evidence.aks_adapter import AKSAdapter
    from corvin.investigation.topology import (
        ServiceTopology, TopologyNode, TopologyEdge,
        _inject_apim_topology,
    )

    # AKS deployment label → logical CHAD service name.
    # The `app` label in k8s is "chad-fundapis" but we call it "fundapis" everywhere.
    _AKS_NAME_MAP: dict[str, str] = {
        "chad-fundapis":    "fundapis",
        "chad-fundsso":     "fundsso",
        "chad-partnerapis": "partnerapis",
    }

    # ── Static CHAD architecture — always shown regardless of AKS reachability ──
    # Start with the three logical service nodes. Live pod data will update their
    # status and attach pod children to these same nodes (not duplicate them).
    nodes: dict[str, TopologyNode] = {
        "svc:fundapis":    TopologyNode(id="svc:fundapis",    label="fundapis",    kind="service", status="high"),
        "svc:partnerapis": TopologyNode(id="svc:partnerapis", label="partnerapis", kind="service", status="high"),
        "svc:fundsso":     TopologyNode(id="svc:fundsso",     label="fundsso",     kind="service", status="high"),
    }
    edges: dict[tuple[str, str, str | None], TopologyEdge] = {}

    # Inject APIM gateway + API route nodes (fundapis/partnerapis) + PingFederate (fundsso)
    _inject_apim_topology(nodes, edges)

    # ── Live pod data from AKS — overlay status + pod children ───────────────
    try:
        adapter = AKSAdapter()
        result = adapter.list_all_pods()
        for svc in result.get("services", []):
            raw_name = svc["name"]
            # Normalise "chad-fundapis" → "fundapis" so pods attach to the right node
            logical_name = _AKS_NAME_MAP.get(raw_name, raw_name)
            svc_id = f"svc:{logical_name}"
            live_status = svc.get("status", "high")
            # Update or create the service node with the live status
            nodes[svc_id] = TopologyNode(id=svc_id, label=logical_name, kind="service", status=live_status)
            for pod in svc.get("pods", []):
                pod_name = pod.get("name", "")
                pod_id = f"pod:{pod_name}"
                phase = pod.get("phase") or "Unknown"
                containers = pod.get("containers", [])
                any_bad = any(not c.get("ready", True) for c in containers)
                pod_status = "hot" if (phase not in ("Running", "Succeeded") or any_bad) else "high"
                nodes[pod_id] = TopologyNode(id=pod_id, label=pod_name, kind="pod", status=pod_status)
                edges[(svc_id, pod_id, "runs")] = TopologyEdge(source=svc_id, target=pod_id, label="runs")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("topology/live AKS call failed (static nodes still returned): %s", exc)

    return ServiceTopology(nodes=list(nodes.values()), edges=list(edges.values())).model_dump()


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


@router.post("/{request_id}/update-runbook", response_model=dict)
def update_runbook(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Generate a runbook resolution step from a completed investigation and append it.

    Only permitted when approval_status is 'executed'. Returns the path written
    and the markdown content so the UI can show a diff preview.
    """
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    if result.request.approval_status != ApprovalStatus.EXECUTED:
        raise HTTPException(status_code=400, detail="Runbook update is only permitted after execution (approval_status=executed).")

    policy = load_config("policies/investigation", get_env())
    llm_cfg = load_config("models/llm", get_env())

    prompt = (
        f"You are a senior SRE. A fix was successfully executed for the following incident.\n\n"
        f"Service: {result.request.service_name} ({result.request.environment})\n"
        f"Root Cause: {result.rca.root_cause}\n"
        f"Fix Applied: {result.fix_strategy.actions[0].title if result.fix_strategy.actions else 'Manual fix'}\n"
        f"Summary: {result.fix_strategy.summary}\n\n"
        f"Write a concise Markdown runbook step (heading + bullet steps) that captures what was done and when to apply it. "
        f"Be specific. Max 200 words. Start with ## Resolution: <short title>."
    )

    try:
        response = litellm.completion(
            model=llm_cfg.get("model", "azure/responses/gpt-5.1"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        step_md = response.choices[0].message.content.strip()
    except Exception as exc:
        _log.warning("LLM runbook generation failed: %s", exc)
        step_md = (
            f"## Resolution: {result.fix_strategy.summary}\n\n"
            f"- Root cause: {result.rca.root_cause}\n"
            f"- Fix applied: {result.fix_strategy.actions[0].title if result.fix_strategy.actions else 'Manual'}\n"
            f"- Investigation: `{request_id}`\n"
        )

    loader = KnowledgeLoader()
    runbook_path = loader.append_runbook_step(result.request.service_name, step_md)
    loader.append_learning(request_id, step_md)

    return {
        "path": str(runbook_path),
        "service_name": result.request.service_name,
        "content": step_md,
        "message": f"Runbook updated for {result.request.service_name}.",
    }


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
    try:
        repo.save_post_mortem(pm)
    except Exception:
        # Concurrent request already inserted — return whichever was saved first
        cached = repo.get_post_mortem(request_id)
        if cached is not None:
            return cached.model_dump(mode="json")
        raise

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


class ChatRequest(BaseModel):
    messages: list[dict]

class SyncResponse(BaseModel):
    ticket_id: str
    url: str | None = None
    message: str

@router.post("/{request_id}/sync/azure-boards", response_model=SyncResponse)
def sync_azure_boards(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> SyncResponse:
    """Export the investigation result as a new Work Item in Azure Boards (ADO)."""
    from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter
    
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    config = load_config("integrations/azure_devops", get_env())
    adapter = AzureDevOpsAdapter(config)
    
    work_item_id = adapter.create_incident(result)
    if work_item_id is None:
        raise HTTPException(
            status_code=502, 
            detail="Failed to create Azure Boards work item. Check adapter configuration."
        )

    # Build direct link to the work item if org/project are known
    org = config.get("org_name")
    proj = config.get("project_name")
    url = f"https://dev.azure.com/{org}/{proj}/_workitems/edit/{work_item_id}" if org and proj else None

    return SyncResponse(
        ticket_id=work_item_id,
        url=url,
        message=f"Created Azure Boards work item {work_item_id}."
    )

@router.post("/{request_id}/sync/servicenow", response_model=SyncResponse)
def sync_servicenow(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> SyncResponse:
    """Mocked export to ServiceNow INC (for hackathon demo purposes)."""
    import time
    # Verify investigation exists
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    mock_inc = f"INC{int(time.time()) % 1000000:06d}"
    return SyncResponse(
        ticket_id=mock_inc,
        message=f"Created ServiceNow Incident {mock_inc} and assigned to SRE team."
    )

class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

@router.get("/{request_id}/chat/history")
def get_chat_history(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> list[ChatMessageOut]:
    """Return the persisted chat message history for an investigation."""
    from corvin.storage.models import ChatMessageRow
    from corvin.storage.db import get_session
    from sqlalchemy import select

    # Verify investigation exists
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    with get_session() as session:
        rows = session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.request_id == request_id)
            .order_by(ChatMessageRow.created_at)
        ).scalars().all()
        return [
            ChatMessageOut(
                id=r.id,
                role=r.role,
                content=r.content,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]

@router.post("/{request_id}/chat")
def chat_with_investigation(
    request_id: str,
    body: ChatRequest,
    repo: InvestigationRepository = Depends(get_repository),
) -> StreamingResponse:
    """Stream a chat conversation with the Copilot using the investigation context.
    
    The last user message and the assembled assistant reply are both persisted
    to the ``chat_messages`` table so the conversation history survives page
    refreshes and can be replayed on the frontend.
    """
    from corvin.strategy.chat_service import ChatService
    from corvin.storage.models import ChatMessageRow
    from corvin.storage.db import get_session

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    # Identify and persist the latest user message immediately
    user_messages = [m for m in body.messages if m.get("role") == "user"]
    if user_messages:
        last_user_msg = user_messages[-1]
        with get_session() as session:
            session.add(ChatMessageRow(
                request_id=request_id,
                role="user",
                content=last_user_msg.get("content", ""),
            ))
            session.commit()

    svc = ChatService()

    def _stream_and_persist():
        """Yield SSE chunks and persist the assembled assistant reply at the end."""
        assistant_chunks: list[str] = []
        for chunk in svc.stream_chat(result, body.messages):
            yield chunk
            # Collect text chunks to assemble full assistant reply
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    import json as _json
                    data = _json.loads(chunk[6:])
                    if data.get("type") == "text" and data.get("text"):
                        assistant_chunks.append(data["text"])
                except Exception:
                    pass

        # Persist assembled assistant reply
        full_reply = "".join(assistant_chunks)
        if full_reply.strip():
            try:
                with get_session() as session:
                    session.add(ChatMessageRow(
                        request_id=request_id,
                        role="assistant",
                        content=full_reply,
                    ))
                    session.commit()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Failed to persist assistant reply: %s", exc)

    return StreamingResponse(
        _stream_and_persist(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )

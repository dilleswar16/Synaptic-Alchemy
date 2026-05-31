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
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, InvestigationResult, TriggerSource
from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter
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
from corvin.triggers.prediction_penalty import penalize_prediction

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


def _sync_ado_acknowledged_close(
    request_id: str,
    repo: InvestigationRepository,
) -> tuple[bool, str]:
    """Best-effort: close linked ADO ticket and append an acknowledgement comment."""
    work_item_id = repo.get_ado_work_item_id(request_id)
    if not work_item_id:
        return True, "No Azure Boards ticket linked for this investigation."

    config = load_config("integrations/azure_devops", get_env())
    adapter = AzureDevOpsAdapter(config)

    comment = (
        "Corvin update: No action needed. "
        "Operator acknowledged this investigation as informational and closed the ticket. "
        f"Investigation ID: {request_id}."
    )

    state_ok = adapter.update_work_item_state(work_item_id, "Closed")
    comment_ok = adapter.add_comment(work_item_id, comment)

    if state_ok and comment_ok:
        return True, f"Azure Boards #{work_item_id} updated (state=Closed + acknowledgement comment)."
    if state_ok and not comment_ok:
        return False, f"Azure Boards #{work_item_id} state was closed, but comment update failed."
    if not state_ok and comment_ok:
        return False, f"Azure Boards #{work_item_id} comment posted, but state update to Closed failed."
    return False, f"Azure Boards #{work_item_id} update failed (state and comment)."


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
    acknowledged: int
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

    # Penalize predictive analysis: record miss/insufficient prediction for learning.
    try:
        penalize_prediction(result)
    except Exception as exc:
        _log.warning("Prediction penalty recording failed (non-fatal): %s", exc)

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

    # Penalize predictive analysis: record miss/insufficient prediction for learning.
    try:
        penalize_prediction(result)
    except Exception as exc:
        _log.warning("Prediction penalty recording failed (non-fatal): %s", exc)

    return InvestigationAccepted(
        request_id=result.request_id,
        status="completed",
        message="Predictive investigation completed and persisted.",
    )


# ─── Predictive Learnings / Penalties ─────────────────────────────────────────


@router.get("/predictive-learnings")
def list_predictive_learnings(
    service: Optional[str] = Query(None, description="Filter by service name"),
    limit: int = Query(20, ge=1, le=100),
):
    """Return recorded predictive penalties (missed or insufficient predictions)."""
    from corvin.triggers.prediction_penalty import load_penalties_for_service
    from corvin.storage.db import get_session as _get_db_session
    from corvin.storage.models import PredictivePenaltyRow

    if service:
        return load_penalties_for_service(service, limit=limit)

    with _get_db_session() as db:
        rows = (
            db.query(PredictivePenaltyRow)
            .order_by(PredictivePenaltyRow.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "service_name": r.service_name,
                "environment": r.environment,
                "alert_type": r.alert_type,
                "penalty_type": r.penalty_type,
                "investigation_id": r.investigation_id,
                "predictive_alert_id": r.predictive_alert_id,
                "pattern_description": r.pattern_description,
                "root_cause_fingerprint": r.root_cause_fingerprint,
                "suggested_threshold_adjustment": r.suggested_threshold_adjustment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


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

    Service nodes, the k8s label→name mapping, and APIM routing edges are all
    driven by ApplicationServiceRow records registered through the Applications UI.
    No service details are hardcoded — add/remove services via Applications → Services.
    """
    from corvin.evidence.aks_adapter import AKSAdapter
    from corvin.evidence.container_logs_adapter import ContainerLogsAdapter
    from corvin.investigation.topology import (
        ServiceTopology, TopologyNode, TopologyEdge,
        build_pod_topology_node,
        _resource_summary, _resource_summary_by_pod,
    )
    from corvin.storage.db import get_session as _get_db_session
    from corvin.storage.models import ApplicationServiceRow as _SvcRow

    nodes: dict[str, TopologyNode] = {}
    edges: dict[tuple[str, str, str | None], TopologyEdge] = {}
    # k8s deployment label (e.g. "chad-fundapis") → logical service name ("fundapis")
    aks_name_map: dict[str, str] = {}

    # ── Build initial service nodes + routing edges from DB ──────────────────
    with _get_db_session() as _db:
        svc_rows = _db.query(_SvcRow).all()

    for svc in svc_rows:
        svc_id = f"svc:{svc.service_name}"
        if svc.k8s_app_label:
            aks_name_map[svc.k8s_app_label] = svc.service_name
        nodes[svc_id] = TopologyNode(
            id=svc_id, label=svc.service_name, kind="service", status="unknown",
        )
        meta: dict = svc.metadata_json or {}
        # APIM routing: inject gateway → api node → service edges
        if meta.get("apim_routes_through_gateway"):
            api_id = meta.get("apim_api_id") or svc.service_name
            gateway_id = "gateway:apim"
            api_node_id = f"api:{api_id}"
            if gateway_id not in nodes:
                nodes[gateway_id] = TopologyNode(
                    id=gateway_id, label="APIM Gateway", kind="gateway", status="supporting",
                )
            nodes.setdefault(
                api_node_id,
                TopologyNode(id=api_node_id, label=api_id, kind="api", status="observed"),
            )
            edges[(gateway_id, api_node_id, "routes")] = TopologyEdge(
                source=gateway_id, target=api_node_id, label="routes",
            )
            edges[(api_node_id, svc_id, "routes")] = TopologyEdge(
                source=api_node_id, target=svc_id, label="routes",
            )
        # SSO / direct-to-IdP dependency
        if meta.get("is_sso_direct"):
            pf_id = "backend:pingfederate"
            nodes.setdefault(
                pf_id,
                TopologyNode(id=pf_id, label="PingFederate SSO", kind="backend", status="supporting"),
            )
            edges[(svc_id, pf_id, "depends-on")] = TopologyEdge(
                source=svc_id, target=pf_id, label="depends-on",
            )

    # If no services have been registered yet, return an empty topology
    if not nodes:
        return ServiceTopology(nodes=[], edges=[]).model_dump()

    # ── Live pod data from AKS — overlay status + pod children ───────────────
    try:
        adapter = AKSAdapter()
        logs_adapter = ContainerLogsAdapter()
        result = adapter.list_all_pods()
        for svc in result.get("services", []):
            raw_name = svc["name"]
            # Normalise k8s label → logical name using the DB-driven map
            logical_name = aks_name_map.get(raw_name, raw_name)
            svc_id = f"svc:{logical_name}"
            live_status = svc.get("status", "high")
            try:
                metric_rows = logs_adapter.get_resource_metrics(logical_name or raw_name)
            except Exception:
                metric_rows = []
            service_resource = _resource_summary(metric_rows)
            pod_resource_map = _resource_summary_by_pod(metric_rows)
            # Update or create the service node with live status + resource metrics
            nodes[svc_id] = TopologyNode(
                id=svc_id,
                label=logical_name or raw_name,
                kind="service",
                status=live_status,
                cpu_mcores=service_resource["cpu_mcores"],
                cpu_request_mcores=service_resource["cpu_request_mcores"],
                cpu_limit_mcores=service_resource["cpu_limit_mcores"],
                cpu_utilization_pct=service_resource["cpu_utilization_pct"],
                memory_mib=service_resource["memory_mib"],
                memory_request_mib=service_resource["memory_request_mib"],
                memory_limit_mib=service_resource["memory_limit_mib"],
                memory_utilization_pct=service_resource["memory_utilization_pct"],
            )
            for pod in svc.get("pods", []):
                if not isinstance(pod, dict):
                    continue
                pod_copy = dict(pod)
                pod_name = str(pod_copy.get("name") or pod_copy.get("pod") or "").strip()
                pod_resource = pod_resource_map.get(pod_name, {})
                for key, value in pod_resource.items():
                    if value is not None:
                        pod_copy[key] = value
                pod_node = build_pod_topology_node(pod_copy)
                nodes[pod_node.id] = pod_node
                edges[(svc_id, pod_node.id, "runs")] = TopologyEdge(
                    source=svc_id, target=pod_node.id, label="runs",
                )
    except Exception as exc:
        _log.warning("topology/live AKS call failed (DB-seeded nodes still returned): %s", exc)

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


@router.post("/{request_id}/acknowledge", response_model=ApprovalResponse, status_code=200)
def acknowledge_investigation(
    request_id: str,
    approved_by: Optional[str] = Query(default=None, description="SRE name/email for audit log"),
    repo: InvestigationRepository = Depends(get_repository),
) -> ApprovalResponse:
    """Acknowledge an informational investigation and close linked ADO ticket.

    Transitions approval_status: pending -> acknowledged.
    Best-effort sync: when an Azure Boards work item is linked, sets state to
    Closed and adds an acknowledgement comment.
    """
    row = repo.get_approval_status(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    if row != ApprovalStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Investigation {request_id!r} is in state {row!r}; "
                f"only investigations in 'pending' can be acknowledged."
            ),
        )

    repo.update_approval_status(request_id, ApprovalStatus.ACKNOWLEDGED, approved_by=approved_by)

    ado_ok, ado_msg = _sync_ado_acknowledged_close(request_id, repo)
    message = (
        "Investigation acknowledged and closed as informational. "
        f"{ado_msg}"
    )
    if not ado_ok:
        _log.warning("Acknowledge completed but ADO sync had issues for %s: %s", request_id, ado_msg)

    return ApprovalResponse(
        request_id=request_id,
        approval_status=ApprovalStatus.ACKNOWLEDGED.value,
        message=message,
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
            "logs": o.logs,
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


@router.post("/{request_id}/execute/{action_index}", response_model=dict, status_code=200)
def execute_single_action(
    request_id: str,
    action_index: int,
    repo: InvestigationRepository = Depends(get_repository),
    svc: ExecutionService = Depends(get_execution_service),
) -> dict:
    """Execute a single fix action by its index (0-based).

    Gate rules:
      - Returns 404 if the investigation does not exist.
      - Returns 409 if approval_status is not 'approved' or 'executed'.
      - Returns 400 if action_index is out of range.

    On first action execution, transitions approval_status → executed.
    """
    approval_status = repo.get_approval_status(request_id)
    if approval_status is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    if approval_status not in (ApprovalStatus.APPROVED.value, ApprovalStatus.EXECUTED.value):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Investigation {request_id!r} cannot be executed: "
                f"approval_status is '{approval_status}', expected 'approved' or 'executed'."
            ),
        )

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation {request_id!r} result not found.",
        )

    try:
        outcome = svc.execute_single(result, action_index, approval_status=approval_status)
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Transition to EXECUTED on first action execution
    if approval_status == ApprovalStatus.APPROVED.value:
        repo.update_approval_status(request_id, ApprovalStatus.EXECUTED)

    return {
        "request_id": request_id,
        "action_index": action_index,
        "action_type": outcome.action_type.value,
        "title": outcome.title,
        "success": outcome.success,
        "detail": outcome.detail,
        "logs": outcome.logs,
    }


@router.get("/{request_id}/execute/stream")
def stream_execute_all(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
    svc: ExecutionService = Depends(get_execution_service),
) -> StreamingResponse:
    """Execute all fix actions step-by-step and stream progress as SSE.

    Each action emits events:
      - ``action_start``: action is about to execute
      - ``action_complete``: action finished with outcome + logs
      - ``pod_logs``: live container logs fetched after execution
      - ``done``: all actions completed

    Gate: returns 404/409 same as single-action endpoint.
    """
    import json as _json
    import time as _time

    approval_status = repo.get_approval_status(request_id)
    if approval_status is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")
    if approval_status not in (ApprovalStatus.APPROVED.value, ApprovalStatus.EXECUTED.value):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot execute: approval_status is '{approval_status}'.",
        )

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation result not found.")

    def _generate():
        from corvin.evidence.aks_adapter import AKSAdapter

        aks = AKSAdapter()
        service_name = result.request.service_name
        actions = result.fix_strategy.actions
        current_status = approval_status
        all_succeeded = True

        for i, action in enumerate(actions):
            # Emit start event
            yield f"data: {_json.dumps({'event': 'action_start', 'action_index': i, 'title': action.title, 'action_type': action.action_type.value, 'total': len(actions)})}\n\n"

            try:
                outcome = svc.execute_single(result, i, approval_status=current_status)
            except (PermissionError, IndexError) as exc:
                yield f"data: {_json.dumps({'event': 'action_complete', 'action_index': i, 'title': action.title, 'success': False, 'detail': str(exc), 'logs': []})}\n\n"
                all_succeeded = False
                continue

            # Transition status after first action
            if current_status == ApprovalStatus.APPROVED.value:
                repo.update_approval_status(request_id, ApprovalStatus.EXECUTED)
                current_status = ApprovalStatus.EXECUTED.value

            if not outcome.success:
                all_succeeded = False

            yield f"data: {_json.dumps({'event': 'action_complete', 'action_index': i, 'title': outcome.title, 'action_type': outcome.action_type.value, 'success': outcome.success, 'detail': outcome.detail, 'logs': outcome.logs})}\n\n"

            # Fetch live pod logs after automatable actions
            if outcome.action_type.value != "manual":
                # Use action-level target if available, else fall back to investigation service
                log_svc = action.target_service or service_name
                log_ns = action.target_namespace or None
                _time.sleep(2)  # Brief wait for pods to start producing logs
                try:
                    pod_logs = aks.get_pod_logs(log_svc, namespace=log_ns, tail_lines=30, since_seconds=10)
                    yield f"data: {_json.dumps({'event': 'pod_logs', 'action_index': i, 'pod_logs': pod_logs})}\n\n"
                except Exception as exc:
                    _log.warning("Failed to fetch pod logs after action %d: %s", i, exc)
                    yield f"data: {_json.dumps({'event': 'pod_logs', 'action_index': i, 'pod_logs': [], 'error': str(exc)})}\n\n"

        yield f"data: {_json.dumps({'event': 'done', 'all_succeeded': all_succeeded, 'total': len(actions)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{request_id}/logs")
def get_service_logs(
    request_id: str,
    tail_lines: int = Query(default=60, ge=1, le=500),
    since_seconds: int = Query(default=30, ge=5, le=600),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Fetch recent pod logs for the service associated with this investigation."""
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")

    from corvin.evidence.aks_adapter import AKSAdapter
    aks = AKSAdapter()
    pod_logs = aks.get_pod_logs(
        result.request.service_name,
        tail_lines=tail_lines,
        since_seconds=since_seconds,
    )
    return {
        "request_id": request_id,
        "service_name": result.request.service_name,
        "pod_logs": pod_logs,
    }


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
    """Export investigation to ServiceNow. Requires a configured ServiceNow outbound connector."""
    import httpx
    from corvin.storage.database import get_session
    from corvin.storage.models import OutboundConnectorRow, InvestigationRequestRow

    # Verify investigation exists
    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    # Look up ServiceNow connector config
    with get_session() as session:
        inv = session.query(InvestigationRequestRow).filter_by(id=request_id).first()
        app_id = inv.application_id if inv else None

        connector = session.query(OutboundConnectorRow).filter(
            OutboundConnectorRow.connector_type == "servicenow",
            OutboundConnectorRow.enabled == True,
        ).first()

    if connector is None:
        raise HTTPException(
            status_code=422,
            detail="ServiceNow connector not configured. Add an outbound connector with type='servicenow' in Settings.",
        )

    config = connector.config_json or {}
    instance_url = config.get("instance_url", "").rstrip("/")
    username = config.get("username")
    password = config.get("password")

    if not instance_url or not username or not password:
        raise HTTPException(
            status_code=422,
            detail="ServiceNow connector misconfigured: instance_url, username, and password are required.",
        )

    # Build incident payload from investigation
    short_desc = f"[Corvin] {result.rca.root_cause}" if result.rca else f"[Corvin] Investigation {request_id}"
    description_parts = []
    if result.rca:
        description_parts.append(f"Root Cause: {result.rca.root_cause}")
        if result.rca.contributing_factors:
            description_parts.append(f"Contributing Factors: {', '.join(result.rca.contributing_factors)}")
    if result.fix_strategy:
        description_parts.append(f"Fix Strategy: {result.fix_strategy.summary}")

    payload = {
        "short_description": short_desc[:160],
        "description": "\n".join(description_parts)[:4000],
        "urgency": "2",
        "impact": "2",
        "category": "Software",
        "caller_id": config.get("caller_id", ""),
        "assignment_group": config.get("assignment_group", ""),
    }

    try:
        resp = httpx.post(
            f"{instance_url}/api/now/table/incident",
            json=payload,
            auth=(username, password),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json().get("result", {})
        inc_number = data.get("number", "UNKNOWN")
        inc_url = f"{instance_url}/nav_to.do?uri=incident.do?sys_id={data.get('sys_id', '')}"
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"ServiceNow API error: {e.response.status_code} {e.response.text[:200]}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"ServiceNow connection failed: {str(e)[:200]}")

    return SyncResponse(
        ticket_id=inc_number,
        url=inc_url,
        message=f"Created ServiceNow Incident {inc_number} and assigned to SRE team."
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


# ══════════════════════════════════════════════════════════════════════════════
# V5.0 — Agentic AI Features
# ══════════════════════════════════════════════════════════════════════════════


# ── F4: Causal Reasoning Graph ────────────────────────────────────────────────

@router.get("/{request_id}/causal-chain")
def get_causal_chain(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Generate a directed causal chain from the investigation's RCA.

    Returns a DAG with nodes (trigger → failure → cascade → impact) and edges,
    suitable for rendering as a Mermaid flowchart on the frontend.
    """
    from corvin.strategy.causal_chain import CausalChainGenerator

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    generator = CausalChainGenerator()
    return generator.generate(result)


# ── F7: Incident Communication Drafts ────────────────────────────────────────

class CommsDraftRequest(BaseModel):
    audience: str = Field(default="internal", description="One of: executive, internal, public")


@router.post("/{request_id}/comms-draft")
def generate_comms_draft(
    request_id: str,
    body: CommsDraftRequest = Body(default=CommsDraftRequest()),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Generate an audience-appropriate incident communication draft.

    Supports three audience levels:
    - executive: C-suite business impact summary
    - internal: Engineering status update
    - public: Customer-facing status page update
    """
    from corvin.strategy.comms_draft import CommsDraftGenerator

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    if body.audience not in ("executive", "internal", "public"):
        raise HTTPException(status_code=400, detail=f"Invalid audience: {body.audience}. Must be executive, internal, or public.")

    generator = CommsDraftGenerator()
    return generator.generate(result, body.audience)


@router.get("/{request_id}/comms-draft/all")
def generate_all_comms_drafts(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> list[dict]:
    """Generate communication drafts for all audience levels at once."""
    from corvin.strategy.comms_draft import CommsDraftGenerator

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    generator = CommsDraftGenerator()
    return generator.generate_all(result)


# ── F6: Natural Language → KQL ────────────────────────────────────────────────

class NLToKQLRequest(BaseModel):
    question: str = Field(..., description="Natural language question to translate to KQL")
    time_range: str | None = Field(default=None, description="Optional time range (e.g. 'last 2 hours')")


@router.post("/kql/translate")
def translate_nl_to_kql(body: NLToKQLRequest) -> dict:
    """Translate a natural language question into a KQL query.

    Includes safety guardrails that block destructive management commands.
    Returns the KQL query, safety status, and original question.
    """
    from corvin.strategy.nl_to_kql import NLToKQLService

    service = NLToKQLService()
    return service.translate(body.question, body.time_range)


# ── F9: Multi-Agent Investigation ─────────────────────────────────────────────

class MultiAgentRequest(BaseModel):
    service_name: str
    environment: str = "prod"
    description: str
    priority: str = "P2"


@router.post("/multi-agent", status_code=202)
def start_multi_agent_investigation(
    body: MultiAgentRequest,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Launch a multi-agent investigation using the SelectorGroupChat pattern.

    Specialist agents (EvidenceCollector, RCAAnalyst, FixStrategist) are
    dynamically coordinated by an LLM-based orchestrator.
    Returns the investigation result + agent trace for observability.
    """
    from corvin.strategy.multi_agent import MultiAgentOrchestrator

    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=body.service_name,
        environment=body.environment,
        description=body.description,
        raw_payload={"priority": body.priority, "mode": "multi_agent"},
    )

    orchestrator = MultiAgentOrchestrator()
    result, trace = orchestrator.run(request)
    repo.save_investigation_result(result)

    return {
        "request_id": result.request_id,
        "status": "completed",
        "mode": "multi_agent",
        "trace": trace.to_dict(),
        "confidence": result.rca.confidence.value,
        "root_cause": result.rca.root_cause,
    }


@router.get("/{request_id}/multi-agent/trace")
def get_multi_agent_trace(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Re-run multi-agent orchestration and return the trace (for replay/debugging)."""
    from corvin.strategy.multi_agent import MultiAgentOrchestrator

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    orchestrator = MultiAgentOrchestrator()
    _, trace = orchestrator.run(result.request)
    return trace.to_dict()


# ── F10: Chaos Experiment Generator ───────────────────────────────────────────

@router.get("/{request_id}/chaos-experiments")
def get_chaos_experiments(
    request_id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Generate chaos experiment recommendations based on investigation findings.

    Analyzes the RCA and produces targeted chaos experiments that would
    validate the system's resilience against similar failures.
    """
    from corvin.strategy.chaos_engine import ChaosExperimentGenerator

    result = repo.get_investigation_result(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {request_id!r} not found.")

    generator = ChaosExperimentGenerator()
    plan = generator.generate(result)
    return plan.to_dict()


# ── F11: IDE Integration Context ─────────────────────────────────────────────

@router.get("/ide/context/{service_name}")
def get_ide_context(
    service_name: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Get IDE-optimized context for a service.

    Returns active investigations, recent incidents, deployment safety signals,
    and relevant knowledge snippets — designed for VS Code extension consumption.
    """
    from corvin.strategy.ide_integration import IDEIntegrationService

    service = IDEIntegrationService(repository=repo)
    context = service.get_context(service_name, repo=repo)
    return context.to_dict()


class IDEFixSuggestionRequest(BaseModel):
    service_name: str
    file_path: str
    error_context: str


@router.post("/ide/fix-suggestion")
def get_ide_fix_suggestion(
    body: IDEFixSuggestionRequest,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Get a context-aware fix suggestion for a specific file/error.

    Cross-references with past investigations to provide informed suggestions
    optimized for inline display in VS Code.
    """
    from corvin.strategy.ide_integration import IDEIntegrationService

    service = IDEIntegrationService(repository=repo)
    suggestion = service.get_fix_suggestion(
        body.service_name, body.file_path, body.error_context, repo=repo
    )
    return suggestion.to_dict()


@router.get("/ide/deploy-safety/{service_name}")
def get_deploy_safety(
    service_name: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Pre-deployment safety check for CI/CD integration.

    Returns whether it's safe to deploy to the given service based on
    active incidents and recent failure patterns.
    """
    from corvin.strategy.ide_integration import IDEIntegrationService

    service = IDEIntegrationService(repository=repo)
    signal = service.get_deploy_safety(service_name, repo=repo)
    return signal.to_dict()


# ── F12: Voice Incident Reporter ─────────────────────────────────────────────

@router.post("/voice/report")
async def voice_incident_report(
    audio: UploadFile = File(...),
) -> dict:
    """Process voice audio into a structured incident report.

    Accepts audio file upload, transcribes via Azure Speech STT,
    then extracts structured incident fields using LLM.

    Content-Type: multipart/form-data with 'audio' file field.
    """
    from corvin.strategy.voice_incident import VoiceIncidentService

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    content_type = audio.content_type or "audio/wav"
    supported = {"audio/wav", "audio/ogg", "audio/webm", "audio/mpeg"}
    if content_type not in supported:
        raise HTTPException(status_code=415, detail=f"Unsupported audio format: {content_type}. Supported: {sorted(supported)}")

    service = VoiceIncidentService()
    report = service.process_audio(audio_bytes, content_type=content_type)
    return report.to_dict()


@router.post("/voice/transcribe-and-report")
async def voice_transcribe_and_report(
    audio: bytes = Body(..., media_type="application/octet-stream"),
) -> dict:
    """Full voice pipeline: audio bytes → transcription → structured incident.

    Send raw audio bytes in the request body.
    Returns transcription + extracted incident fields.
    """
    from corvin.strategy.voice_incident import VoiceIncidentService

    service = VoiceIncidentService()
    report = service.process_audio(audio, content_type="audio/wav")
    return report.to_dict()

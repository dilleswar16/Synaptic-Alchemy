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

import json
import logging
import os
import subprocess

import litellm
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List

# ── UUID path-converter ───────────────────────────────────────────────────────
# Register a custom Starlette path converter so /{request_id:investigation_id}
# only matches UUID-formatted strings.  This prevents literal-path routes like
# /heatmap and /similarity-network from being swallowed by the catch-all
# /{request_id} route, regardless of their registration order in the file.
from starlette.convertors import Convertor, CONVERTOR_TYPES

class _InvestigationIdConvertor(Convertor):
    regex = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value

CONVERTOR_TYPES["investigation_id"] = _InvestigationIdConvertor()

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, InvestigationResult, TriggerSource
from corvin.delivery.azure_devops_adapter import AzureDevOpsAdapter
from corvin.delivery.rca_notification import send_rca_email_if_enabled, resolve_ado_boards_config_for_service
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


def _kubectl_live_pod_names(namespace: str) -> set[str]:
    """Best-effort live pod names from kubectl for selected namespace."""
    ns = str(namespace or "").strip()
    if not ns:
        return set()
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", ns, "-o", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0 or not result.stdout:
            return set()
        payload = json.loads(result.stdout)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        names = {
            str(item.get("metadata", {}).get("name") or "").strip()
            for item in items
            if isinstance(item, dict)
        }
        return {name for name in names if name}
    except Exception:
        return set()


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

    result = repo.get_investigation_result(request_id)
    if result is None:
        return False, f"Investigation {request_id!r} not found while syncing Azure Boards update."

    config = resolve_ado_boards_config_for_service(result.request.service_name)
    if not config:
        return False, "Azure Boards connector is not configured for this service."
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
    environment: str = Query(..., description="Target environment (e.g. production, staging, dev)"),
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
    environment: str = Query(..., description="Target environment (e.g. production, staging, dev)"),
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
    application_id: str | None = Query(default=None, description="Optional application id to scope topology"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    service_names: list[str] | None = None
    if hasattr(repo, "list_application_service_names"):
        try:
            service_names = repo.list_application_service_names(application_id)
        except TypeError:
            service_names = repo.list_application_service_names(application_id) if application_id else None
    topology = build_service_topology(repo.list_recent_results(limit=30, service_names=service_names))
    return topology.model_dump()


@router.get("/topology/live", response_model=dict)
def get_topology_live(
    application_id: str | None = Query(default=None, description="Optional application id to scope topology"),
    clusters: str | None = Query(default=None, description="Optional comma-separated cluster names to include"),
    namespaces: str | None = Query(default=None, description="Optional comma-separated namespaces to include"),
) -> dict:
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
    from corvin.storage.models import ApplicationRow as _AppRow, ApplicationServiceRow as _SvcRow, LogSourceRow as _LogSourceRow

    nodes: dict[str, TopologyNode] = {}
    edges: dict[tuple[str, str, str | None], TopologyEdge] = {}
    # k8s deployment label (e.g. "payments-api-deployment") → logical service name ("payments-api")
    aks_name_map: dict[str, str] = {}
    allowed_service_ids: set[str] = set()
    selected_clusters = [v.strip() for v in (clusters or "").split(",") if v.strip()]
    selected_namespaces = [v.strip() for v in (namespaces or "").split(",") if v.strip()]
    available_clusters: set[str] = set()
    available_namespaces: set[str] = set()
    cluster_namespaces: dict[str, set[str]] = {}
    namespace_status: dict[str, dict[str, int | str]] = {}

    def _add_cluster_ns(cluster_name: str | None, ns_name: str | None) -> None:
        cluster = str(cluster_name or "").strip()
        ns = str(ns_name or "").strip()
        if not cluster or not ns:
            return
        bucket = cluster_namespaces.setdefault(cluster, set())
        bucket.add(ns)

    metrics_source_ok = False
    pod_source_ok = False
    filtered_service_count = 0

    # ── Build initial service nodes + routing edges from DB ──────────────────
    with _get_db_session() as _db:
        if application_id:
            app_row = _db.get(_AppRow, application_id)
            if app_row is None:
                raise HTTPException(status_code=404, detail=f"Application {application_id!r} not found")
            svc_rows = _db.query(_SvcRow).filter(_SvcRow.application_id == application_id).all()
            log_source_rows = _db.query(_LogSourceRow).filter(_LogSourceRow.application_id == application_id).all()
        else:
            svc_rows = _db.query(_SvcRow).all()
            log_source_rows = _db.query(_LogSourceRow).all()

    for svc in svc_rows:
        if svc.namespace:
            available_namespaces.add(str(svc.namespace))

    for row in log_source_rows:
        cfg = row.config_json or {}
        if row.source_type == "aks":
            if isinstance(cfg.get("clusters"), list):
                for cluster in cfg.get("clusters", []):
                    cluster_name = None
                    if isinstance(cluster, dict) and cluster.get("cluster_name"):
                        cluster_name = str(cluster.get("cluster_name"))
                        available_clusters.add(cluster_name)
                    cluster_ns = cluster.get("namespaces") if isinstance(cluster, dict) else None
                    if isinstance(cluster_ns, list):
                        for ns in cluster_ns:
                            if str(ns).strip():
                                ns_name = str(ns).strip()
                                available_namespaces.add(ns_name)
                                _add_cluster_ns(cluster_name if isinstance(cluster, dict) else None, ns_name)
            if cfg.get("cluster_name"):
                cluster_name = str(cfg.get("cluster_name"))
                available_clusters.add(cluster_name)
            if isinstance(cfg.get("namespaces"), list):
                for ns in cfg.get("namespaces", []):
                    if str(ns).strip():
                        ns_name = str(ns).strip()
                        available_namespaces.add(ns_name)
                        _add_cluster_ns(cluster_name if cfg.get("cluster_name") else None, ns_name)
            elif cfg.get("default_namespace"):
                ns_name = str(cfg.get("default_namespace"))
                available_namespaces.add(ns_name)
                _add_cluster_ns(cluster_name if cfg.get("cluster_name") else None, ns_name)
        if row.source_type == "azure_monitor" and str(cfg.get("connector_role") or "") == "container_insights":
            if cfg.get("cluster_name"):
                cluster_name = str(cfg.get("cluster_name"))
                available_clusters.add(cluster_name)
            if isinstance(cfg.get("namespaces"), list):
                for ns in cfg.get("namespaces", []):
                    if str(ns).strip():
                        ns_name = str(ns).strip()
                        available_namespaces.add(ns_name)
                        _add_cluster_ns(cluster_name if cfg.get("cluster_name") else None, ns_name)
            elif cfg.get("default_namespace"):
                ns_name = str(cfg.get("default_namespace"))
                available_namespaces.add(ns_name)
                _add_cluster_ns(cluster_name if cfg.get("cluster_name") else None, ns_name)

    # Default to one concrete cluster + namespace on first load for better UX.
    if not selected_clusters and available_clusters:
        selected_clusters = [sorted(available_clusters)[0]]
    if not selected_namespaces:
        ns_candidates: set[str] = set()
        if selected_clusters:
            for c in selected_clusters:
                ns_candidates.update(cluster_namespaces.get(c, set()))
        if not ns_candidates:
            ns_candidates = set(available_namespaces)
        if ns_candidates:
            selected_namespaces = [sorted(ns_candidates)[0]]

    # Preserve user-selected namespace(s) in metadata even when discovery is partial,
    # so UI selection does not snap back to defaults.
    for selected_ns in selected_namespaces:
        if str(selected_ns).strip():
            available_namespaces.add(str(selected_ns).strip())
            for selected_cluster in selected_clusters:
                _add_cluster_ns(selected_cluster, str(selected_ns).strip())

    visible_svc_rows = svc_rows
    if selected_namespaces:
        selected_ns_set = {ns.lower() for ns in selected_namespaces}
        visible_svc_rows = [
            svc for svc in svc_rows
            if str(svc.namespace or "").strip().lower() in selected_ns_set
        ]

    effective_available_namespaces = set(available_namespaces)
    if selected_clusters:
        narrowed_namespaces: set[str] = set()
        for cluster_name in selected_clusters:
            narrowed_namespaces.update(cluster_namespaces.get(cluster_name, set()))
        if narrowed_namespaces:
            effective_available_namespaces = narrowed_namespaces

    for svc in visible_svc_rows:
        svc_id = f"svc:{svc.service_name}"
        allowed_service_ids.add(svc_id)
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
            pf_id = str(meta.get("sso_provider_id") or "backend:sso-provider")
            pf_label = str(meta.get("sso_provider_label") or "SSO Provider")
            nodes.setdefault(
                pf_id,
                TopologyNode(id=pf_id, label=pf_label, kind="backend", status="supporting"),
            )
            edges[(svc_id, pf_id, "depends-on")] = TopologyEdge(
                source=svc_id, target=pf_id, label="depends-on",
            )

    # If there are no catalog nodes and no runtime filters, return empty topology.
    # When filters are present, continue to runtime discovery so non-catalog namespaces
    # can still render live pods/services dynamically.
    if not nodes and not (selected_clusters or selected_namespaces):
        empty_topology = ServiceTopology(nodes=[], edges=[]).model_dump()
        empty_topology["metadata"] = {
            "available_clusters": sorted(available_clusters),
            "available_namespaces": sorted(effective_available_namespaces),
            "cluster_namespaces": {k: sorted(v) for k, v in sorted(cluster_namespaces.items())},
            "selected_clusters": selected_clusters,
            "selected_namespaces": selected_namespaces,
            "namespace_status": {},
            "metrics_source_ok": False,
            "pod_source_ok": False,
            "filtered_service_count": 0,
        }
        return empty_topology

    def _resolve_logical_service(raw_name: str) -> str:
        """Resolve AKS service/deployment names to catalog service names.

        Supports exact k8s label matches plus common prefixed naming patterns
        like "namespace-service" while keeping catalog ownership authoritative.
        """
        direct = aks_name_map.get(raw_name)
        if direct:
            return direct

        raw_lower = raw_name.lower()
        candidates: list[str] = []
        for svc in svc_rows:
            service_name = str(svc.service_name or "")
            service_lower = service_name.lower()
            k8s_label = str(svc.k8s_app_label or "")
            k8s_lower = k8s_label.lower()

            if service_lower and (raw_lower == service_lower or raw_lower.endswith(f"-{service_lower}")):
                candidates.append(service_name)
                continue
            if k8s_lower and (raw_lower == k8s_lower or raw_lower.endswith(f"-{k8s_lower}")):
                candidates.append(service_name)

        if len(candidates) == 1:
            return candidates[0]
        return raw_name

    # ── Service-level metrics overlay (independent from AKS availability) ───
    connector_seed_service = None
    if svc_rows:
        connector_seed_service = str(svc_rows[0].service_name or "").strip() or None

    logs_adapter_cfg = {}
    for row in log_source_rows:
        cfg = row.config_json or {}
        if row.source_type == "azure_monitor" and str(cfg.get("connector_role") or "") == "container_insights":
            if isinstance(cfg, dict):
                logs_adapter_cfg = dict(cfg)
                break

    if connector_seed_service:
        try:
            from corvin.connectors.config_resolver import ROLE_CONTAINER_INSIGHTS, resolve_log_source_config

            resolved_cfg = resolve_log_source_config(
                connector_seed_service,
                source_type="azure_monitor",
                role=ROLE_CONTAINER_INSIGHTS,
                fallback={},
            )
            if isinstance(resolved_cfg, dict):
                logs_adapter_cfg = dict(resolved_cfg)
        except Exception:
            logs_adapter_cfg = {}

    try:
        logs_adapter = ContainerLogsAdapter(config=logs_adapter_cfg)
    except TypeError:
        logs_adapter = ContainerLogsAdapter()
    service_metric_map: dict[str, tuple[dict[str, float | None], dict[str, dict[str, float | None]]]] = {}
    for svc in visible_svc_rows:
        logical_name = str(svc.service_name or "").strip()
        if not logical_name:
            continue
        svc_namespace = str(svc.namespace or "").strip() or None
        try:
            try:
                effective_namespace = svc_namespace
                if selected_namespaces and (not svc_namespace or svc_namespace not in selected_namespaces):
                    if len(selected_namespaces) > 1:
                        effective_namespace = None
                    else:
                        effective_namespace = selected_namespaces[0]
                if selected_clusters and not selected_namespaces:
                    # Do not force namespace when cluster-only filter is active.
                    effective_namespace = svc_namespace
                if selected_namespaces and svc_namespace in selected_namespaces:
                    effective_namespace = svc_namespace
                if selected_namespaces and not svc_namespace and len(selected_namespaces) > 1:
                    effective_namespace = None
                if selected_namespaces and not svc_namespace and len(selected_namespaces) == 1:
                    effective_namespace = selected_namespaces[0]
                metric_rows = logs_adapter.get_resource_metrics(logical_name, namespace=effective_namespace)
            except TypeError:
                metric_rows = logs_adapter.get_resource_metrics(logical_name)
        except Exception:
            metric_rows = []
        if metric_rows:
            metrics_source_ok = True
        service_resource = _resource_summary(metric_rows)
        pod_resource_map = _resource_summary_by_pod(metric_rows)
        service_metric_map[logical_name] = (service_resource, pod_resource_map)

        svc_id = f"svc:{logical_name}"
        base = nodes.get(svc_id)
        if base is None:
            continue
        nodes[svc_id] = TopologyNode(
            id=base.id,
            label=base.label,
            kind=base.kind,
            status=base.status,
            cpu_mcores=service_resource["cpu_mcores"],
            cpu_request_mcores=service_resource["cpu_request_mcores"],
            cpu_limit_mcores=service_resource["cpu_limit_mcores"],
            cpu_utilization_pct=service_resource["cpu_utilization_pct"],
            memory_mib=service_resource["memory_mib"],
            memory_request_mib=service_resource["memory_request_mib"],
            memory_limit_mib=service_resource["memory_limit_mib"],
            memory_utilization_pct=service_resource["memory_utilization_pct"],
        )

    # ── Live pod data from AKS — overlay status + pod children ───────────────
    try:
        aks_adapter_cfg = {}
        for row in log_source_rows:
            if row.source_type == "aks" and isinstance(row.config_json, dict):
                aks_adapter_cfg = dict(row.config_json)
                break
        try:
            adapter = AKSAdapter(config=aks_adapter_cfg)
        except TypeError:
            adapter = AKSAdapter()
        result = {"services": []}
        namespace_seed_service = None
        if visible_svc_rows:
            namespace_seed_service = str(visible_svc_rows[0].service_name or "").strip() or None
        if not namespace_seed_service and svc_rows:
            namespace_seed_service = str(svc_rows[0].service_name or "").strip() or None

        list_namespaces_fn = getattr(adapter, "list_namespaces", None)
        if callable(list_namespaces_fn):
            try:
                discovered = list_namespaces_fn(service_name=namespace_seed_service, cluster_names=selected_clusters or None)
                if isinstance(discovered, dict):
                    for cluster_name, ns_values in discovered.items():
                        if str(cluster_name).strip():
                            available_clusters.add(str(cluster_name).strip())
                        if isinstance(ns_values, list):
                            for ns in ns_values:
                                ns_name = str(ns).strip()
                                if ns_name:
                                    available_namespaces.add(ns_name)
                                    _add_cluster_ns(str(cluster_name), ns_name)
            except TypeError:
                # Backward-compatible adapter signature fallback.
                try:
                    discovered = list_namespaces_fn(cluster_names=selected_clusters or None)
                    if isinstance(discovered, dict):
                        for cluster_name, ns_values in discovered.items():
                            if str(cluster_name).strip():
                                available_clusters.add(str(cluster_name).strip())
                            if isinstance(ns_values, list):
                                for ns in ns_values:
                                    ns_name = str(ns).strip()
                                    if ns_name:
                                        available_namespaces.add(ns_name)
                                        _add_cluster_ns(str(cluster_name), ns_name)
                except Exception:
                    pass
            except Exception:
                pass

        # Secondary runtime fallback: derive namespaces from Container Insights inventory.
        try:
            needs_namespace_fallback = len(effective_available_namespaces) <= 1
            if needs_namespace_fallback:
                ci_cluster = selected_clusters[0] if selected_clusters else None
                ci_namespaces = logs_adapter.list_namespaces(
                    service_name=namespace_seed_service or "*",
                    cluster_name=ci_cluster,
                )
                if ci_namespaces:
                    for ns_name in ci_namespaces:
                        available_namespaces.add(ns_name)
                        if ci_cluster:
                            _add_cluster_ns(ci_cluster, ns_name)
        except Exception:
            pass

        service_seeds = [svc.service_name for svc in visible_svc_rows if svc.service_name]
        if not service_seeds and namespace_seed_service:
            service_seeds = [namespace_seed_service]
        if not service_seeds:
            service_seeds = [None]

        for seed_service in service_seeds:
            seed_namespace = None
            for svc in visible_svc_rows:
                if svc.service_name == seed_service:
                    seed_namespace = str(svc.namespace or "").strip() or None
                    break
            try:
                try:
                    request_namespace = seed_namespace
                    if selected_namespaces and len(selected_namespaces) == 1:
                        request_namespace = selected_namespaces[0]
                    attempt = adapter.list_all_pods(
                        namespace=request_namespace,
                        service_name=seed_service,
                        cluster_names=selected_clusters or None,
                        discover_namespaces=not selected_namespaces,
                    )
                except TypeError:
                    attempt = adapter.list_all_pods()
            except Exception:
                attempt = {"services": []}
            if attempt.get("services"):
                result = attempt
                break

        if not result.get("services"):
            try:
                try:
                    request_namespace = None
                    if selected_namespaces and len(selected_namespaces) == 1:
                        request_namespace = selected_namespaces[0]
                    result = adapter.list_all_pods(
                        namespace=request_namespace,
                        cluster_names=selected_clusters or None,
                        discover_namespaces=not selected_namespaces,
                    )
                except TypeError:
                    result = adapter.list_all_pods()
            except Exception:
                result = {"services": []}

        for svc in result.get("services", []):
            svc_clusters = [str(c).strip() for c in (svc.get("clusters", []) if isinstance(svc.get("clusters"), list) else []) if str(c).strip()]
            for cluster in svc_clusters:
                if str(cluster).strip():
                    available_clusters.add(str(cluster).strip())
            if selected_clusters and svc_clusters and not any(c in selected_clusters for c in svc_clusters):
                continue
            svc_namespaces = svc.get("namespaces") if isinstance(svc.get("namespaces"), list) else []
            if not svc_namespaces and isinstance(svc.get("pods"), list):
                svc_namespaces = sorted(
                    {
                        str(p.get("namespace")).strip()
                        for p in svc.get("pods", [])
                        if isinstance(p, dict) and str(p.get("namespace") or "").strip()
                    }
                )
            for cluster_name in svc_clusters:
                for ns in svc_namespaces:
                    _add_cluster_ns(cluster_name, str(ns))
            if selected_namespaces and svc_namespaces and not any(str(ns) in selected_namespaces for ns in svc_namespaces):
                continue

            raw_name = svc["name"]
            # Normalise k8s label → logical name using the DB-driven map
            logical_name = _resolve_logical_service(raw_name)
            svc_id = f"svc:{logical_name}"
            if svc_id not in allowed_service_ids and not (selected_namespaces or selected_clusters):
                continue
            pod_source_ok = True
            filtered_service_count += 1
            live_status = svc.get("status", "high")
            if logical_name not in service_metric_map:
                try:
                    dynamic_ns = selected_namespaces[0] if selected_namespaces else None
                    dynamic_rows = logs_adapter.get_resource_metrics(logical_name, namespace=dynamic_ns)
                except TypeError:
                    dynamic_rows = logs_adapter.get_resource_metrics(logical_name)
                except Exception:
                    dynamic_rows = []
                if dynamic_rows:
                    metrics_source_ok = True
                service_metric_map[logical_name] = (
                    _resource_summary(dynamic_rows),
                    _resource_summary_by_pod(dynamic_rows),
                )

            service_resource, pod_resource_map = service_metric_map.get(
                logical_name,
                ({
                    "cpu_mcores": None,
                    "cpu_request_mcores": None,
                    "cpu_limit_mcores": None,
                    "cpu_utilization_pct": None,
                    "memory_mib": None,
                    "memory_request_mib": None,
                    "memory_limit_mib": None,
                    "memory_utilization_pct": None,
                }, {}),
            )
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

                def _pod_base(value: str) -> str:
                    parts = [p for p in str(value or "").split("-") if p]
                    if len(parts) > 2:
                        return "-".join(parts[:-2])
                    return str(value or "")

                if not pod_resource and pod_name:
                    pod_base = _pod_base(pod_name)
                    for metric_pod_name, metric_values in pod_resource_map.items():
                        metric_key = str(metric_pod_name or "")
                        metric_base = _pod_base(metric_key)
                        if (
                            metric_key == pod_name
                            or metric_key.endswith(pod_name)
                            or pod_name.endswith(metric_key)
                            or (pod_base and metric_base and pod_base == metric_base)
                        ):
                            pod_resource = metric_values
                            break
                for key, value in pod_resource.items():
                    if value is not None:
                        pod_copy[key] = value
                pod_node = build_pod_topology_node(pod_copy)
                nodes[pod_node.id] = pod_node
                edges[(svc_id, pod_node.id, "runs")] = TopologyEdge(
                    source=svc_id, target=pod_node.id, label="runs",
                )

            for ns in svc_namespaces:
                ns_name = str(ns)
                if not ns_name:
                    continue
                state = namespace_status.setdefault(ns_name, {"high": 0, "recovering": 0, "hot": 0, "services": 0, "status": "high"})
                state["services"] = int(state.get("services", 0)) + 1
                if live_status in ("high", "recovering", "hot"):
                    state[live_status] = int(state.get(live_status, 0)) + 1
                if int(state.get("hot", 0)) > 0:
                    state["status"] = "hot"
                elif int(state.get("recovering", 0)) > 0:
                    state["status"] = "recovering"
                else:
                    state["status"] = "high"

        # Fallback: derive pod runtime from Container Insights when AKS API is unavailable.
        if not pod_source_ok:
            for svc in visible_svc_rows:
                logical_name = str(svc.service_name or "").strip()
                if not logical_name:
                    continue
                ns_candidates = selected_namespaces or ([str(svc.namespace)] if str(svc.namespace or "").strip() else [])
                service_rows: list[dict] = []
                for ns in ns_candidates:
                    try:
                        rows = logs_adapter.get_pod_inventory(logical_name, namespace=ns)
                    except TypeError:
                        rows = logs_adapter.get_pod_inventory(logical_name)
                    except Exception:
                        rows = []
                    if rows:
                        service_rows.extend(rows)

                if not service_rows:
                    continue

                service_resource, pod_resource_map = service_metric_map.get(
                    logical_name,
                    ({
                        "cpu_mcores": None,
                        "cpu_request_mcores": None,
                        "cpu_limit_mcores": None,
                        "cpu_utilization_pct": None,
                        "memory_mib": None,
                        "memory_request_mib": None,
                        "memory_limit_mib": None,
                        "memory_utilization_pct": None,
                    }, {}),
                )

                pod_payloads: list[dict] = []
                for row in service_rows:
                    pod_name = str(row.get("Name") or "").strip()
                    ns_name = str(row.get("Namespace") or row.get("namespace") or (ns_candidates[0] if ns_candidates else "")).strip()
                    phase = str(row.get("PodStatus") or "Unknown")
                    restarts = int(row.get("PodRestartCount") or row.get("ContainerRestartCount") or 0)
                    pod_payload = {
                        "name": pod_name,
                        "namespace": ns_name,
                        "phase": phase,
                        "containers": [{
                            "name": "main",
                            "ready": phase in ("Running", "Succeeded"),
                            "restart_count": restarts,
                        }],
                    }
                    metric_values = pod_resource_map.get(pod_name, {})
                    for key, value in metric_values.items():
                        if value is not None:
                            pod_payload[key] = value
                    pod_payloads.append(pod_payload)

                any_failed = any(p.get("phase") not in ("Running", "Succeeded") for p in pod_payloads)
                any_restarting = any(
                    any(int(c.get("restart_count", 0)) > 3 for c in p.get("containers", []))
                    for p in pod_payloads
                )
                live_status = "hot" if any_failed else ("recovering" if any_restarting else "high")

                svc_id = f"svc:{logical_name}"
                nodes[svc_id] = TopologyNode(
                    id=svc_id,
                    label=logical_name,
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

                for pod in pod_payloads:
                    pod_node = build_pod_topology_node(pod)
                    nodes[pod_node.id] = pod_node
                    edges[(svc_id, pod_node.id, "runs")] = TopologyEdge(
                        source=svc_id,
                        target=pod_node.id,
                        label="runs",
                    )

                for ns_name in {str(p.get("namespace") or "") for p in pod_payloads if str(p.get("namespace") or "")}:
                    state = namespace_status.setdefault(ns_name, {"high": 0, "recovering": 0, "hot": 0, "services": 0, "status": "high"})
                    state["services"] = int(state.get("services", 0)) + 1
                    state[live_status] = int(state.get(live_status, 0)) + 1
                    if int(state.get("hot", 0)) > 0:
                        state["status"] = "hot"
                    elif int(state.get("recovering", 0)) > 0:
                        state["status"] = "recovering"
                    else:
                        state["status"] = "high"

                pod_source_ok = True
                filtered_service_count += 1

        # Namespace-wide fallback: when selected namespace has no app-catalog services,
        # still render runtime pods/metrics discovered from Container Insights.
        if not pod_source_ok and selected_namespaces and not visible_svc_rows:
            selected_ns = selected_namespaces[0]
            try:
                ns_rows = logs_adapter.get_pod_inventory("all", namespace=selected_ns)
            except TypeError:
                ns_rows = logs_adapter.get_pod_inventory("all")
            except Exception:
                ns_rows = []

            by_runtime_service: dict[str, list[dict]] = {}

            def _runtime_service_name(pod_name: str, controller_name: str | None) -> str:
                ctl = str(controller_name or "").strip()
                if ctl:
                    return ctl
                parts = [p for p in str(pod_name or "").split("-") if p]
                if len(parts) > 2:
                    return "-".join(parts[:-2])
                return str(pod_name or "")

            for row in ns_rows:
                if not isinstance(row, dict):
                    continue
                pod_name = str(row.get("Name") or "").strip()
                if not pod_name:
                    continue
                runtime_service = _runtime_service_name(pod_name, row.get("ControllerName"))
                if not runtime_service:
                    continue
                by_runtime_service.setdefault(runtime_service, []).append(row)

            for runtime_service, rows in by_runtime_service.items():
                try:
                    metric_rows = logs_adapter.get_resource_metrics(runtime_service, namespace=selected_ns)
                except TypeError:
                    metric_rows = logs_adapter.get_resource_metrics(runtime_service)
                except Exception:
                    metric_rows = []

                if metric_rows:
                    metrics_source_ok = True

                service_resource = _resource_summary(metric_rows)
                pod_resource_map = _resource_summary_by_pod(metric_rows)

                pod_payloads: list[dict] = []
                for row in rows:
                    pod_name = str(row.get("Name") or "").strip()
                    phase = str(row.get("PodStatus") or "Unknown")
                    restarts = int(row.get("PodRestartCount") or row.get("ContainerRestartCount") or 0)
                    payload = {
                        "name": pod_name,
                        "namespace": selected_ns,
                        "phase": phase,
                        "containers": [{
                            "name": "main",
                            "ready": phase in ("Running", "Succeeded"),
                            "restart_count": restarts,
                        }],
                    }
                    metrics = pod_resource_map.get(pod_name, {})
                    for key, value in metrics.items():
                        if value is not None:
                            payload[key] = value
                    pod_payloads.append(payload)

                any_failed = any(p.get("phase") not in ("Running", "Succeeded") for p in pod_payloads)
                any_restarting = any(
                    any(int(c.get("restart_count", 0)) > 3 for c in p.get("containers", []))
                    for p in pod_payloads
                )
                live_status = "hot" if any_failed else ("recovering" if any_restarting else "high")

                svc_id = f"svc:{runtime_service}"
                nodes[svc_id] = TopologyNode(
                    id=svc_id,
                    label=runtime_service,
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

                for pod in pod_payloads:
                    pod_node = build_pod_topology_node(pod)
                    nodes[pod_node.id] = pod_node
                    edges[(svc_id, pod_node.id, "runs")] = TopologyEdge(
                        source=svc_id,
                        target=pod_node.id,
                        label="runs",
                    )

                state = namespace_status.setdefault(selected_ns, {"high": 0, "recovering": 0, "hot": 0, "services": 0, "status": "high"})
                state["services"] = int(state.get("services", 0)) + 1
                state[live_status] = int(state.get(live_status, 0)) + 1
                if int(state.get("hot", 0)) > 0:
                    state["status"] = "hot"
                elif int(state.get("recovering", 0)) > 0:
                    state["status"] = "recovering"
                else:
                    state["status"] = "high"

                pod_source_ok = True
                filtered_service_count += 1

    except Exception as exc:
        _log.warning("topology/live AKS call failed (DB-seeded nodes still returned): %s", exc)

    if len(selected_namespaces) == 1 and not visible_svc_rows and not os.getenv("PYTEST_CURRENT_TEST"):
        selected_ns = selected_namespaces[0]
        live_pod_names = _kubectl_live_pod_names(selected_ns)
        if live_pod_names:
            live_pod_node_ids = {
                node_id
                for node_id, node in nodes.items()
                if node.kind == "pod"
                and str(node.namespace or "").strip() == selected_ns
                and str(node.label or "").strip() in live_pod_names
            }

            # Only reconcile if we found matching pod nodes
            if live_pod_node_ids:
                keep_node_ids = {
                    node_id
                    for node_id, node in nodes.items()
                    if node.kind != "pod"
                }
                keep_node_ids.update(live_pod_node_ids)

                services_with_live_pods = {
                    edge.source
                    for edge in edges.values()
                    if edge.target in live_pod_node_ids
                }
                for node_id, node in list(nodes.items()):
                    if node.kind == "service" and node_id.startswith("svc:") and node_id not in services_with_live_pods:
                        keep_node_ids.discard(node_id)

                nodes = {
                    node_id: node
                    for node_id, node in nodes.items()
                    if node_id in keep_node_ids
                }
                edges = {
                    key: edge
                    for key, edge in edges.items()
                    if edge.source in nodes and edge.target in nodes
                }

                pod_source_ok = any(node.kind == "pod" for node in nodes.values())
                filtered_service_count = sum(1 for node in nodes.values() if node.kind == "service")

    catalog_service_count = len(
        [svc for svc in visible_svc_rows if str(svc.service_name or "").strip()]
    )

    topology = ServiceTopology(nodes=list(nodes.values()), edges=list(edges.values())).model_dump()
    effective_available_namespaces = set(available_namespaces)
    if selected_clusters:
        narrowed_namespaces: set[str] = set()
        for cluster_name in selected_clusters:
            narrowed_namespaces.update(cluster_namespaces.get(cluster_name, set()))
        if narrowed_namespaces:
            effective_available_namespaces = narrowed_namespaces

    topology["metadata"] = {
        "available_clusters": sorted(available_clusters),
        "available_namespaces": sorted(effective_available_namespaces),
        "cluster_namespaces": {k: sorted(v) for k, v in sorted(cluster_namespaces.items())},
        "namespace_source": "runtime_aks_discovery_with_db_fallback",
        "selected_clusters": selected_clusters,
        "selected_namespaces": selected_namespaces,
        "namespace_status": namespace_status,
        "metrics_source_ok": metrics_source_ok,
        "pod_source_ok": pod_source_ok,
        "filtered_service_count": filtered_service_count,
        "catalog_service_count": catalog_service_count,
        "runtime_unmapped_pods_only": bool(selected_namespaces and catalog_service_count == 0),
    }
    return topology


@router.get("/score", response_model=dict)
def get_service_score(
    service_name: str = Query(..., description="Service name to score"),
    environment: str = Query(..., description="Target environment (e.g. production, staging, dev)"),
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

    _runbook_model = llm_cfg.get("fallback_model") or llm_cfg.get("model")
    if not _runbook_model:
        raise ValueError("models/llm.yaml must define 'model' or 'fallback_model'")

    try:
        response = litellm.completion(
            model=_runbook_model,
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


@router.get("/{request_id:investigation_id}", response_model=InvestigationResult)
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

    config = resolve_ado_boards_config_for_service(result.request.service_name)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Azure Boards connector is not configured for this service.",
        )
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

        if app_id is None:
            raise HTTPException(status_code=422, detail="Investigation has no application context.")

        connector = session.query(OutboundConnectorRow).filter(
            OutboundConnectorRow.application_id == app_id,
            OutboundConnectorRow.connector_type == "servicenow",
            OutboundConnectorRow.is_active == True,  # noqa: E712
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
    environment: str
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


# ── Feature 8: Root Cause Debate Mode ────────────────────────────────────────


class SelectHypothesisRequest(BaseModel):
    hypothesis_id: str = Field(..., min_length=1, max_length=10)


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_debate_meta(hypotheses: list[dict], selected_id: str | None) -> dict:
    """Build compact decision-support metadata for the debate panel."""
    if not hypotheses:
        return {
            "leader_id": None,
            "leader_score": 0.0,
            "runner_up_id": None,
            "runner_up_score": 0.0,
            "score_gap": 0.0,
            "is_ambiguous": False,
            "recommendation": "No hypotheses available yet.",
            "pairwise": [],
            "selected_id": selected_id,
        }

    ranked = sorted(
        hypotheses,
        key=lambda h: _to_float(h.get("confidence_score"), 0.0),
        reverse=True,
    )
    leader = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else leader
    leader_score = _to_float(leader.get("confidence_score"), 0.0)
    runner_score = _to_float(runner.get("confidence_score"), 0.0)
    gap = max(0.0, round(leader_score - runner_score, 3))
    is_ambiguous = len(ranked) > 1 and gap < 0.12

    if selected_id:
        recommendation = "Root cause selected. Verify action outcomes and close loop with post-fix validation."
    elif is_ambiguous:
        recommendation = (
            "Top hypotheses are close. Run one targeted disproof check before selecting a winner."
        )
    else:
        recommendation = "Confidence gap is clear enough to proceed with a primary root-cause candidate."

    pairwise: list[dict] = []
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            left = ranked[i]
            right = ranked[j]
            left_score = _to_float(left.get("confidence_score"), 0.0)
            right_score = _to_float(right.get("confidence_score"), 0.0)
            winner = left if left_score >= right_score else right
            loser = right if winner is left else left
            pairwise.append(
                {
                    "left_id": left.get("id"),
                    "right_id": right.get("id"),
                    "winner_id": winner.get("id"),
                    "score_gap": round(abs(left_score - right_score), 3),
                    "reason": (
                        f"{winner.get('id')} leads on confidence "
                        f"({_to_float(winner.get('confidence_score'), 0.0):.2f} vs "
                        f"{_to_float(loser.get('confidence_score'), 0.0):.2f})"
                    ),
                }
            )

    return {
        "leader_id": leader.get("id"),
        "leader_score": round(leader_score, 3),
        "runner_up_id": runner.get("id") if len(ranked) > 1 else None,
        "runner_up_score": round(runner_score, 3) if len(ranked) > 1 else None,
        "score_gap": gap,
        "is_ambiguous": is_ambiguous,
        "recommendation": recommendation,
        "pairwise": pairwise,
        "selected_id": selected_id,
    }


@router.post("/{id}/hypotheses", response_model=dict)
def generate_hypotheses(
    id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Generate competing root-cause hypotheses for an existing investigation.

    Reads the investigation result from DB, calls HypothesisService, persists
    the generated hypotheses, and returns them.

    Returns 404 when the investigation is not found.
    Returns 422 when debate_mode.enabled=false in investigation.yaml.
    """
    from corvin.strategy.hypothesis_service import HypothesisService

    result = repo.get_investigation_result(id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {id!r} not found.")

    svc = HypothesisService()
    if not svc.is_enabled():
        raise HTTPException(
            status_code=422,
            detail="Debate mode is disabled (debate_mode.enabled=false in investigation.yaml).",
        )

    hypotheses = svc.generate(result)
    repo.save_hypotheses(id, hypotheses)

    hypotheses_payload = [h.model_dump(mode="json") for h in hypotheses]

    return {
        "request_id": id,
        "hypotheses": hypotheses_payload,
        "selected_hypothesis_id": None,
        "debate_meta": _build_debate_meta(hypotheses_payload, None),
    }


@router.get("/{id}/hypotheses", response_model=dict)
def get_hypotheses(
    id: str,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return stored hypotheses for an investigation.

    Returns 404 when the investigation is not found.
    Returns an empty hypotheses list when the investigation pre-dates Feature 8.
    """
    # Confirm investigation exists
    with repo._session_factory() as session:
        from corvin.storage.models import InvestigationRequestRow
        req_row = session.get(InvestigationRequestRow, id)
        if req_row is None:
            raise HTTPException(status_code=404, detail=f"Investigation {id!r} not found.")
        selected = getattr(req_row, "selected_hypothesis_id", None)

    stored = repo.get_hypotheses(id)

    hypotheses_payload = stored or []

    return {
        "request_id": id,
        "hypotheses": hypotheses_payload,
        "selected_hypothesis_id": selected,
        "debate_meta": _build_debate_meta(hypotheses_payload, selected),
    }


@router.post("/{id}/select-hypothesis", response_model=dict)
def select_hypothesis(
    id: str,
    body: SelectHypothesisRequest,
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Set the winning hypothesis and regenerate fix strategy.

    Sets selected_hypothesis_id on the investigation row.
    Then regenerates the fix strategy based on the winning hypothesis's root_cause.
    Returns the updated InvestigationResult.

    Returns 404 when the investigation is not found.
    Returns 400 when the hypothesis_id is not in the stored list.
    """
    from corvin.strategy.fix_strategy_generator import FixStrategyGenerator
    from corvin.core.contracts import RCAOutput, RCAConfidence

    result = repo.get_investigation_result(id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {id!r} not found.")

    stored = repo.get_hypotheses(id) or []
    hypothesis_map = {h["id"]: h for h in stored if isinstance(h, dict)}

    if body.hypothesis_id not in hypothesis_map:
        raise HTTPException(
            status_code=400,
            detail=f"Hypothesis {body.hypothesis_id!r} not found. Available: {list(hypothesis_map.keys())}",
        )

    selected = hypothesis_map[body.hypothesis_id]
    repo.set_selected_hypothesis(id, body.hypothesis_id)

    # Regenerate fix strategy using the selected hypothesis root_cause.
    # We synthesise an RCAOutput that substitutes the hypothesis fields.
    patched_rca = RCAOutput(
        request_id=id,
        summary=selected.get("title", result.rca.summary),
        root_cause=selected.get("root_cause", result.rca.root_cause),
        contributing_factors=selected.get("supporting_signals", result.rca.contributing_factors),
        confidence=RCAConfidence.MEDIUM,
        confidence_reasoning=f"Selected hypothesis: {selected.get('title', '')}",
        evidence_references=selected.get("evidence_ids", result.rca.evidence_references),
    )

    try:
        fix_gen = FixStrategyGenerator()
        new_fix = fix_gen.generate(result.request, patched_rca)
        new_fix = new_fix.model_copy(update={"request_id": id})
    except Exception as exc:
        _log.warning("select-hypothesis: fix strategy regeneration failed: %s", exc)
        new_fix = result.fix_strategy

    # Persist via upsert directly
    from corvin.storage.models import FixStrategyOutputRow
    with repo._session_factory() as session:
        existing = session.execute(
            __import__("sqlalchemy").select(FixStrategyOutputRow).where(
                FixStrategyOutputRow.request_id == id
            )
        ).scalar_one_or_none()
        if existing:
            existing.summary = new_fix.summary
            existing.actions = [a.model_dump(mode="json") for a in new_fix.actions]
            existing.justification = new_fix.justification
        else:
            session.add(FixStrategyOutputRow(
                request_id=id,
                summary=new_fix.summary,
                actions=[a.model_dump(mode="json") for a in new_fix.actions],
                justification=new_fix.justification,
            ))
        session.commit()

    # Return updated result
    updated = repo.get_investigation_result(id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to reload investigation after update.")

    return {
        **updated.model_dump(mode="json"),
        "selected_hypothesis_id": body.hypothesis_id,
        "hypotheses": stored,
        "debate_meta": _build_debate_meta(stored, body.hypothesis_id),
    }


# ── Feature 9: Incident Heatmap Calendar ─────────────────────────────────────


@router.get("/heatmap", response_model=dict)
def get_incident_heatmap(
    days: int = Query(default=90, ge=1, le=365),
    service_name: Optional[str] = Query(default=None),
    environment: Optional[str] = Query(default=None),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Return daily investigation counts for the GitHub-style heatmap calendar.

    days: lookback window — capped by heatmap.max_days in investigation.yaml.
    Severity thresholds are loaded from investigation.yaml and returned
    alongside the data so the frontend never needs to hardcode them.

    Returns:
        days: list of {date, count, severity}
        max_count: the highest single-day count in the window
        total_incidents: total investigations in the window
        date_range: {start, end}
        severity_thresholds: {low, medium, high, critical}
    """
    from datetime import date, timedelta

    policy = load_config("policies/investigation", get_env())
    heatmap_cfg = policy.get("heatmap", {})

    # Honour max_days cap from config
    max_days = int(heatmap_cfg.get("max_days", 365))
    days = min(days, max_days)

    thresholds = heatmap_cfg.get("severity_thresholds", {
        "low": 1, "medium": 3, "high": 5, "critical": 10
    })

    # Build a complete zero-filled date index for the window
    today = date.today()
    start_date = today - timedelta(days=days - 1)
    all_dates = {
        (start_date + timedelta(days=i)).isoformat(): 0
        for i in range(days)
    }

    # Fetch DB data and merge
    db_rows = repo.get_heatmap_data(days=days, service_name=service_name, environment=environment)
    for row in db_rows:
        if row["date"] in all_dates:
            all_dates[row["date"]] = row["count"]

    def _severity(count: int) -> str:
        if count == 0:
            return "none"
        if count >= int(thresholds.get("critical", 10)):
            return "critical"
        if count >= int(thresholds.get("high", 5)):
            return "high"
        if count >= int(thresholds.get("medium", 3)):
            return "medium"
        return "low"

    # Build service lookup from DB rows
    services_by_date = {row["date"]: row.get("services", {}) for row in db_rows}

    days_list = [
        {
            "date": d,
            "count": c,
            "severity": _severity(c),
            "services": services_by_date.get(d, {}),
        }
        for d, c in sorted(all_dates.items())
    ]

    total = sum(d["count"] for d in days_list)
    max_count = max((d["count"] for d in days_list), default=0)

    return {
        "days": days_list,
        "max_count": max_count,
        "total_incidents": total,
        "date_range": {"start": start_date.isoformat(), "end": today.isoformat()},
        "severity_thresholds": thresholds,
    }


# ── Feature 10: Compliance Evidence Pack ─────────────────────────────────────


@router.get("/{id}/compliance-pack")
def download_compliance_pack(
    id: str,
    format: str = Query(default="zip", pattern="^(zip|pdf)$"),
    repo: InvestigationRepository = Depends(get_repository),
) -> Response:
    """Generate and download a tamper-evident compliance evidence bundle.

    format=zip — returns a ZIP archive with all evidence files + SHA-256 manifest.
    format=pdf — returns a single PDF document with all sections.

    The SHA-256 hash of the manifest.json is included as integrity.sha256.
    Watermark text and supported frameworks are configurable via investigation.yaml.

    Returns 404 when the investigation is not found.
    Returns 422 when compliance_pack.enabled=false in investigation.yaml.
    """
    from corvin.strategy.compliance_pack import CompliancePackBuilder
    from corvin.storage.db import get_session
    from corvin.storage.models import InvestigationRequestRow

    policy = load_config("policies/investigation", get_env())
    pack_cfg = policy.get("compliance_pack", {})
    if not pack_cfg.get("enabled", True):
        raise HTTPException(
            status_code=422,
            detail="Compliance pack is disabled (compliance_pack.enabled=false in investigation.yaml).",
        )

    result = repo.get_investigation_result(id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Investigation {id!r} not found.")

    # Load approved_at from the DB row — not exposed on the contract model.
    approved_at = None
    with get_session() as session:
        req_row = session.get(InvestigationRequestRow, id)
        if req_row is not None:
            approved_at = req_row.approved_at

    # Include post-mortem in the pack when already generated (optional)
    pm = None
    try:
        pm = repo.get_post_mortem(id)
    except Exception:
        pass  # post-mortem is optional

    builder = CompliancePackBuilder(config=pack_cfg)

    if format == "pdf":
        content = builder.build_pdf(result, pm, approved_at=approved_at)
        # When reportlab is absent, build_pdf falls back to plain text.
        if CompliancePackBuilder.reportlab_available():
            media_type = "application/pdf"
            ext = "pdf"
        else:
            media_type = "text/plain; charset=utf-8"
            ext = "txt"
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="corvin-evidence-pack-{id}.{ext}"'
            },
        )
    else:
        zip_bytes = builder.build_zip(result, pm, approved_at=approved_at)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="corvin-evidence-pack-{id}.zip"'
            },
        )


# ── Feature 11: Similarity Network ───────────────────────────────────────────


@router.get("/similarity-network", response_model=dict)
def get_similarity_network(
    focus_id: Optional[str] = Query(default=None, description="Highlight edges from/to this investigation ID"),
    limit: int = Query(default=50, ge=5, le=200, description="Max investigations to include as nodes"),
    min_similarity: float = Query(default=0.20, ge=0.05, le=0.95, description="Minimum similarity score to draw an edge"),
    service_name: Optional[str] = Query(default=None, description="Filter nodes to a specific service"),
    environment: Optional[str] = Query(default=None, description="Filter nodes to a specific environment"),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict:
    """Build an investigation similarity graph for the Similarity Network view.

    Each node is a completed investigation. Edges connect pairs whose
    RCA text, service match, and time proximity exceed ``min_similarity``.

    Similarity is computed using:
      - Service + environment overlap (40 %)
      - RCA Jaccard text similarity  (40 %)
      - Time proximity               (20 %)

    When ``focus_id`` is supplied only edges that touch the focus node are
    returned, reducing graph density for single-investigation drill-down.
    """
    from corvin.strategy.similarity_network import SimilarityNetworkEngine

    policy = load_config("policies/investigation", get_env())
    engine = SimilarityNetworkEngine(config=policy)

    investigations = repo.list_investigations_for_similarity(
        limit=limit,
        service_name=service_name,
        environment=environment,
    )

    return engine.build(
        investigations=investigations,
        focus_id=focus_id,
        min_similarity=min_similarity,
    )

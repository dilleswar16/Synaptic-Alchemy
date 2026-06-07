"""
Trigger ingestion routes.

Receives inbound trigger payloads from external sources (Azure Monitor,
Teams, etc.) and normalizes them into InvestigationRequests.

The ``/azure-alert`` endpoint runs the full engine pipeline (mirroring
``POST /investigations/``) so an Azure Action Group webhook can drive an
end-to-end investigation with no human in the loop.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from corvin.core.contracts import InvestigationRequest, TriggerSource
from corvin.delivery.rca_notification import send_rca_email_if_enabled
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository
from corvin.triggers.azure_alert import normalize_azure_alert

router = APIRouter()
_log = logging.getLogger(__name__)


# ── Dependency providers (overridable in tests) ───────────────────────────────


def get_engine() -> InvestigationEngine:
    return InvestigationEngine()


def get_repository() -> InvestigationRepository:
    return InvestigationRepository()


def get_teams_adapter() -> TeamsAdapter:
    return TeamsAdapter()


# ── Background worker ─────────────────────────────────────────────────────────


def _run_investigation_in_background(
    request: InvestigationRequest,
    engine: InvestigationEngine,
    repo: InvestigationRepository,
    teams: TeamsAdapter,
) -> None:
    """Run engine -> persist -> teams. Never raises.

    Called from a FastAPI BackgroundTask so the inbound webhook returns 202
    immediately. Azure Monitor Action Groups have a ~120s connection timeout
    and retry on non-2xx OR timeout, so we MUST not block the response on
    engine work that may take longer than that.
    """
    try:
        result = engine.run(request)
    except Exception as exc:  # noqa: BLE001
        _log.exception(
            "Azure alert investigation failed for request %s: %s", request.id, exc
        )
        return

    try:
        repo.save_investigation_result(result)
    except Exception as exc:  # noqa: BLE001
        _log.exception(
            "Azure alert persistence failed for request %s: %s", request.id, exc
        )
        # fall through — still try to deliver to Teams so SREs see the result

    try:
        teams.send_result(result)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Teams delivery failed (non-fatal) for %s: %s", request.id, exc)

    # Optional and non-fatal: email RCA PDF when configured.
    send_rca_email_if_enabled(result)


@router.post("/azure-alert", status_code=202)
def receive_azure_alert(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    engine: InvestigationEngine = Depends(get_engine),
    repo: InvestigationRepository = Depends(get_repository),
    teams: TeamsAdapter = Depends(get_teams_adapter),
) -> dict[str, str]:
    """
    Receive an Azure Monitor Common Alert Schema webhook payload.

    Acknowledges the alert immediately with 202 then runs the investigation
    pipeline (engine -> persist -> Teams) in a background task.

    Azure Action Groups should point at:  POST /triggers/azure-alert
    """
    request: InvestigationRequest = normalize_azure_alert(payload)

    background_tasks.add_task(
        _run_investigation_in_background,
        request,
        engine,
        repo,
        teams,
    )

    return {
        "request_id": request.id,
        "status": "accepted",
        "trigger_source": request.trigger_source,
        "service_name": request.service_name,
    }


@router.post("/manual", status_code=202)
def manual_trigger(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    engine: InvestigationEngine = Depends(get_engine),
    repo: InvestigationRepository = Depends(get_repository),
) -> dict[str, str]:
    """
    Accept a free-form manual trigger from Teams or other surfaces.

    Expects at minimum: service_name, environment, description.
    """
    request = InvestigationRequest(
        trigger_source=TriggerSource.TEAMS,
        service_name=payload.get("service_name", "unknown"),
        environment=payload.get("environment", "unknown"),
        description=payload.get("description", "Manual trigger"),
        raw_payload=payload,
    )
    # Persist the request and hand off to the investigation orchestrator
    repo.save_request(request)
    background_tasks.add_task(engine.run_investigation, request)
    return {"request_id": request.id, "status": "accepted", "trigger_source": request.trigger_source}


# ── V3.5 Alert Simulator ──────────────────────────────────────────────────────

class SimulateAlertRequest(BaseModel):
    """Request body for the alert simulator endpoint."""
    service_name: str
    environment: str = "dev"
    scenario: str  # hpa_failure | five_zero_three_spike | auth_errors | memory_leak
    description: str | None = None


def _resolve_preset_description(service_name: str, scenario: str, default: str) -> str:
    """Look up the preset description from the DB for the matching service/scenario.

    Falls back to *default* if no matching SimulatorPresetRow is found.
    This removes the hardcoded _SCENARIO_DESCRIPTIONS dict — descriptions
    now live in the DB, managed via the Application Panel.
    """
    try:
        from corvin.storage.db import get_session
        from corvin.storage.models import ApplicationServiceRow, SimulatorPresetRow
        from sqlalchemy import or_
        with get_session() as session:
            svc = session.query(ApplicationServiceRow).filter(
                or_(ApplicationServiceRow.service_name == service_name,
                    ApplicationServiceRow.k8s_app_label == service_name)
            ).first()
            if svc is None:
                return default
            preset = session.query(SimulatorPresetRow).filter_by(
                application_id=svc.application_id,
                scenario_id=scenario,
            ).first()
            if preset and preset.description:
                return preset.description
    except Exception as exc:
        _log.debug("preset description DB lookup failed: %s", exc)
    return default


@router.post("/simulate", status_code=202)
def simulate_alert(
    body: SimulateAlertRequest,
    background_tasks: BackgroundTasks,
    engine: InvestigationEngine = Depends(get_engine),
    repo: InvestigationRepository = Depends(get_repository),
    teams: TeamsAdapter = Depends(get_teams_adapter),
) -> dict[str, str]:
    """
    Fire a synthetic alert investigation without needing a real Azure Monitor event.

    Builds a realistic-looking InvestigationRequest from the chosen scenario preset
    and runs the full pipeline (evidence → RCA → fix strategy) in a background task,
    exactly as a real Azure alert would.

    Available scenarios: hpa_failure | five_zero_three_spike | auth_errors | memory_leak

    Returns immediately with the new request_id so the UI can open the SSE stream.
    """
    default_desc = f"Simulated {body.scenario} scenario on {body.service_name}."
    description = body.description or _resolve_preset_description(
        body.service_name, body.scenario, default_desc
    )

    request = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name=body.service_name,
        environment=body.environment,
        description=f"[SIMULATED: {body.scenario}] {description}",
    )

    background_tasks.add_task(
        _run_investigation_in_background,
        request,
        engine,
        repo,
        teams,
    )

    return {
        "request_id": request.id,
        "status": "accepted",
        "scenario": body.scenario,
        "service_name": body.service_name,
        "environment": body.environment,
    }


# ── V5.0 F1: Autonomous Agent Webhook ────────────────────────────────────────


class AutonomousAlertRequest(BaseModel):
    """Incoming alert payload for autonomous investigation."""
    service_name: str
    environment: str
    description: str
    priority: str = "P2"
    source: str = "webhook"  # webhook | alertmanager | azure_monitor | datadog


def _run_autonomous_agent_in_background(
    request: InvestigationRequest,
) -> None:
    """Run the full autonomous pipeline in background. Never raises."""
    from corvin.strategy.autonomous_agent import AutonomousAgent
    try:
        agent = AutonomousAgent()
        result = agent.run(request)
        _log.info(
            "Autonomous agent completed for %s — status=%s, events=%d",
            request.id, result.get("status"), len(result.get("events", [])),
        )
    except Exception as exc:
        _log.exception("Autonomous agent failed for request %s: %s", request.id, exc)


@router.post("/autonomous", status_code=202)
def autonomous_alert(
    body: AutonomousAlertRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    V5.0 Autonomous Incident Response — Zero-touch investigation.

    Accepts an alert payload and immediately launches the full autonomous pipeline:
    1. Auto-investigate (evidence collection + RCA)
    2. Generate causal chain
    3. Draft incident communications
    4. Notify Teams with proposed fix + approval buttons
    5. Wait for human approval before executing remediation

    "Corvin investigated the 3AM incident before your SRE woke up."
    """
    request = InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name=body.service_name,
        environment=body.environment,
        description=f"[AUTONOMOUS:{body.source}] {body.description}",
        raw_payload={"source": body.source, "priority": body.priority},
    )

    background_tasks.add_task(_run_autonomous_agent_in_background, request)

    return {
        "request_id": request.id,
        "status": "autonomous_investigation_started",
        "service_name": body.service_name,
        "environment": body.environment,
        "priority": request.incident_priority,
        "message": "Corvin is autonomously investigating. You will be notified via Teams when complete.",
    }

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
def manual_trigger(payload: dict[str, Any]) -> dict[str, str]:
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
    # TODO (Slice 5+): hand off to orchestrator
    return {"request_id": request.id, "status": "accepted", "trigger_source": request.trigger_source}


# ── V3.5 Alert Simulator ──────────────────────────────────────────────────────

class SimulateAlertRequest(BaseModel):
    """Request body for the alert simulator endpoint."""
    service_name: str
    environment: str = "dev"
    scenario: str  # hpa_failure | five_zero_three_spike | auth_errors | memory_leak
    description: str | None = None


_SCENARIO_DESCRIPTIONS: dict[str, str] = {
    "hpa_failure": "HPA not scaling — pods stuck at 1 replica despite 92% CPU. Partner integrations degraded.",
    "five_zero_three_spike": "503 error rate spiked to 18% on /v1/funds endpoint. Two pods restarted in the last 30 minutes.",
    "auth_errors": "JWT validation failures spiking — service returning 401 on 35% of SSO requests since 09:00.",
    "memory_leak": "Heap usage climbing steadily — service at 89% memory limit, OOM kill expected within 2 hours.",
}


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
    description = body.description or _SCENARIO_DESCRIPTIONS.get(
        body.scenario,
        f"Simulated {body.scenario} scenario on {body.service_name}.",
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


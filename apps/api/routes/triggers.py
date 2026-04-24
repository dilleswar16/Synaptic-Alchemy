"""
Trigger ingestion routes.

Receives inbound trigger payloads from external sources (Azure Monitor,
Teams, etc.) and normalizes them into InvestigationRequests.

V1 stubs: normalizes and returns the request ID.
Orchestrator hand-off and persistence are wired in a later slice.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from corvin.core.contracts import InvestigationRequest, TriggerSource
from corvin.triggers.azure_alert import normalize_azure_alert

router = APIRouter()


@router.post("/azure-alert", status_code=202)
def receive_azure_alert(payload: dict[str, Any]) -> dict[str, str]:
    """
    Receive an Azure Monitor Common Alert Schema webhook payload.

    Azure Action Groups should point at:  POST /triggers/azure-alert
    """
    request: InvestigationRequest = normalize_azure_alert(payload)
    # TODO (Slice 5+): hand off request to investigation orchestrator
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

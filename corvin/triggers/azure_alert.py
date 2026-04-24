"""
Azure Monitor alert trigger adapter.

Normalizes Azure Monitor Common Alert Schema payloads into a shared
InvestigationRequest.  This is the primary automated trigger path for V1.

Reference schema:
https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-common-schema
"""

from __future__ import annotations

from typing import Any

from corvin.core.contracts import InvestigationRequest, TriggerSource


def normalize_azure_alert(payload: dict[str, Any]) -> InvestigationRequest:
    """
    Convert an Azure Monitor Common Alert Schema payload into an InvestigationRequest.

    Extracts service name from the first alertTargetID, falls back to the
    alert rule name when target IDs are absent.  The full raw payload is
    preserved so investigators can reference original alert metadata.
    """
    data = payload.get("data", {})
    essentials = data.get("essentials", {})

    target_ids: list[str] = essentials.get("alertTargetIDs", [])
    if target_ids:
        # Use the last path segment of the first target resource ID as a
        # human-readable service name.
        service_name = target_ids[0].rstrip("/").split("/")[-1]
    else:
        service_name = essentials.get("alertRule", "unknown-service")

    description = essentials.get("description") or essentials.get("alertRule", "Azure alert")
    environment = essentials.get("monitoringService", "azure")

    return InvestigationRequest(
        trigger_source=TriggerSource.AZURE_ALERT,
        service_name=service_name,
        environment=environment,
        description=description,
        raw_payload=payload,
    )

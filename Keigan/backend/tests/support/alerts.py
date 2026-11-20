"""Alert webhook helpers: canonical generic payloads and posting with a source's token."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx


@dataclass(frozen=True)
class AlertSourceFixture:
    alert_source_id: str
    webhook_secret: str
    application_id: str


def generic_alert_payload(rule_id: str, status: str = "firing") -> dict[str, object]:
    """A payload in Keigan's canonical generic format (see the setup instructions example)."""
    return {
        "externalId": f"ext-{uuid.uuid4().hex[:8]}",
        "ruleId": rule_id,
        "ruleName": f"Test rule {rule_id}",
        "status": status,
        "severity": 2,
        "resourceRef": "aks-prod-01",
        "service": "claims-api",
        "environment": "prod",
        "startedAt": datetime.now(UTC).isoformat(),
        "summary": "Error rate is 7.4% over 5 minutes",
    }


async def post_alert(client: httpx.AsyncClient, source: AlertSourceFixture, payload: dict[str, object], token: str | None = None) -> httpx.Response:
    return await client.post(
        f"/api/alerts/in/{source.alert_source_id}", json=payload, headers={"X-Keigan-Token": source.webhook_secret if token is None else token}
    )

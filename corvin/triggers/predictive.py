"""Predictive detection heuristics for V3.7."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from corvin.core.contracts import InvestigationResult
from corvin.storage.repository import InvestigationRepository


class PredictiveAlert(BaseModel):
    id: str
    service_name: str
    environment: str
    alert_type: str
    title: str
    summary: str
    severity: str
    confidence: str
    signal_value: float
    threshold_value: float
    estimated_breach_at: datetime | None = None
    rationale: str
    source_request_id: str | None = None
    status: str = "open"
    investigation_request_id: str | None = None
    created_at: datetime = datetime.now(timezone.utc)


class PredictiveMonitor:
    def __init__(self, repo: InvestigationRepository | None = None) -> None:
        self._repo = repo or InvestigationRepository()

    def refresh_alerts(self, limit: int = 20) -> list[PredictiveAlert]:
        results = self._repo.list_recent_results(limit=limit)
        alerts: dict[str, PredictiveAlert] = {}
        for result in results:
            for alert in _alerts_for_result(result):
                alerts[alert.id] = alert

        ordered = sorted(alerts.values(), key=lambda a: (a.severity, a.created_at), reverse=True)
        self._repo.replace_predictive_alerts([alert.model_dump(mode="json") for alert in ordered])
        return ordered

    async def run_forever(self, interval_seconds: int = 300) -> None:
        while True:
            try:
                self.refresh_alerts()
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)


def _alerts_for_result(result: InvestigationResult) -> list[PredictiveAlert]:
    alerts: list[PredictiveAlert] = []
    haystack = " ".join(
        [
            result.request.description,
            result.rca.summary,
            result.rca.root_cause,
            " ".join(result.rca.contributing_factors),
        ]
    ).lower()

    apim_errors = _apim_error_count(result)
    apim_total = len(result.evidence.log_analytics_apim)
    error_ratio = apim_errors / max(apim_total, 1) if apim_total else 0.0
    restart_count = _restart_count(result)

    if any(word in haystack for word in ["memory", "heap", "oom"]):
        alerts.append(
            _make_alert(
                result,
                alert_type="memory_pressure",
                title="Memory trend indicates likely OOM",
                summary="Heap pressure is rising fast enough to justify a pre-mortem investigation before the next restart wave.",
                severity="high",
                confidence=result.rca.confidence.value,
                signal_value=89.0,
                threshold_value=95.0,
                breach_in_hours=4,
                rationale="Recent RCA and trigger context mention memory pressure / heap growth / OOM indicators.",
            )
        )

    if error_ratio >= 0.15 or apim_errors >= 5:
        alerts.append(
            _make_alert(
                result,
                alert_type="error_rate",
                title="Error rate trend is climbing toward customer-visible impact",
                summary="5xx volume is high enough to justify an investigation before the service crosses the next reliability threshold.",
                severity="critical" if error_ratio >= 0.3 else "high",
                confidence=result.rca.confidence.value,
                signal_value=round(error_ratio * 100, 1),
                threshold_value=15.0,
                breach_in_hours=2,
                rationale=f"Observed {apim_errors} 5xx-like APIM events across {apim_total} requests in the captured window.",
            )
        )

    if restart_count >= 3:
        alerts.append(
            _make_alert(
                result,
                alert_type="restart_acceleration",
                title="Pod restart acceleration suggests unstable deployment",
                summary="The restart cadence indicates the service may enter a noisier failure cycle without intervention.",
                severity="medium",
                confidence=result.rca.confidence.value,
                signal_value=float(restart_count),
                threshold_value=3.0,
                breach_in_hours=6,
                rationale=f"AKS context shows {restart_count} recent pod restarts.",
            )
        )

    return alerts


def _make_alert(
    result: InvestigationResult,
    *,
    alert_type: str,
    title: str,
    summary: str,
    severity: str,
    confidence: str,
    signal_value: float,
    threshold_value: float,
    breach_in_hours: int,
    rationale: str,
) -> PredictiveAlert:
    key = f"{result.request.service_name}:{result.request.environment}:{alert_type}"
    alert_id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return PredictiveAlert(
        id=alert_id,
        service_name=result.request.service_name,
        environment=result.request.environment,
        alert_type=alert_type,
        title=title,
        summary=summary,
        severity=severity,
        confidence=confidence,
        signal_value=signal_value,
        threshold_value=threshold_value,
        estimated_breach_at=datetime.now(timezone.utc) + timedelta(hours=breach_in_hours),
        rationale=rationale,
        source_request_id=result.request_id,
        created_at=result.completed_at,
    )


def _apim_error_count(result: InvestigationResult) -> int:
    total = 0
    for row in result.evidence.log_analytics_apim:
        status = row.get("StatusCode", row.get("status_code", row.get("status")))
        try:
            if int(status) >= 500:
                total += 1
        except (TypeError, ValueError):
            if str(status).startswith("5"):
                total += 1
    return total


def _restart_count(result: InvestigationResult) -> int:
    total = 0
    for pod in result.evidence.aks_context.get("pods", []):
        if not isinstance(pod, dict):
            continue
        try:
            total += int(pod.get("restart_count", pod.get("restarts", 0)))
        except (TypeError, ValueError):
            continue
    return total
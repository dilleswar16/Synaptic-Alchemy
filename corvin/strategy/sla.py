"""SLA countdown helpers for V3.7."""

from __future__ import annotations

from pydantic import BaseModel

from corvin.core.contracts import InvestigationResult


class SlaCountdown(BaseModel):
    service_name: str
    environment: str
    sla_target_percent: float
    monthly_budget_seconds: float
    seconds_already_down_this_month: float
    current_error_rate: float
    remaining_budget_seconds: float
    estimated_breach_in_seconds: float | None
    severity: str
    breached: bool


def build_sla_countdown(
    result: InvestigationResult,
    *,
    monthly_downtime_seconds: float,
    policy: dict,
) -> SlaCountdown:
    target_percent = float(policy.get("sla_target_percent", 99.9))
    monthly_minutes = float(policy.get("sla_month_minutes", 30 * 24 * 60))
    monthly_budget_seconds = max(0.0, monthly_minutes * 60 * (1 - target_percent / 100.0))
    error_rate = _error_rate(result)
    remaining_budget = max(0.0, monthly_budget_seconds - monthly_downtime_seconds)

    if remaining_budget <= 0:
        eta = 0.0
        breached = True
    elif error_rate <= 0:
        eta = None
        breached = False
    else:
        eta = remaining_budget / error_rate
        breached = False

    severity = "green"
    if breached or eta == 0:
        severity = "red"
    elif eta is not None and eta <= float(policy.get("sla_red_seconds", 1800)):
        severity = "red"
    elif eta is not None and eta <= float(policy.get("sla_amber_seconds", 7200)):
        severity = "amber"

    return SlaCountdown(
        service_name=result.request.service_name,
        environment=result.request.environment,
        sla_target_percent=target_percent,
        monthly_budget_seconds=round(monthly_budget_seconds, 1),
        seconds_already_down_this_month=round(monthly_downtime_seconds, 1),
        current_error_rate=round(error_rate, 4),
        remaining_budget_seconds=round(remaining_budget, 1),
        estimated_breach_in_seconds=round(eta, 1) if eta is not None else None,
        severity=severity,
        breached=breached,
    )


def _error_rate(result: InvestigationResult) -> float:
    rows = result.evidence.log_analytics_apim
    if not rows:
        return 0.0

    errors = 0
    for row in rows:
        status = row.get("StatusCode", row.get("status_code", row.get("status")))
        try:
            if int(status) >= 500:
                errors += 1
        except (TypeError, ValueError):
            text = str(status).lower()
            if text.startswith("5") or "error" in text:
                errors += 1
    return errors / max(len(rows), 1)
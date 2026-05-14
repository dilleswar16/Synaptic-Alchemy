"""ROI calculator for V3.9 — deterministic, no LLM.

Reads real investigation data from Postgres and computes:
  - incidents handled this month
  - average MTTR with Corvin
  - hours saved vs a configurable baseline
  - cost saved in GBP (or configured currency)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel


class RoiStats(BaseModel):
    period_months: int
    total_incidents: int
    baseline_mttr_minutes: float
    corvin_mttr_minutes: float
    hours_saved: float
    cost_saved: float
    currency: str
    incidents_per_day: float
    mttr_reduction_pct: float


def build_roi_stats(
    investigation_rows: list[dict],
    *,
    policy: dict,
) -> RoiStats:
    """Build ROI stats from a list of investigation summary dicts.

    Each dict must have at least ``created_at`` and ``completed_at`` ISO strings.
    """
    baseline_mttr = float(policy.get("baseline_mttr_minutes", 45))
    hourly_rate   = float(policy.get("engineer_hourly_rate_gbp", 120))
    currency      = str(policy.get("roi_currency", "GBP"))
    period_months = 1

    total = len(investigation_rows)
    if total == 0:
        return RoiStats(
            period_months=period_months,
            total_incidents=0,
            baseline_mttr_minutes=baseline_mttr,
            corvin_mttr_minutes=0.0,
            hours_saved=0.0,
            cost_saved=0.0,
            currency=currency,
            incidents_per_day=0.0,
            mttr_reduction_pct=0.0,
        )

    # Compute average MTTR from real timestamps
    durations: list[float] = []
    for row in investigation_rows:
        try:
            created  = _parse_dt(row["created_at"])
            completed = _parse_dt(row["completed_at"])
            if created and completed and completed > created:
                durations.append((completed - created).total_seconds() / 60.0)
        except (KeyError, TypeError, ValueError):
            pass

    corvin_mttr = sum(durations) / len(durations) if durations else baseline_mttr

    # Time saved per incident vs baseline
    saved_per_incident_hours = max(0.0, (baseline_mttr - corvin_mttr) / 60.0)
    hours_saved = round(saved_per_incident_hours * total, 1)
    cost_saved  = round(hours_saved * hourly_rate, 0)

    reduction_pct = 0.0
    if baseline_mttr > 0:
        reduction_pct = round(max(0.0, (baseline_mttr - corvin_mttr) / baseline_mttr * 100), 1)

    # Days span from oldest to newest
    dates = []
    for row in investigation_rows:
        try:
            dt = _parse_dt(row.get("created_at") or row.get("completed_at"))
            if dt:
                dates.append(dt)
        except (TypeError, ValueError):
            pass
    if len(dates) >= 2:
        span_days = max(1.0, (max(dates) - min(dates)).total_seconds() / 86400)
    else:
        span_days = 30.0
    incidents_per_day = round(total / span_days, 2)

    return RoiStats(
        period_months=period_months,
        total_incidents=total,
        baseline_mttr_minutes=round(baseline_mttr, 1),
        corvin_mttr_minutes=round(corvin_mttr, 1),
        hours_saved=hours_saved,
        cost_saved=cost_saved,
        currency=currency,
        incidents_per_day=incidents_per_day,
        mttr_reduction_pct=reduction_pct,
    )


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None

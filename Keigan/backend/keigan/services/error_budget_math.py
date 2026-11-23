"""The maths of the error budget policy (spec 30, 4.3). Pure functions, no database.

The budget of an SLO is ``(1 - target) x events in its window``. One incident used the share ``bad events during the incident / budget``. With full data coverage the share equals the
fall in "budget remaining" the SLO page shows over the same window. A window that was only partly measured is scaled up to the full window, and below the minimum coverage or volume no
share is stated at all: a wrong number must not block anyone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from keigan.utils.time_utils import floor_to_interval

SAMPLE_INTERVAL_MINUTES = 5  # the SLI measurement grid (slo_service.SAMPLE_INTERVAL_MINUTES)
WINDOWS_PER_DAY = 24 * 60 // SAMPLE_INTERVAL_MINUTES


@dataclass(frozen=True)
class MeasurementTotals:
    good: int
    total: int
    measured_window_count: int  # 5-minute windows that had events

    @property
    def bad(self) -> int:
        return max(0, self.total - self.good)


@dataclass(frozen=True)
class BudgetShare:
    coverage_percent: float
    budget_event_count: float | None
    share_percent: float | None
    insufficient_reason: str | None  # no_budget, coverage or events

    @property
    def is_insufficient(self) -> bool:
        return self.insufficient_reason is not None


def impact_window(*, opened_at: datetime, detected_at: datetime | None, first_alert_at: datetime | None, resolved_at: datetime | None, now: datetime) -> tuple[datetime, datetime]:
    """From the earliest signal Keigan has (bad events before the ticket was opened belong to the incident) to resolution or now, on the 5-minute grid; never empty."""
    start = floor_to_interval(min(moment for moment in (opened_at, detected_at, first_alert_at) if moment is not None), SAMPLE_INTERVAL_MINUTES)
    end = floor_to_interval(resolved_at or now, SAMPLE_INTERVAL_MINUTES)
    return start, max(end, start + timedelta(minutes=SAMPLE_INTERVAL_MINUTES))


def budget_share(
    impact: MeasurementTotals, window: MeasurementTotals, target_percentage: float, window_days: int, *, minimum_coverage_percent: float, minimum_window_events: int,
) -> BudgetShare:
    allowed_ratio = 1 - target_percentage / 100
    coverage = min(100.0, window.measured_window_count / (window_days * WINDOWS_PER_DAY) * 100)
    coverage = round(coverage, 1)
    if allowed_ratio <= 0:
        return BudgetShare(coverage, None, None, "no_budget")
    if coverage < minimum_coverage_percent:
        return BudgetShare(coverage, None, None, "coverage")
    if window.total < max(1, minimum_window_events):
        return BudgetShare(coverage, None, None, "events")
    budget_events = allowed_ratio * window.total * 100 / coverage  # scales a partly measured window up to the full window
    return BudgetShare(coverage, budget_events, round(impact.bad / budget_events * 100, 1), None)


def union_of_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Overlapping or touching windows merged, so the quarter rule counts no time twice."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged

"""Explainable statistics for SLOs and predictive intelligence (robust baselines, burn rates, trends)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ROBUST_Z_SCORE_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data


@dataclass(frozen=True)
class RobustBaseline:
    median: float
    median_absolute_deviation: float

    def robust_z_score(self, observed_value: float) -> float:
        scale = self.median_absolute_deviation * ROBUST_Z_SCORE_SCALE
        if scale == 0:
            return 0.0 if observed_value == self.median else float("inf") if observed_value > self.median else float("-inf")
        return (observed_value - self.median) / scale


def robust_baseline(values: list[float]) -> RobustBaseline | None:
    finite_values = np.array([value for value in values if value is not None and np.isfinite(value)], dtype=float)
    if finite_values.size < 3:
        return None
    median_value = float(np.median(finite_values))
    return RobustBaseline(median=median_value, median_absolute_deviation=float(np.median(np.abs(finite_values - median_value))))


@dataclass(frozen=True)
class LinearTrend:
    slope_per_hour: float
    intercept: float
    r_squared: float

    def hours_until(self, threshold_value: float, current_value: float) -> float | None:
        if self.slope_per_hour <= 0 or current_value >= threshold_value:
            return None
        return (threshold_value - current_value) / self.slope_per_hour


def linear_trend(hours_since_start: list[float], values: list[float]) -> LinearTrend | None:
    if len(values) < 6:
        return None
    x_values = np.array(hours_since_start, dtype=float)
    y_values = np.array(values, dtype=float)
    slope, intercept = np.polyfit(x_values, y_values, 1)
    predicted_values = slope * x_values + intercept
    total_variance = float(np.sum((y_values - y_values.mean()) ** 2)) or 1e-9
    r_squared = 1 - float(np.sum((y_values - predicted_values) ** 2)) / total_variance
    return LinearTrend(float(slope), float(intercept), max(0.0, r_squared))


def availability_ratio(good_event_count: int | float, total_event_count: int | float) -> float | None:
    if not total_event_count:
        return None
    return float(good_event_count) / float(total_event_count)


def burn_rate(good_event_count: float, total_event_count: float, target_percentage: float) -> float | None:
    """How fast the error budget is being consumed: 1.0 = exactly on budget for the whole window."""
    if not total_event_count:
        return None
    allowed_error_ratio = 1 - target_percentage / 100
    if allowed_error_ratio <= 0:
        return None
    observed_error_ratio = 1 - good_event_count / total_event_count
    return observed_error_ratio / allowed_error_ratio


def error_budget_minutes(target_percentage: float, window_days: int) -> float:
    return (1 - target_percentage / 100) * window_days * 24 * 60


PROPOSED_TARGET_LADDER = (99.99, 99.95, 99.9, 99.5, 99.0, 98.0, 95.0)


def propose_availability_target(measured_percentage: float) -> float | None:
    """Highest ladder value at least 0.05 points below what was achieved (realistic on day one)."""
    for candidate_target in PROPOSED_TARGET_LADDER:
        if candidate_target <= measured_percentage - 0.05:
            return candidate_target
    return None


def propose_latency_threshold_milliseconds(measured_p95_milliseconds: float) -> int:
    return int(np.ceil(measured_p95_milliseconds * 1.2 / 50.0) * 50)

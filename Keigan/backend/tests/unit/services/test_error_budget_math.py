"""keigan/services/error_budget_math.py: the share of an SLO's error budget one incident used (spec 30, AC-2, AC-3, AC-4, AC-7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.services.error_budget_math import MeasurementTotals, budget_share, impact_window, union_of_windows

FULL_WINDOW_COUNT = 30 * 288  # every 5-minute window of 30 days measured
LIMITS = dict(minimum_coverage_percent=50.0, minimum_window_events=1000)


def at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


# ── The share ────────────────────────────────────────────────────────────────────────────────────


def test_the_share_is_the_bad_events_over_the_budget_in_events() -> None:
    # 1,000,000 events in the window at 99.9 % allow 1,000 bad events; 340 bad events used 34 %.
    share = budget_share(MeasurementTotals(good=9_660, total=10_000, measured_window_count=10), MeasurementTotals(good=999_000, total=1_000_000, measured_window_count=FULL_WINDOW_COUNT), 99.9, 30, **LIMITS)
    assert share.budget_event_count == pytest.approx(1_000.0) and share.share_percent == 34.0 and share.coverage_percent == 100.0 and not share.is_insufficient


def test_a_partly_measured_window_is_scaled_up_to_the_full_window() -> None:
    half = MeasurementTotals(good=499_500, total=500_000, measured_window_count=FULL_WINDOW_COUNT // 2)
    share = budget_share(MeasurementTotals(good=0, total=100, measured_window_count=1), half, 99.9, 30, **LIMITS)
    assert share.coverage_percent == 50.0 and share.budget_event_count == pytest.approx(1_000.0) and share.share_percent == 10.0


@pytest.mark.parametrize(("window", "reason"), [
    (MeasurementTotals(good=1, total=1_000_000, measured_window_count=FULL_WINDOW_COUNT // 4), "coverage"),
    (MeasurementTotals(good=1, total=999, measured_window_count=FULL_WINDOW_COUNT), "events"),
    (MeasurementTotals(good=0, total=0, measured_window_count=0), "coverage"),
])
def test_too_little_data_states_no_share(window: MeasurementTotals, reason: str) -> None:
    share = budget_share(MeasurementTotals(good=0, total=10, measured_window_count=1), window, 99.9, 30, **LIMITS)
    assert share.is_insufficient and share.share_percent is None and share.budget_event_count is None and share.insufficient_reason == reason


def test_a_target_of_one_hundred_percent_has_no_budget() -> None:
    share = budget_share(MeasurementTotals(good=0, total=10, measured_window_count=1), MeasurementTotals(good=1_000_000, total=1_000_000, measured_window_count=FULL_WINDOW_COUNT), 100.0, 30, **LIMITS)
    assert share.is_insufficient and share.insufficient_reason == "no_budget"


def test_an_incident_with_no_bad_events_used_nothing() -> None:
    share = budget_share(MeasurementTotals(good=500, total=500, measured_window_count=5), MeasurementTotals(good=999_000, total=1_000_000, measured_window_count=FULL_WINDOW_COUNT), 99.9, 30, **LIMITS)
    assert share.share_percent == 0.0


# ── The impact window ────────────────────────────────────────────────────────────────────────────


def test_the_window_starts_at_the_earliest_known_moment_and_ends_at_resolution_on_the_grid() -> None:
    start, end = impact_window(opened_at=at(10, 7), detected_at=at(10, 3), first_alert_at=at(9, 58), resolved_at=at(11, 32), now=at(15))
    assert (start, end) == (at(9, 55), at(11, 30))


def test_an_open_incident_ends_now_and_missing_moments_are_ignored() -> None:
    assert impact_window(opened_at=at(10, 7), detected_at=None, first_alert_at=None, resolved_at=None, now=at(10, 44)) == (at(10, 5), at(10, 40))


def test_the_window_is_never_empty() -> None:
    start, end = impact_window(opened_at=at(10, 7), detected_at=None, first_alert_at=None, resolved_at=at(10, 8), now=at(15))
    assert end - start == timedelta(minutes=5)


# ── The quarter rule counts overlap once ─────────────────────────────────────────────────────────


def test_overlapping_windows_are_merged_so_no_time_is_counted_twice() -> None:
    merged = union_of_windows([(at(10), at(12)), (at(11), at(13)), (at(15), at(16))])
    assert merged == [(at(10), at(13)), (at(15), at(16))]


def test_touching_windows_merge_and_no_windows_give_nothing() -> None:
    assert union_of_windows([(at(10), at(11)), (at(11), at(12))]) == [(at(10), at(12))]
    assert union_of_windows([]) == []

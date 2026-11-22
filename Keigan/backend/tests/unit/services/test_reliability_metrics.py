"""keigan/services/reliability_metrics.py: the maths behind the reliability metrics page (A4). No database, no clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keigan.config.settings import ModelPrice
from keigan.entities.status_values import InvestigationFeedbackVerdict
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.services.reliability_metrics import (
    UsageCall, percentile, resolve_window, summarize, summarize_ai_usage, summarize_durations, summarize_ratings, week_start,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # a Wednesday
MAXIMUM_DAYS = 365


def minutes(count: float) -> timedelta:
    return timedelta(minutes=count)


# ── Percentiles and summaries ──────────────────────────────────────────────────

def test_no_data_gives_a_sample_size_of_zero_and_no_figures_at_all() -> None:
    result = summarize([])
    assert (result.sample_count, result.median, result.p90, result.mean) == (0, None, None, None)


def test_one_data_point_is_its_own_median_and_p90() -> None:
    result = summarize([42])
    assert (result.sample_count, result.median, result.p90, result.mean) == (1, 42, 42, 42)


def test_the_median_of_an_even_count_is_the_mean_of_the_two_middle_values() -> None:
    assert summarize([10, 40, 20, 30]).median == 25


def test_p90_is_interpolated_between_ranks_and_rounded_to_one_decimal() -> None:
    # Ten values 1..10: rank 0.9 * 9 = 8.1, so p90 = 9 + 0.1 * (10 - 9) = 9.1
    assert percentile(list(range(1, 11)), 0.9) == pytest.approx(9.1)
    assert summarize(list(range(1, 11))).p90 == 9.1
    assert summarize([1, 2, 4]).mean == 2.3  # 7 / 3 = 2.333... shown with one decimal


def test_p90_never_exceeds_the_largest_observed_value() -> None:
    assert summarize([5, 5, 1000]).p90 <= 1000


def test_the_input_order_does_not_matter() -> None:
    assert summarize([3, 1, 2]) == summarize([1, 2, 3])


# ── Durations ──────────────────────────────────────────────────────────────────

def test_durations_are_in_seconds_between_start_and_end() -> None:
    summary = summarize_durations([(NOW, NOW + minutes(10)), (NOW, NOW + minutes(30))])
    assert summary.distribution.sample_count == 2
    assert summary.distribution.median == 1200
    assert summary.excluded_count == 0


def test_an_unresolved_incident_has_no_end_and_is_left_out_of_the_resolve_time() -> None:
    summary = summarize_durations([(NOW, None), (NOW, NOW + minutes(5))])
    assert summary.distribution.sample_count == 1
    assert summary.distribution.median == 300
    assert summary.excluded_count == 1


def test_an_incident_without_an_alert_has_no_start_and_is_counted_as_excluded() -> None:
    summary = summarize_durations([(None, NOW), (NOW - minutes(3), NOW)])
    assert summary.distribution.sample_count == 1 and summary.excluded_count == 1


def test_an_end_before_the_start_is_excluded_not_shown_as_a_negative_time() -> None:
    summary = summarize_durations([(NOW, NOW - minutes(1))])
    assert summary.distribution.sample_count == 0 and summary.excluded_count == 1
    assert summary.distribution.median is None


def test_a_zero_second_duration_is_a_real_sample() -> None:
    assert summarize_durations([(NOW, NOW)]).distribution.sample_count == 1


# ── Ratings ────────────────────────────────────────────────────────────────────

CORRECT, PARTIAL, INCORRECT = InvestigationFeedbackVerdict.CORRECT, InvestigationFeedbackVerdict.PARTIALLY_CORRECT, InvestigationFeedbackVerdict.INCORRECT


def test_the_share_marked_correct_is_taken_over_rated_investigations_only() -> None:
    summary = summarize_ratings([CORRECT, CORRECT, CORRECT, PARTIAL, INCORRECT, None, None, None], minimum_sample=5)
    assert (summary.rated_count, summary.correct_count, summary.partially_correct_count, summary.incorrect_count) == (5, 3, 1, 1)
    assert summary.share_correct == 60.0


def test_below_the_minimum_sample_no_percentage_is_given() -> None:
    summary = summarize_ratings([CORRECT, CORRECT, CORRECT, CORRECT], minimum_sample=5)
    assert summary.rated_count == 4 and summary.share_correct is None


def test_exactly_the_minimum_sample_is_enough() -> None:
    assert summarize_ratings([CORRECT] * 4 + [INCORRECT], minimum_sample=5).share_correct == 80.0


def test_no_ratings_at_all_is_zero_rated_and_no_percentage() -> None:
    summary = summarize_ratings([None, None], minimum_sample=1)
    assert summary.rated_count == 0 and summary.share_correct is None


def test_a_minimum_of_one_allows_a_percentage_from_a_single_rating() -> None:
    assert summarize_ratings([INCORRECT], minimum_sample=1).share_correct == 0.0


# ── AI usage and cost ──────────────────────────────────────────────────────────

def call(investigation: str, model: str = "model-a", input_tokens: int = 1000, output_tokens: int = 200, latency: int = 800, failed: bool = False) -> UsageCall:
    return UsageCall(investigation_id=investigation, model_name=model, input_tokens=input_tokens, output_tokens=output_tokens, latency_milliseconds=latency, failed=failed)


def test_tokens_are_added_up_per_investigation_before_the_median_is_taken() -> None:
    calls = [call("i1", input_tokens=1000), call("i1", input_tokens=3000), call("i2", input_tokens=2000)]
    usage = summarize_ai_usage(calls, prices={})
    assert usage.investigation_count == 2 and usage.call_count == 3
    assert usage.input_tokens.sample_count == 2 and usage.input_tokens.median == 3000  # (4000 + 2000) / 2
    assert usage.output_tokens.median == 300  # (400 + 200) / 2


def test_latency_is_per_model_call_and_failures_are_counted() -> None:
    usage = summarize_ai_usage([call("i1", latency=100), call("i1", latency=300, failed=True), call("i2", latency=200)], prices={})
    assert usage.latency_milliseconds.sample_count == 3 and usage.latency_milliseconds.median == 200
    assert usage.failed_call_count == 1


def test_no_usage_is_an_empty_summary_not_an_error() -> None:
    usage = summarize_ai_usage([], prices={})
    assert (usage.investigation_count, usage.call_count, usage.failed_call_count) == (0, 0, 0)
    assert usage.input_tokens.median is None and usage.cost.total is None


def test_without_configured_prices_no_cost_is_estimated() -> None:
    cost = summarize_ai_usage([call("i1")], prices={}).cost
    assert cost.is_configured is False
    assert cost.total is None and cost.per_investigation.sample_count == 0 and cost.unpriced_models == ()


def test_with_a_price_the_cost_is_tokens_times_the_price_per_million() -> None:
    prices = {"model-a": ModelPrice(input_per_million=2.0, output_per_million=10.0)}
    cost = summarize_ai_usage([call("i1", input_tokens=1_000_000, output_tokens=500_000), call("i2", input_tokens=500_000, output_tokens=0)], prices=prices).cost
    assert cost.is_configured is True
    assert cost.per_investigation.sample_count == 2
    assert cost.per_investigation.median == 4.0  # i1 costs 2 + 5 = 7, i2 costs 1: median of 7 and 1 is 4
    assert cost.total == 8.0


def test_an_investigation_that_used_an_unpriced_model_is_left_out_of_the_cost_and_the_model_is_named() -> None:
    prices = {"model-a": ModelPrice(input_per_million=1.0, output_per_million=1.0)}
    calls = [call("i1", model="model-a"), call("i2", model="model-a"), call("i2", model="model-b")]
    cost = summarize_ai_usage(calls, prices=prices).cost
    assert cost.per_investigation.sample_count == 1
    assert cost.unpriced_models == ("model-b",)
    assert cost.unpriced_investigation_count == 1


def test_model_names_are_matched_exactly_not_by_prefix() -> None:
    cost = summarize_ai_usage([call("i1", model="model-a-large")], prices={"model-a": ModelPrice(input_per_million=1.0, output_per_million=1.0)}).cost
    assert cost.per_investigation.sample_count == 0 and cost.unpriced_models == ("model-a-large",)


# ── Weeks and the period ───────────────────────────────────────────────────────

def test_a_week_starts_on_monday_at_midnight_utc() -> None:
    assert week_start(NOW) == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
    assert week_start(datetime(2026, 11, 22, 23, 59, tzinfo=UTC)) == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)  # Sunday
    assert week_start(datetime(2026, 11, 23, 0, 0, tzinfo=UTC)) == datetime(2026, 11, 23, 0, 0, tzinfo=UTC)  # Monday


def test_a_days_window_ends_now_and_starts_that_many_days_earlier() -> None:
    window = resolve_window(days=7, start=None, end=None, now=NOW, maximum_days=MAXIMUM_DAYS)
    assert (window.end, window.start) == (NOW, NOW - timedelta(days=7))


def test_without_any_period_the_default_is_thirty_days() -> None:
    window = resolve_window(days=None, start=None, end=None, now=NOW, maximum_days=MAXIMUM_DAYS)
    assert window.end - window.start == timedelta(days=30)


def test_an_explicit_from_and_to_are_used_as_given() -> None:
    start, end = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 15, tzinfo=UTC)
    window = resolve_window(days=None, start=start, end=end, now=NOW, maximum_days=MAXIMUM_DAYS)
    assert (window.start, window.end) == (start, end)


def test_a_from_without_a_to_runs_until_now() -> None:
    assert resolve_window(days=None, start=NOW - timedelta(days=10), end=None, now=NOW, maximum_days=MAXIMUM_DAYS).end == NOW


@pytest.mark.parametrize(
    "arguments",
    [
        {"days": 0}, {"days": -3}, {"days": MAXIMUM_DAYS + 1},
        {"start": NOW, "end": NOW}, {"start": NOW, "end": NOW - timedelta(days=1)},
        {"start": NOW - timedelta(days=MAXIMUM_DAYS + 1), "end": NOW},
        {"days": 7, "start": NOW - timedelta(days=3)},
        {"end": NOW},
    ],
)
def test_an_invalid_period_is_refused(arguments: dict[str, object]) -> None:
    with pytest.raises(BusinessValidationException):
        resolve_window(**{"days": None, "start": None, "end": None, **arguments}, now=NOW, maximum_days=MAXIMUM_DAYS)  # type: ignore[arg-type]


def test_the_longest_allowed_period_is_accepted() -> None:
    assert resolve_window(days=MAXIMUM_DAYS, start=None, end=None, now=NOW, maximum_days=MAXIMUM_DAYS).start == NOW - timedelta(days=MAXIMUM_DAYS)

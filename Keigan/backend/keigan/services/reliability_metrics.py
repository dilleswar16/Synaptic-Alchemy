"""The maths behind the reliability metrics page (roadmap A4). Pure functions: no database, no clock, no settings.

``ReliabilityMetricsService`` reads the rows and calls these. Everything here is deterministic, so every rule that decides what the page may
claim (what counts as a sample, when a percentage is withheld, when a cost exists) is unit-tested without a database.

Definitions (the page shows the same words; the keys are in ``DEFINITION_KEYS``):

* A duration counts in the period in which it ended. Incidents opened in a period are counted by ``opened_at``, resolved ones by ``resolved_at``.
* Time to detect: the earliest alert (``alert.first_seen_at``, in an alert group linked to the incident) to ``incident.opened_at``. It cannot see when the
  problem really began, only how long a signal existed before an incident did. An incident with no linked alert, or whose first alert came after it
  was opened, has no such time: it is counted as excluded, never guessed.
* Time to first update: ``detected_by_keigan_at`` (when Keigan registered the incident) to ``first_update_sent_at``. Same start as the home page tile.
* Time to resolve (MTTR): ``opened_at`` to ``resolved_at``. An unresolved incident is not in it.
* Time to conclusion: investigation ``started_at`` to ``completed_at``, completed investigations only.
* Median and p90 use linear interpolation between ranks, rounded to one decimal. The sample size n is always carried next to the figure.
* There is no acknowledgement timestamp anywhere in the data, so time to acknowledge is not computed (see ``NOT_AVAILABLE_METRICS``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from keigan.config.settings import ModelPrice
from keigan.entities.status_values import InvestigationFeedbackVerdict
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.utils.time_utils import ensure_utc

MEDIAN_FRACTION = 0.5
P90_FRACTION = 0.9
DEFAULT_WINDOW_DAYS = 30
TOKENS_PER_PRICE_UNIT = 1_000_000
COST_DIGITS = 4

DEFINITION_KEYS = (
    "incidentsOpened", "incidentsResolved", "timeToDetect", "timeToFirstUpdate", "timeToResolve", "timeToConclusion", "investigationStatuses", "ratings",
    "aiTokens", "aiLatency", "aiCalls", "aiCost", "weeklyTrend", "percentiles",
)

# Metrics the page names but cannot compute, with the reason key the page translates.
NOT_AVAILABLE_METRICS = {"timeToAcknowledge": "no_acknowledgement_timestamp"}


@dataclass(frozen=True)
class Distribution:
    sample_count: int
    median: float | None
    p90: float | None
    mean: float | None


@dataclass(frozen=True)
class DurationSummary:
    distribution: Distribution
    # Pairs that could not give a duration: no start (for example an incident with no alert), no end (still open), or an end before the start.
    excluded_count: int


@dataclass(frozen=True)
class RatingSummary:
    rated_count: int
    correct_count: int
    partially_correct_count: int
    incorrect_count: int
    # Percent marked correct among rated investigations; None while fewer than the minimum sample were rated.
    share_correct: float | None


@dataclass(frozen=True)
class UsageCall:
    investigation_id: str
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_milliseconds: int
    failed: bool


@dataclass(frozen=True)
class CostSummary:
    is_configured: bool
    # Estimated cost per investigation, over investigations whose every call used a priced model.
    per_investigation: Distribution
    # Estimated cost of every priced call; None when no price is configured.
    total: float | None
    unpriced_models: tuple[str, ...]
    unpriced_investigation_count: int


@dataclass(frozen=True)
class AiUsageSummary:
    investigation_count: int
    call_count: int
    failed_call_count: int
    input_tokens: Distribution  # per investigation
    output_tokens: Distribution  # per investigation
    latency_milliseconds: Distribution  # per model call
    cost: CostSummary


@dataclass(frozen=True)
class MetricsWindow:
    start: datetime
    end: datetime


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Linear interpolation between the two nearest ranks (the usual "type 7" percentile). None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * (rank - lower_index)


def summarize(values: Iterable[float], digits: int = 1) -> Distribution:
    """Sample size, median, p90 and mean, rounded to ``digits`` decimals (one for seconds and tokens, more for a money amount)."""
    samples = list(values)
    if not samples:
        return Distribution(sample_count=0, median=None, p90=None, mean=None)
    return Distribution(
        sample_count=len(samples), median=round(percentile(samples, MEDIAN_FRACTION) or 0.0, digits), p90=round(percentile(samples, P90_FRACTION) or 0.0, digits),
        mean=round(sum(samples) / len(samples), digits),
    )


def summarize_durations(pairs: Iterable[tuple[datetime | None, datetime | None]]) -> DurationSummary:
    """Seconds from start to end for every usable (start, end) pair; the others are counted, not guessed."""
    seconds: list[float] = []
    excluded = 0
    for start, end in pairs:
        if start is None or end is None or end < start:
            excluded += 1
        else:
            seconds.append((end - start).total_seconds())
    return DurationSummary(distribution=summarize(seconds), excluded_count=excluded)


def summarize_ratings(verdicts: Iterable[str | None], minimum_sample: int) -> RatingSummary:
    """Share marked correct among RATED investigations (a verdict of None is not rated). No percentage below the minimum sample."""
    verdict_list = [verdict for verdict in verdicts if verdict in {item.value for item in InvestigationFeedbackVerdict}]
    correct = verdict_list.count(InvestigationFeedbackVerdict.CORRECT)
    share = round(100 * correct / len(verdict_list), 1) if verdict_list and len(verdict_list) >= minimum_sample else None
    return RatingSummary(
        rated_count=len(verdict_list), correct_count=correct, partially_correct_count=verdict_list.count(InvestigationFeedbackVerdict.PARTIALLY_CORRECT),
        incorrect_count=verdict_list.count(InvestigationFeedbackVerdict.INCORRECT), share_correct=share,
    )


def _call_cost(call: UsageCall, price: ModelPrice) -> float:
    return (call.input_tokens * price.input_per_million + call.output_tokens * price.output_per_million) / TOKENS_PER_PRICE_UNIT


def summarize_ai_usage(calls: Sequence[UsageCall], prices: Mapping[str, ModelPrice]) -> AiUsageSummary:
    """Tokens per investigation, latency per call, failures, and (only for models with a configured price) an estimated cost.

    A model matches a price only by its exact name. An investigation that used any unpriced model is left out of the per-investigation cost, so the
    figure never quietly understates; the unpriced models are named instead.
    """
    by_investigation: dict[str, list[UsageCall]] = defaultdict(list)
    for call in calls:
        by_investigation[call.investigation_id].append(call)
    unpriced_models = sorted({call.model_name for call in calls if call.model_name not in prices}) if prices else []
    costs_per_investigation: list[float] = []
    unpriced_investigations = 0
    if prices:
        for investigation_calls in by_investigation.values():
            if all(call.model_name in prices for call in investigation_calls):
                costs_per_investigation.append(sum(_call_cost(call, prices[call.model_name]) for call in investigation_calls))
            else:
                unpriced_investigations += 1
    return AiUsageSummary(
        investigation_count=len(by_investigation), call_count=len(calls), failed_call_count=sum(1 for call in calls if call.failed),
        input_tokens=summarize(sum(call.input_tokens for call in group) for group in by_investigation.values()),
        output_tokens=summarize(sum(call.output_tokens for call in group) for group in by_investigation.values()),
        latency_milliseconds=summarize(call.latency_milliseconds for call in calls),
        cost=CostSummary(
            is_configured=bool(prices), per_investigation=summarize(costs_per_investigation, COST_DIGITS),
            total=round(sum(_call_cost(call, prices[call.model_name]) for call in calls if call.model_name in prices), COST_DIGITS) if prices else None,
            unpriced_models=tuple(unpriced_models), unpriced_investigation_count=unpriced_investigations,
        ),
    )


def week_start(moment: datetime) -> datetime:
    """Monday 00:00 UTC of the week the moment falls in."""
    utc_moment = ensure_utc(moment) or moment
    return (utc_moment - timedelta(days=utc_moment.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def weeks_in(window: MetricsWindow) -> list[datetime]:
    """The Monday of every week the window touches; the first and last week may be only partly inside it."""
    weeks: list[datetime] = []
    current = week_start(window.start)
    while current < window.end:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


def resolve_window(*, days: int | None, start: datetime | None, end: datetime | None, now: datetime, maximum_days: int) -> MetricsWindow:
    """The period of a request: ``days`` back from now, or an explicit ``from`` (and ``to``, default now). Neither: the default window."""
    if days is not None and (start is not None or end is not None):
        raise BusinessValidationException("Use either days or from and to, not both.")
    if end is not None and start is None:
        raise BusinessValidationException("A to date needs a from date.")
    if start is None:
        window_days = DEFAULT_WINDOW_DAYS if days is None else days
        if window_days < 1 or window_days > maximum_days:
            raise BusinessValidationException(f"Days must be between 1 and {maximum_days}.")
        return MetricsWindow(start=now - timedelta(days=window_days), end=now)
    window = MetricsWindow(start=ensure_utc(start) or start, end=now if end is None else ensure_utc(end) or end)
    if window.end <= window.start:
        raise BusinessValidationException("The period must end after it starts.")
    if window.end - window.start > timedelta(days=maximum_days):
        raise BusinessValidationException(f"The period can be at most {maximum_days} days.")
    return window

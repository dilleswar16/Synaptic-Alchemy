"""Reliability metrics page DTOs. Every figure travels with its sample size; a figure that could not be computed is null, never zero."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from keigan.dtos.common_dtos import ApiModel


class StatResponse(ApiModel):
    """Median, p90 and mean of ``sample_count`` values. All three are null when there are no samples."""

    sample_count: int
    median: float | None = None
    p90: float | None = None
    mean: float | None = None
    # How many items could not give a value (no start, no end, or an end before the start). Only durations fill it.
    excluded_count: int = 0


class PriorityCountResponse(ApiModel):
    priority: str  # P1 to P4, or "unassigned" when the incident has no Keigan priority
    opened_count: int
    resolved_count: int


class InvestigationStatusCountResponse(ApiModel):
    status: str
    count: int


class RatingsResponse(ApiModel):
    rated_count: int
    correct_count: int
    partially_correct_count: int
    incorrect_count: int
    minimum_sample: int
    # Percent marked correct among rated investigations; null while fewer than minimum_sample were rated.
    share_correct: float | None = None


class MemoryMetricsResponse(ApiModel):
    """How the memory of past incidents (spec 34) is used and judged in the period."""

    completed_investigation_count: int
    investigations_given_a_hint_count: int  # completed investigations whose AI was shown at least one confirmed past incident
    relevance_answer_count: int
    relevant_count: int
    not_relevant_count: int
    minimum_sample: int
    # Percent of answers that said "relevant"; null while fewer than minimum_sample answers were given.
    share_relevant: float | None = None
    hidden_entry_count: int  # past incidents an admin hid in the period


class KeiganHelpCountResponse(ApiModel):
    answer: str  # an IncidentKeiganHelp value
    count: int


class KeiganHelpMetricsResponse(ApiModel):
    """What the people who resolved incidents in the period said about how far Keigan's analysis helped. A person's answer, so it is shown with how many answered."""

    resolved_count: int
    answered_count: int
    answers: list[KeiganHelpCountResponse]
    minimum_sample: int
    # Percent of answers that said "found the cause"; null while fewer than minimum_sample answers were given.
    share_found_cause: float | None = None
    # Time to resolve for incidents answered "found the cause" or "helped partly" against those answered "did not help" or "not used"; each has its own sample size.
    time_to_resolve_with_help: StatResponse
    time_to_resolve_without_help: StatResponse


class CostResponse(ApiModel):
    is_configured: bool
    total_estimated_cost: float | None = None
    per_investigation: StatResponse
    unpriced_models: list[str] = Field(default_factory=list)
    unpriced_investigation_count: int = 0


class AiUsageResponse(ApiModel):
    investigation_count: int
    call_count: int
    failed_call_count: int
    input_tokens: StatResponse  # per investigation
    output_tokens: StatResponse  # per investigation
    latency_milliseconds: StatResponse  # per model call
    cost: CostResponse


class MetricsSummaryResponse(ApiModel):
    incidents_opened_count: int
    incidents_resolved_count: int
    by_priority: list[PriorityCountResponse]
    time_to_detect: StatResponse
    time_to_first_update: StatResponse
    time_to_resolve: StatResponse
    time_to_conclusion: StatResponse
    investigation_count: int
    investigations_by_status: list[InvestigationStatusCountResponse]
    ratings: RatingsResponse
    memory: MemoryMetricsResponse
    keigan_help: KeiganHelpMetricsResponse
    ai_usage: AiUsageResponse


class ApplicationMetricsResponse(MetricsSummaryResponse):
    application_id: str
    application_name: str
    application_code: str


class WeeklyPointResponse(ApiModel):
    week_start: datetime  # Monday 00:00 UTC; the first and last week of the period may be only partly inside it
    incidents_opened_count: int
    incidents_resolved_count: int
    time_to_resolve: StatResponse
    time_to_conclusion: StatResponse
    tokens_per_investigation: StatResponse  # input plus output tokens, per investigation


class NotAvailableMetricResponse(ApiModel):
    metric: str
    reason: str  # a key the page translates


class MetricsOverviewResponse(ApiModel):
    period_start: datetime
    period_end: datetime
    application_id: str | None = None
    minimum_rating_sample: int
    maximum_window_days: int
    summary: MetricsSummaryResponse
    applications: list[ApplicationMetricsResponse]
    weekly_trend: list[WeeklyPointResponse]
    not_available: list[NotAvailableMetricResponse]
    definition_keys: list[str]
    generated_at: datetime

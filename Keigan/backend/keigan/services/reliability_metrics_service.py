"""Reliability metrics page: reads incidents, investigations, alerts and AI usage in a period, and hands them to ``reliability_metrics`` for the maths."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.metrics_dtos import (
    AiUsageResponse, ApplicationMetricsResponse, CostResponse, InvestigationStatusCountResponse, KeiganHelpCountResponse, KeiganHelpMetricsResponse, MemoryMetricsResponse, MetricsOverviewResponse, MetricsSummaryResponse, NotAvailableMetricResponse,
    PriorityCountResponse, RatingsResponse, StatResponse, WeeklyPointResponse,
)
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Incident, Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryRelevanceFeedback, InvestigationMemoryReference
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.entities.status_values import IncidentKeiganHelp, IncidentMemoryRelevanceVerdict, InvestigationStatus, LlmCallOutcome, Priority
from keigan.security.current_user import CurrentUser
from keigan.services.authorization_service import AuthorizationService
from keigan.services.reliability_metrics import (
    DEFINITION_KEYS, NOT_AVAILABLE_METRICS, Distribution, MetricsWindow, UsageCall, resolve_window, summarize, summarize_ai_usage, summarize_durations, summarize_ratings,
    week_start, weeks_in,
)
from keigan.utils.time_utils import utc_now

UNASSIGNED_PRIORITY = "unassigned"
PRIORITY_ORDER = (*(priority.value for priority in Priority), UNASSIGNED_PRIORITY)
COMPLETED_INVESTIGATION_STATUSES = (InvestigationStatus.COMPLETED, InvestigationStatus.COMPLETED_EVIDENCE_ONLY)


@dataclass(frozen=True)
class IncidentRow:
    incident_id: str
    application_id: str
    priority: str
    opened_at: datetime
    detected_by_keigan_at: datetime
    first_update_sent_at: datetime | None
    resolved_at: datetime | None
    first_alert_at: datetime | None  # earliest alert in an alert group linked to the incident
    keigan_help: str | None = None  # the resolver's answer to "how did Keigan's analysis help?"


@dataclass(frozen=True)
class InvestigationRow:
    investigation_id: str
    application_id: str
    status: str
    verdict: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class MemoryRows:
    given_a_hint: frozenset[str]  # investigation ids whose AI was shown a past incident
    answers: list[tuple[str, str]]  # (application id, verdict) of each "relevant" or "not relevant" answer in the period
    hidden_application_ids: list[str]  # the application of each past incident hidden in the period

    def for_application(self, application_id: str, investigation_ids: Iterable[str]) -> MemoryRows:
        return MemoryRows(
            self.given_a_hint & frozenset(investigation_ids), [answer for answer in self.answers if answer[0] == application_id], [item for item in self.hidden_application_ids if item == application_id],
        )


@dataclass(frozen=True)
class CallRow:
    application_id: str
    investigation_created_at: datetime
    call: UsageCall


def _stat(distribution: Distribution, excluded_count: int = 0) -> StatResponse:
    return StatResponse(sample_count=distribution.sample_count, median=distribution.median, p90=distribution.p90, mean=distribution.mean, excluded_count=excluded_count)


class ReliabilityMetricsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def overview(self, current_user: CurrentUser, application_id: str | None, days: int | None, start: datetime | None, end: datetime | None) -> MetricsOverviewResponse:
        now = utc_now()
        window = resolve_window(days=days, start=start, end=end, now=now, maximum_days=self.settings.metrics_maximum_window_days)
        authorization = AuthorizationService(self.session)
        if application_id is not None:
            await authorization.ensure_application_reader(current_user, application_id)
        application_ids = await authorization.scoped_application_ids(current_user, [application_id] if application_id else None)
        applications = list((await self.session.scalars(select(Application).where(Application.application_id.in_(application_ids)).order_by(Application.application_name))).all()) if application_ids else []
        incidents = await self._incidents(application_ids, window) if application_ids else []
        investigations = await self._investigations(application_ids, window) if application_ids else []
        calls = await self._calls(application_ids, window) if application_ids else []
        memory = await self._memory_rows(application_ids, window, investigations) if application_ids else MemoryRows(frozenset(), [], [])
        return MetricsOverviewResponse(
            period_start=window.start, period_end=window.end, application_id=application_id, minimum_rating_sample=self.settings.metrics_minimum_rating_sample,
            maximum_window_days=self.settings.metrics_maximum_window_days, summary=self._summarize(incidents, investigations, calls, window, memory),
            applications=[
                ApplicationMetricsResponse(
                    application_id=application.application_id, application_name=application.application_name, application_code=application.application_code,
                    **self._summarize(
                        [row for row in incidents if row.application_id == application.application_id], [row for row in investigations if row.application_id == application.application_id],
                        [row for row in calls if row.application_id == application.application_id], window,
                        memory.for_application(application.application_id, (row.investigation_id for row in investigations if row.application_id == application.application_id)),
                    ).model_dump(),
                )
                for application in applications
            ],
            weekly_trend=self._weekly_trend(incidents, investigations, calls, window),
            not_available=[NotAvailableMetricResponse(metric=metric, reason=reason) for metric, reason in NOT_AVAILABLE_METRICS.items()],
            definition_keys=list(DEFINITION_KEYS), generated_at=now,
        )

    # ── Reading ────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _incidents(self, application_ids: list[str], window: MetricsWindow) -> list[IncidentRow]:
        """Incidents that were opened, got their first update or were resolved in the period, with the earliest alert of those opened in it."""
        in_scope = Incident.application_id.in_(application_ids)
        rows = (await self.session.execute(select(
            Incident.incident_id, Incident.application_id, Incident.keigan_priority, Incident.opened_at, Incident.detected_by_keigan_at, Incident.first_update_sent_at, Incident.resolved_at, Incident.keigan_help).where(
            in_scope, (Incident.opened_at >= window.start) & (Incident.opened_at < window.end) | (Incident.resolved_at >= window.start) & (Incident.resolved_at < window.end)
            | (Incident.first_update_sent_at >= window.start) & (Incident.first_update_sent_at < window.end)))).all()
        first_alerts = dict((await self.session.execute(
            select(AlertGroup.incident_id, func.min(Alert.first_seen_at)).join(Alert, Alert.alert_group_id == AlertGroup.alert_group_id).join(Incident, Incident.incident_id == AlertGroup.incident_id).where(
                in_scope, Incident.opened_at >= window.start, Incident.opened_at < window.end).group_by(AlertGroup.incident_id))).all())
        return [
            IncidentRow(row.incident_id, row.application_id, row.keigan_priority or UNASSIGNED_PRIORITY, row.opened_at, row.detected_by_keigan_at, row.first_update_sent_at, row.resolved_at,
                        first_alerts.get(row.incident_id), row.keigan_help)
            for row in rows
        ]

    async def _investigations(self, application_ids: list[str], window: MetricsWindow) -> list[InvestigationRow]:
        rows = (await self.session.execute(select(
            Investigation.investigation_id, Investigation.application_id, Investigation.investigation_status, Investigation.user_feedback_verdict, Investigation.created_at,
            Investigation.started_at, Investigation.completed_at).where(
            Investigation.application_id.in_(application_ids), (Investigation.created_at >= window.start) & (Investigation.created_at < window.end)
            | (Investigation.completed_at >= window.start) & (Investigation.completed_at < window.end)))).all()
        return [InvestigationRow(*row) for row in rows]

    async def _memory_rows(self, application_ids: list[str], window: MetricsWindow, investigations: list[InvestigationRow]) -> MemoryRows:
        """What the memory of past incidents did in the period: which investigations were given a hint, how people answered "was this relevant?", and which entries an admin hid."""
        investigation_ids = [row.investigation_id for row in investigations]
        given = frozenset((await self.session.scalars(select(InvestigationMemoryReference.investigation_id).where(InvestigationMemoryReference.investigation_id.in_(investigation_ids)))).all()) if investigation_ids else frozenset()
        answers = (await self.session.execute(
            select(Investigation.application_id, IncidentMemoryRelevanceFeedback.relevance_verdict)
            .join(Investigation, Investigation.investigation_id == IncidentMemoryRelevanceFeedback.investigation_id)
            .where(Investigation.application_id.in_(application_ids), IncidentMemoryRelevanceFeedback.recorded_at >= window.start, IncidentMemoryRelevanceFeedback.recorded_at < window.end)
        )).all()
        hidden = (await self.session.scalars(
            select(IncidentMemoryEntry.application_id).where(IncidentMemoryEntry.application_id.in_(application_ids), IncidentMemoryEntry.hidden_at >= window.start, IncidentMemoryEntry.hidden_at < window.end)
        )).all()
        return MemoryRows(given, [(application_id, verdict) for application_id, verdict in answers], list(hidden))

    def _memory(self, memory: MemoryRows, concluded: list[InvestigationRow]) -> MemoryMetricsResponse:
        completed = [row for row in concluded if row.status == InvestigationStatus.COMPLETED]
        relevant = sum(1 for _, verdict in memory.answers if verdict == IncidentMemoryRelevanceVerdict.RELEVANT)
        answered = len(memory.answers)
        minimum = self.settings.metrics_minimum_rating_sample
        return MemoryMetricsResponse(
            completed_investigation_count=len(completed), investigations_given_a_hint_count=sum(1 for row in completed if row.investigation_id in memory.given_a_hint), relevance_answer_count=answered,
            relevant_count=relevant, not_relevant_count=answered - relevant, minimum_sample=minimum, share_relevant=round(100 * relevant / answered, 1) if answered >= minimum and answered else None,
            hidden_entry_count=len(memory.hidden_application_ids),
        )

    async def _calls(self, application_ids: list[str], window: MetricsWindow) -> list[CallRow]:
        """Model calls made for investigations created in the period (calls with no investigation, such as chat, are not part of this page)."""
        rows = (await self.session.execute(select(
            Investigation.application_id, Investigation.created_at, LlmUsageRecord.investigation_id, LlmUsageRecord.model_name, LlmUsageRecord.input_token_count, LlmUsageRecord.output_token_count,
            LlmUsageRecord.latency_milliseconds, LlmUsageRecord.outcome_status).join(Investigation, Investigation.investigation_id == LlmUsageRecord.investigation_id).where(
            Investigation.application_id.in_(application_ids), Investigation.created_at >= window.start, Investigation.created_at < window.end))).all()
        return [
            CallRow(row.application_id, row.created_at, UsageCall(row.investigation_id, row.model_name, row.input_token_count or 0, row.output_token_count or 0, row.latency_milliseconds or 0,
                                                                  row.outcome_status == LlmCallOutcome.FAILED))
            for row in rows
        ]

    # ── Summaries ──────────────────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _in(window: MetricsWindow, moment: datetime | None) -> bool:
        return moment is not None and window.start <= moment < window.end

    def _summarize(self, incidents: list[IncidentRow], investigations: list[InvestigationRow], calls: list[CallRow], window: MetricsWindow, memory: MemoryRows) -> MetricsSummaryResponse:
        """Every figure for one set of rows (all applications, or one). A duration counts in the period in which it ended."""
        opened = [row for row in incidents if self._in(window, row.opened_at)]
        resolved = [row for row in incidents if self._in(window, row.resolved_at)]
        created = [row for row in investigations if self._in(window, row.created_at)]
        concluded = [row for row in investigations if row.status in COMPLETED_INVESTIGATION_STATUSES and self._in(window, row.completed_at)]
        detect = summarize_durations((row.first_alert_at, row.opened_at) for row in opened)
        first_update = summarize_durations((row.detected_by_keigan_at, row.first_update_sent_at) for row in incidents if self._in(window, row.first_update_sent_at))
        resolve = summarize_durations((row.opened_at, row.resolved_at) for row in resolved)
        conclude = summarize_durations((row.started_at, row.completed_at) for row in concluded)
        ratings = summarize_ratings((row.verdict for row in created), self.settings.metrics_minimum_rating_sample)
        status_counts = defaultdict(int, {status.value: 0 for status in InvestigationStatus})
        for row in created:
            status_counts[row.status] += 1
        return MetricsSummaryResponse(
            incidents_opened_count=len(opened), incidents_resolved_count=len(resolved),
            by_priority=[
                PriorityCountResponse(priority=priority, opened_count=sum(1 for row in opened if row.priority == priority), resolved_count=sum(1 for row in resolved if row.priority == priority))
                for priority in PRIORITY_ORDER
            ],
            time_to_detect=_stat(detect.distribution, detect.excluded_count), time_to_first_update=_stat(first_update.distribution, first_update.excluded_count),
            time_to_resolve=_stat(resolve.distribution, resolve.excluded_count), time_to_conclusion=_stat(conclude.distribution, conclude.excluded_count), investigation_count=len(created),
            investigations_by_status=[InvestigationStatusCountResponse(status=status, count=count) for status, count in status_counts.items()],
            ratings=RatingsResponse(
                rated_count=ratings.rated_count, correct_count=ratings.correct_count, partially_correct_count=ratings.partially_correct_count, incorrect_count=ratings.incorrect_count,
                minimum_sample=self.settings.metrics_minimum_rating_sample, share_correct=ratings.share_correct),
            memory=self._memory(memory, concluded),
            keigan_help=self._keigan_help(resolved),
            ai_usage=self._ai_usage(calls),
        )

    def _keigan_help(self, resolved: list[IncidentRow]) -> KeiganHelpMetricsResponse:
        """The resolvers' answers for incidents resolved in the period, and how long those incidents took to resolve with and without Keigan's help."""
        answered = [row for row in resolved if row.keigan_help]
        with_help = {IncidentKeiganHelp.FOUND_CAUSE, IncidentKeiganHelp.HELPED_PARTLY}
        without_help = {IncidentKeiganHelp.DID_NOT_HELP, IncidentKeiganHelp.NOT_USED}
        found = sum(1 for row in answered if row.keigan_help == IncidentKeiganHelp.FOUND_CAUSE)
        minimum = self.settings.metrics_minimum_rating_sample
        helped, unhelped = (summarize_durations((row.opened_at, row.resolved_at) for row in answered if row.keigan_help in answers) for answers in (with_help, without_help))
        return KeiganHelpMetricsResponse(
            resolved_count=len(resolved), answered_count=len(answered), answers=[KeiganHelpCountResponse(answer=answer.value, count=sum(1 for row in answered if row.keigan_help == answer)) for answer in IncidentKeiganHelp],
            minimum_sample=minimum, share_found_cause=round(100 * found / len(answered), 1) if len(answered) >= minimum else None,
            time_to_resolve_with_help=_stat(helped.distribution, helped.excluded_count), time_to_resolve_without_help=_stat(unhelped.distribution, unhelped.excluded_count),
        )

    def _ai_usage(self, calls: Iterable[CallRow]) -> AiUsageResponse:
        usage = summarize_ai_usage([row.call for row in calls], self.settings.llm_model_prices)
        return AiUsageResponse(
            investigation_count=usage.investigation_count, call_count=usage.call_count, failed_call_count=usage.failed_call_count, input_tokens=_stat(usage.input_tokens),
            output_tokens=_stat(usage.output_tokens), latency_milliseconds=_stat(usage.latency_milliseconds),
            cost=CostResponse(
                is_configured=usage.cost.is_configured, total_estimated_cost=usage.cost.total, per_investigation=_stat(usage.cost.per_investigation),
                unpriced_models=list(usage.cost.unpriced_models), unpriced_investigation_count=usage.cost.unpriced_investigation_count),
        )

    def _weekly_trend(self, incidents: list[IncidentRow], investigations: list[InvestigationRow], calls: list[CallRow], window: MetricsWindow) -> list[WeeklyPointResponse]:
        def by_week(rows: Iterable, moment_of: Callable[[object], datetime | None]) -> dict[datetime, list]:
            grouped: dict[datetime, list] = defaultdict(list)
            for row in rows:
                moment = moment_of(row)
                if self._in(window, moment):
                    grouped[week_start(moment)].append(row)  # type: ignore[arg-type]
            return grouped

        opened = by_week(incidents, lambda row: row.opened_at)  # type: ignore[attr-defined]
        resolved = by_week(incidents, lambda row: row.resolved_at)  # type: ignore[attr-defined]
        concluded = by_week((row for row in investigations if row.status in COMPLETED_INVESTIGATION_STATUSES), lambda row: row.completed_at)  # type: ignore[attr-defined]
        tokens_by_investigation: dict[datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in calls:
            tokens_by_investigation[week_start(row.investigation_created_at)][row.call.investigation_id] += row.call.input_tokens + row.call.output_tokens
        return [
            WeeklyPointResponse(
                week_start=week, incidents_opened_count=len(opened.get(week, [])), incidents_resolved_count=len(resolved.get(week, [])),
                time_to_resolve=self._duration_stat((row.opened_at, row.resolved_at) for row in resolved.get(week, [])),
                time_to_conclusion=self._duration_stat((row.started_at, row.completed_at) for row in concluded.get(week, [])),
                tokens_per_investigation=_stat(summarize(tokens_by_investigation.get(week, {}).values())))
            for week in weeks_in(window)
        ]

    @staticmethod
    def _duration_stat(pairs: Iterable[tuple[datetime | None, datetime | None]]) -> StatResponse:
        summary = summarize_durations(pairs)
        return _stat(summary.distribution, summary.excluded_count)

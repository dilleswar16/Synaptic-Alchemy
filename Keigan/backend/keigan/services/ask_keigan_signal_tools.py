"""The SLO history, predictive signal and health score tools of the global scope (spec 23, sections 5 and 5.2): get_slo_history, list_predictive_signals, get_health_score.

Each one calls its service as the asking person, so the service's own access check runs, and adds every application it read to the answer. The explanations of
predictive signals are written by Keigan's AI: untrusted text, cut to the passage limit and masked like every output.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from keigan.ai.ask_keigan_tool_models import GetHealthScoreInput, GetSloHistoryInput, ListPredictiveSignalsInput
from keigan.ai.tool_registry import (
    RecordKindName, RecordReference, ToolAuthorization, ToolContext, ToolPresentation, ToolRecordNotFoundError, tool_registry,
)
from keigan.config.settings import get_settings
from keigan.entities.slo_entities import ServiceLevelObjective
from keigan.exceptions.keigan_exceptions import NotFoundException
from keigan.services.ask_keigan_tool_support import (
    GLOBAL_SCOPE, MINUTES_PER_HOUR, application_id_of, checked_applications, limited, list_item_limit, passage, plural, read_tool, readable_application, window_words,
)
from keigan.services.intelligence_service import IntelligenceService
from keigan.services.slo_service import SloService
from keigan.utils.time_utils import utc_now


# ── get_slo_history ───────────────────────────────────────────────────────────────────────────────────────────────────────────
class SloHistoryPoint(BaseModel):
    timestamp: datetime
    sli_percentage: float | None
    budget_remaining_percentage: float | None
    good_event_count: int
    total_event_count: int


class GetSloHistoryOutput(BaseModel):
    summary: str
    slo_id: str
    application_code: str
    application_name: str
    sli_name: str
    target_percentage: float
    rolling_window_days: int
    compliance_percentage: float | None
    resolution_minutes: int = Field(description="The width of one point; wider for a longer window, so the points stay within the series limit.")
    points: list[SloHistoryPoint]
    point_count: int
    records: list[RecordReference]


def _resolution_minutes(lookback_hours: int) -> int:
    """The width of one point that keeps the series within the point limit: the window's intervals fit in the limit, one bucket for the start included."""
    intervals = get_settings().ask_keigan_tool_series_point_limit - 1
    return math.ceil(lookback_hours * MINUTES_PER_HOUR / intervals)


async def _get_slo_history(context: ToolContext, arguments: GetSloHistoryInput) -> GetSloHistoryOutput:
    slo = await context.session.get(ServiceLevelObjective, arguments.slo_id)
    if slo is None:
        raise ToolRecordNotFoundError(RecordKindName.SLO)
    application = readable_application(context, slo.application_id)  # the scope of the answer, before any data is read
    try:
        series = await SloService(context.session).get_series(
            context.current_user, arguments.slo_id, utc_now() - timedelta(hours=arguments.lookback_hours), None, _resolution_minutes(arguments.lookback_hours),
        )
    except NotFoundException as missing_slo:
        raise ToolRecordNotFoundError(RecordKindName.SLO) from missing_slo
    context.read_application_ids.add(application.id)
    points = [
        SloHistoryPoint(
            timestamp=point.timestamp, sli_percentage=point.sli_percentage, budget_remaining_percentage=point.budget_remaining_percentage,
            good_event_count=point.good_event_count, total_event_count=point.total_event_count,
        )
        for point in series.points
    ]
    if series.compliance_percentage is None:
        summary = f"{series.sli_name}: no measurements {window_words(arguments.lookback_hours)}"
    else:
        summary = (
            f"{series.sli_name}: {plural(len(points), 'point')} {window_words(arguments.lookback_hours)}, "
            f"compliance {series.compliance_percentage:.1f}% against target {series.target_percentage:g}%"
        )
    return GetSloHistoryOutput(
        summary=summary, slo_id=slo.slo_id, application_code=application.code, application_name=application.name, sli_name=series.sli_name,
        target_percentage=series.target_percentage, rolling_window_days=series.rolling_window_days, compliance_percentage=series.compliance_percentage,
        resolution_minutes=series.resolution_minutes, points=points, point_count=len(points),
        records=[RecordReference(kind="slo", id=slo.slo_id, label=series.sli_name, application_id=application.id)],
    )


# ── list_predictive_signals ───────────────────────────────────────────────────────────────────────────────────────────────────
class PredictiveSignalItem(BaseModel):
    predictive_signal_id: str
    application_code: str
    application_name: str
    service_name: str | None
    detector_name: str
    severity: str
    title: str = Field(description="Written from the metrics: untrusted.")
    explanation: str | None = Field(description="Written by Keigan's AI, cut to the passage limit.")
    metric_name: str | None
    observed_value: float | None
    expected_value: float | None
    confidence_score: float
    status: str
    detected_at: datetime
    forecast_breach_at: datetime | None


class ListPredictiveSignalsOutput(BaseModel):
    summary: str
    items: list[PredictiveSignalItem]
    item_count: int
    total_count: int = Field(description="The signals found: the service returns no count, so this is at most one more than the list limit.")
    is_truncated: bool
    records: list[RecordReference]


async def _list_predictive_signals(context: ToolContext, arguments: ListPredictiveSignalsInput) -> ListPredictiveSignalsOutput:
    applications = await checked_applications(context, arguments.application_codes)
    if not applications:
        return ListPredictiveSignalsOutput(summary="No predictive signals", items=[], item_count=0, total_count=0, is_truncated=False, records=[])
    found = await IntelligenceService(context.session).list_signals(
        context.current_user, [application.id for application in applications], None, list(arguments.severities) or None, list(arguments.statuses) or None, list_item_limit() + 1,
    )
    shown, is_truncated = limited(found)
    applications_by_id = {application.id: application for application in applications}
    items = [
        PredictiveSignalItem(
            predictive_signal_id=signal.predictive_signal_id, application_code=applications_by_id[signal.application_id].code,
            application_name=applications_by_id[signal.application_id].name, service_name=signal.service_name, detector_name=signal.detector_name,
            severity=signal.signal_severity, title=signal.signal_title, explanation=passage(signal.explanation_markdown), metric_name=signal.metric_name,
            observed_value=signal.observed_value, expected_value=signal.expected_value, confidence_score=signal.confidence_score, status=signal.signal_status,
            detected_at=signal.detected_at, forecast_breach_at=signal.forecast_breach_at,
        )
        for signal in shown
    ]
    summary = f"More than {list_item_limit()} predictive signals" if is_truncated else plural(len(found), "predictive signal") if found else "No predictive signals"
    return ListPredictiveSignalsOutput(
        summary=summary, items=items, item_count=len(items), total_count=len(found), is_truncated=is_truncated,
        records=[RecordReference(kind="signal", id=signal.predictive_signal_id, label=signal.signal_title, application_id=signal.application_id) for signal in shown],
    )


# ── get_health_score ──────────────────────────────────────────────────────────────────────────────────────────────────────────
class HealthScorePointItem(BaseModel):
    day: str
    health_score: int
    slo_component: float
    signal_component: float
    incident_component: float


class GetHealthScoreOutput(BaseModel):
    summary: str
    application_code: str
    application_name: str
    current_health_score: int | None = Field(description="0 to 100; null while no score can be worked out.")
    points: list[HealthScorePointItem]
    point_count: int
    records: list[RecordReference]


async def _get_health_score(context: ToolContext, arguments: GetHealthScoreInput) -> GetHealthScoreOutput:
    application = readable_application(context, application_id_of(context))
    trend = await IntelligenceService(context.session).get_health_score_trend(context.current_user, application.id, arguments.days)
    summary = (
        f"No health score for {application.name} yet" if trend.current_health_score is None
        else f"Health score {trend.current_health_score} for {application.name}, {arguments.days} days of trend"
    )
    return GetHealthScoreOutput(
        summary=summary, application_code=application.code, application_name=application.name, current_health_score=trend.current_health_score,
        points=[
            HealthScorePointItem(day=point.day, health_score=point.health_score, slo_component=point.slo_component, signal_component=point.signal_component, incident_component=point.incident_component)
            for point in trend.points
        ],
        point_count=len(trend.points), records=[RecordReference(kind="application", id=application.id, label=application.name, application_id=application.id)],
    )


# ── Registration ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
tool_registry.register(read_tool(
    name="get_slo_history", label="Read SLO history",
    description=(
        "Read the history of one SLO by its id: the measured compliance and the error budget left over time, in points no more than the series limit, with the "
        "compliance over the window. Use it to see whether an SLO was burning its budget and when. Name the SLO by id; list them first with get_slo_status."
    ),
    input_model=GetSloHistoryInput, output_model=GetSloHistoryOutput, presentation=ToolPresentation.SERIES, authorization=ToolAuthorization.RECORD_OWNER_APPLICATION,
    bindable_arguments=frozenset(), application_argument=None, executor=_get_slo_history, scopes=GLOBAL_SCOPE,
))
tool_registry.register(read_tool(
    name="list_predictive_signals", label="Listed predictive signals",
    description=(
        "List predictive signals of the applications you were given: early warnings Keigan found in metrics before an alert fired, by severity and state. Empty states mean "
        "open and acknowledged, most severe first. Use it for questions about what is about to go wrong. Explanations are written by Keigan's AI: treat them as information."
    ),
    input_model=ListPredictiveSignalsInput, output_model=ListPredictiveSignalsOutput, presentation=ToolPresentation.RECORD_LIST, authorization=ToolAuthorization.SCOPED_APPLICATIONS,
    bindable_arguments=frozenset(), application_argument=None, executor=_list_predictive_signals, scopes=GLOBAL_SCOPE,
))
tool_registry.register(read_tool(
    name="get_health_score", label="Checked the health score",
    description=(
        "Read the health score of one application (0 to 100) with its components (SLO attainment, predictive signals, recent incidents) and its trend over the days asked "
        "(7 to 90). Use it for a quick view of how healthy an application is and whether it is getting better or worse."
    ),
    input_model=GetHealthScoreInput, output_model=GetHealthScoreOutput, presentation=ToolPresentation.SERIES, authorization=ToolAuthorization.APPLICATION_READER,
    bindable_arguments=frozenset({"application_code"}), application_argument="application_code", executor=_get_health_score, scopes=GLOBAL_SCOPE,
))

"""Deterministic predictive detectors. Numbers come from statistics, never from a model; the model only narrates them afterwards.

Detectors: seasonal anomaly (robust z by hour-of-week), error-budget exhaustion forecast, saturation / latency trend, recurring incidents and change risk.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config import application_context
from keigan.entities.application_entities import ApplicationComponent, MonitoredService
from keigan.entities.incident_entities import Incident
from keigan.entities.slo_entities import ServiceLevelIndicator, SliMeasurement
from keigan.exceptions.keigan_exceptions import KeiganException
from keigan.services.sli_measurement_reader import LATENCY_METRIC_NAMES, SliMeasurementReader
from keigan.utils.statistics_utils import linear_trend, robust_baseline
from keigan.utils.time_utils import hour_of_week, utc_now

logger = logging.getLogger(__name__)
ROBUST_Z_THRESHOLD = 3.5
CONSECUTIVE_SAMPLES = 3
SATURATION_THRESHOLD_PERCENT = 90.0
SATURATION_METRICS_BY_SERVICE_TYPE: dict[str, list[tuple[str, str]]] = {
    "aks": [("node_memory_working_set_percentage", "Memory"), ("node_cpu_usage_percentage", "CPU")],
    "sql_database": [("dtu_consumption_percent", "DTU")],
    "app_service": [("MemoryPercentage", "Memory"), ("CpuPercentage", "CPU")],
}
HOURS_PER_DAY = 24


@dataclass
class DetectedSignal:
    detector_name: str
    signal_title: str
    signal_severity: str
    confidence_score: float
    metric_name: str
    service_id: str | None = None
    sli_id: str | None = None
    observed_value: float | None = None
    expected_value: float | None = None
    deviation_score: float | None = None
    forecast_breach_at: datetime | None = None
    evidence_series: list[dict[str, Any]] = field(default_factory=list)
    facts_text: str = ""

    @property
    def identity(self) -> tuple[str, str | None, str | None, str]:
        return (self.detector_name, self.service_id, self.sli_id, self.metric_name)


def _series_points(points: list[tuple[datetime, float]], maximum_points: int = 60) -> list[dict[str, Any]]:
    step = max(1, len(points) // maximum_points)
    return [{"t": timestamp.isoformat(), "v": round(float(value), 4)} for timestamp, value in points[::step]]


class PredictiveDetectors:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.reader = SliMeasurementReader(session)

    async def run_all(self, application_id: str) -> tuple[list[DetectedSignal], set[str]]:
        """Returns the detected signals and the names of the detectors that ran to completion (only those may expire old signals)."""
        detected: list[DetectedSignal] = []
        completed: set[str] = set()
        for detector_name, detector in (
            ("seasonal_anomaly", self.seasonal_anomalies), ("error_budget_exhaustion", self.error_budget_forecasts), ("saturation_trend", self.saturation_trends),
            ("recurring_incident", self.recurring_incidents), ("change_risk", self.change_risks),
        ):
            try:
                detected.extend(await detector(application_id))
                completed.add(detector_name)
            except Exception:  # noqa: BLE001 - one failing detector must not stop the others
                logger.warning("Detector %s failed for application %s", detector_name, application_id, exc_info=True)
        return detected, completed

    async def _service_names(self, application_id: str) -> dict[str, str]:
        return {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all()}

    async def _enabled_slis(self, application_id: str) -> list[ServiceLevelIndicator]:
        return list((await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id, ServiceLevelIndicator.is_enabled.is_(True)))).all())

    # ── Seasonal anomaly ───────────────────────────────────────────────────────
    async def seasonal_anomalies(self, application_id: str) -> list[DetectedSignal]:
        now = utc_now()
        service_names = await self._service_names(application_id)
        signals: list[DetectedSignal] = []
        for sli in await self._enabled_slis(application_id):
            rows = (await self.session.execute(select(SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(
                SliMeasurement.sli_id == sli.sli_id, SliMeasurement.measurement_window_start >= now - timedelta(weeks=4)))).all()
            hourly_good: dict[datetime, list[float]] = defaultdict(lambda: [0.0, 0.0])
            for window_start, good, total in rows:
                if total:
                    bucket = window_start.replace(minute=0, second=0, microsecond=0)
                    hourly_good[bucket][0] += float(good or 0)
                    hourly_good[bucket][1] += float(total)
            error_ratio_by_hour = {bucket: 1 - good / total for bucket, (good, total) in hourly_good.items() if total >= 50}
            recent_buckets = sorted(error_ratio_by_hour)[-CONSECUTIVE_SAMPLES - 1:-1] if error_ratio_by_hour else []  # the newest bucket may be incomplete
            if len(recent_buckets) < CONSECUTIVE_SAMPLES:
                continue
            z_scores: list[float] = []
            expected_values: list[float] = []
            for bucket in recent_buckets[-CONSECUTIVE_SAMPLES:]:
                peers = [value for other_bucket, value in error_ratio_by_hour.items() if hour_of_week(other_bucket) == hour_of_week(bucket) and other_bucket < bucket - timedelta(hours=1)]
                baseline = robust_baseline(peers)
                if baseline is None:
                    break
                minimum_scale_baseline = type(baseline)(baseline.median, max(baseline.median_absolute_deviation, 0.1 * baseline.median, 2e-4))
                z_scores.append(minimum_scale_baseline.robust_z_score(error_ratio_by_hour[bucket]))
                expected_values.append(baseline.median)
            if len(z_scores) == CONSECUTIVE_SAMPLES and all(z > ROBUST_Z_THRESHOLD for z in z_scores):
                observed = error_ratio_by_hour[recent_buckets[-1]]
                signals.append(DetectedSignal(
                    detector_name="seasonal_anomaly", signal_title=f"{sli.sli_name if sli.sli_name.lower().startswith(service_names.get(sli.service_id or '', '~').lower()) else service_names.get(sli.service_id or '', 'Service') + ': ' + sli.sli_name} is unusually bad for this hour of the week",
                    signal_severity="critical" if min(z_scores) > 10 else "warning", confidence_score=min(0.95, 0.6 + 0.03 * min(z_scores)), metric_name=f"{sli.sli_name} error ratio", service_id=sli.service_id, sli_id=sli.sli_id,
                    observed_value=round(observed * 100, 3), expected_value=round(expected_values[-1] * 100, 3), deviation_score=round(min(z_scores), 2),
                    evidence_series=_series_points([(bucket, error_ratio_by_hour[bucket] * 100) for bucket in sorted(error_ratio_by_hour)[-72:]]),
                    facts_text=f"SLI {sli.sli_name}: error ratio {observed * 100:.3f}% against {expected_values[-1] * 100:.3f}% usual for this hour of the week; robust z-score {min(z_scores):.1f} for {CONSECUTIVE_SAMPLES} consecutive hours.",
                ))
        return signals

    # ── Error budget exhaustion ────────────────────────────────────────────────
    async def error_budget_forecasts(self, application_id: str) -> list[DetectedSignal]:
        from keigan.services.slo_service import SloService

        now = utc_now()
        signals: list[DetectedSignal] = []
        for summary in await SloService(self.session, self.reader).summarize_slos([application_id]):
            remaining_minutes, total_minutes = summary.get("errorBudgetRemainingMinutes"), summary.get("errorBudgetTotalMinutes")
            if remaining_minutes is None or not total_minutes:
                continue
            burn_rate_three_days = await self._burn_rate_over(summary["sliId"], summary["targetPercentage"], timedelta(days=3))
            burn_rate_value = max(summary.get("burnRateSixHours") or 0, summary.get("burnRateOneHour") or 0, burn_rate_three_days or 0)
            window_minutes = summary["rollingWindowDays"] * 24 * 60
            consumption_per_minute = burn_rate_value * total_minutes / window_minutes
            if remaining_minutes <= 0 or summary["status"] == "breached":
                minutes_until_exhaustion = 0.0
            elif burn_rate_value >= 0.5 and consumption_per_minute > 0:
                minutes_until_exhaustion = remaining_minutes / consumption_per_minute
            else:
                continue
            days_until_exhaustion = minutes_until_exhaustion / 1440
            if days_until_exhaustion > 2 * summary["rollingWindowDays"]:
                continue
            severity = "critical" if days_until_exhaustion < 3 and burn_rate_value > 1 else "warning" if days_until_exhaustion < 20 or minutes_until_exhaustion == 0 else "info"
            service_label = summary.get("serviceName") or "Service"
            subject = summary["sliName"] if summary["sliName"].lower().startswith(service_label.lower()) else f"{service_label}: {summary['sliName']}"
            title = f"{subject} error budget {'is exhausted' if minutes_until_exhaustion == 0 else f'will be exhausted in about {days_until_exhaustion:.1f} days at the current pace'}"
            signals.append(DetectedSignal(
                detector_name="error_budget_exhaustion", signal_title=title, signal_severity=severity, confidence_score=0.9 if burn_rate_value > 3 else 0.75, metric_name=f"{summary['sliName']} error budget",
                service_id=summary.get("serviceId"), sli_id=summary["sliId"], observed_value=round(summary.get("compliancePercentage") or 0, 3), expected_value=summary["targetPercentage"],
                deviation_score=round(burn_rate_value, 2), forecast_breach_at=now + timedelta(minutes=minutes_until_exhaustion),
                evidence_series=[{"t": str(index), "v": value} for index, value in enumerate(summary.get("sparkline") or [])],
                facts_text=(f"SLO {summary['sliName']} target {summary['targetPercentage']}% over {summary['rollingWindowDays']} days; compliance {summary.get('compliancePercentage')}%; "
                            f"error budget remaining {summary.get('errorBudgetRemainingPercentage')}% ({remaining_minutes} of {total_minutes} minutes); burn rate {burn_rate_value:.1f}x (1h {summary.get('burnRateOneHour')}, 6h {summary.get('burnRateSixHours')}, 3d {burn_rate_three_days}); "
                            f"forecast exhaustion in {days_until_exhaustion:.1f} days."),
            ))
        return signals

    async def _burn_rate_over(self, sli_id: str, target_percentage: float, period: timedelta) -> float | None:
        rows = (await self.session.execute(select(SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start >= utc_now() - period))).all()
        total = sum(float(row[1] or 0) for row in rows)
        allowed = 1 - target_percentage / 100
        return round((1 - sum(float(row[0] or 0) for row in rows) / total) / allowed, 2) if total and allowed > 0 else None

    # ── Saturation and latency trends ──────────────────────────────────────────
    async def saturation_trends(self, application_id: str) -> list[DetectedSignal]:
        now = utc_now()
        start = now - timedelta(days=7)
        gateway = application_context.telemetry_gateway()
        signals: list[DetectedSignal] = []
        services = (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id, MonitoredService.is_monitoring_enabled.is_(True)))).all()
        for service in services:
            try:
                target = await self.reader.target_for(service.service_id)
                for metric_name, metric_label in SATURATION_METRICS_BY_SERVICE_TYPE.get(service.service_type, []):
                    result = await gateway.query_metrics(target, [metric_name], start, now, 60, "Average")
                    points = [(timestamp, value) for series in result.series for timestamp, value in series.points if value is not None]
                    signal = self._saturation_signal(service, metric_name, metric_label, sorted(points), now)
                    if signal:
                        signals.append(signal)
                latency_metric = LATENCY_METRIC_NAMES.get(service.service_type, "Duration") if service.service_type in ("aks", "api_management", "app_service") else None
                if latency_metric:
                    result = await gateway.query_metrics(target, [latency_metric], start, now, 60, "Average")
                    points = sorted((timestamp, value) for series in result.series for timestamp, value in series.points if value is not None)
                    signal = self._latency_creep_signal(service, latency_metric, points)
                    if signal:
                        signals.append(signal)
            except KeiganException:
                continue  # the metric is not readable for this service
        return signals

    def _saturation_signal(self, service: MonitoredService, metric_name: str, metric_label: str, points: list[tuple[datetime, float]], now: datetime) -> DetectedSignal | None:
        if len(points) < 24:
            return None
        hours = [(timestamp - points[0][0]).total_seconds() / 3600 for timestamp, _ in points]
        values = [value for _, value in points]
        trend = linear_trend(hours, values)
        if trend is None or trend.slope_per_hour * HOURS_PER_DAY < 1.0 or trend.r_squared < 0.45:
            return None
        current_value = sum(values[-3:]) / 3
        hours_to_threshold = trend.hours_until(SATURATION_THRESHOLD_PERCENT, current_value)
        if hours_to_threshold is None or hours_to_threshold > 14 * HOURS_PER_DAY:
            return None
        days_to_threshold = hours_to_threshold / HOURS_PER_DAY
        severity = "critical" if days_to_threshold < 2 else "warning" if days_to_threshold < 7 else "info"
        return DetectedSignal(
            detector_name="saturation_trend", signal_title=f"{service.service_name}: {metric_label} is climbing and will reach {SATURATION_THRESHOLD_PERCENT:.0f}% in about {days_to_threshold:.1f} days", signal_severity=severity,
            confidence_score=round(min(0.95, 0.45 + 0.5 * trend.r_squared), 2), metric_name=metric_name, service_id=service.service_id, observed_value=round(current_value, 1), expected_value=round(sum(values[:12]) / 12, 1),
            deviation_score=round(trend.slope_per_hour * HOURS_PER_DAY, 2), forecast_breach_at=now + timedelta(hours=hours_to_threshold), evidence_series=_series_points(points),
            facts_text=f"{metric_label} on {service.service_name} ({metric_name}) is {current_value:.1f}% now, was {sum(values[:12]) / 12:.1f}% seven days ago; trend +{trend.slope_per_hour * HOURS_PER_DAY:.2f} percentage points per day (fit quality R2 {trend.r_squared:.2f}); forecast to reach {SATURATION_THRESHOLD_PERCENT:.0f}% in {days_to_threshold:.1f} days.",
        )

    def _latency_creep_signal(self, service: MonitoredService, metric_name: str, points: list[tuple[datetime, float]]) -> DetectedSignal | None:
        if len(points) < 48:
            return None
        hours = [(timestamp - points[0][0]).total_seconds() / 3600 for timestamp, _ in points]
        values = [value for _, value in points]
        trend = linear_trend(hours, values)
        if trend is None or trend.slope_per_hour <= 0 or trend.r_squared < 0.3:
            return None
        start_fit, end_fit = trend.intercept, trend.intercept + trend.slope_per_hour * hours[-1]
        if start_fit <= 0 or (end_fit - start_fit) / start_fit < 0.25:
            return None
        rise_percentage = (end_fit - start_fit) / start_fit * 100
        return DetectedSignal(
            detector_name="saturation_trend", signal_title=f"{service.service_name}: latency is creeping up ({rise_percentage:.0f}% over 7 days)", signal_severity="warning" if rise_percentage < 60 else "critical",
            confidence_score=round(min(0.9, 0.4 + 0.6 * trend.r_squared), 2), metric_name=f"{metric_name} (latency)", service_id=service.service_id, observed_value=round(end_fit, 1), expected_value=round(start_fit, 1),
            deviation_score=round(trend.slope_per_hour * HOURS_PER_DAY, 2), evidence_series=_series_points(points),
            facts_text=f"Latency of {service.service_name} ({metric_name}) rose from about {start_fit:.0f} ms to {end_fit:.0f} ms in seven days (+{rise_percentage:.0f}%, +{trend.slope_per_hour * HOURS_PER_DAY:.1f} ms per day, R2 {trend.r_squared:.2f}).",
        )

    # ── Recurring incidents ────────────────────────────────────────────────────
    async def recurring_incidents(self, application_id: str) -> list[DetectedSignal]:
        since = utc_now() - timedelta(days=30)
        incidents = (await self.session.scalars(select(Incident).where(Incident.application_id == application_id, Incident.opened_at >= since).order_by(Incident.opened_at))).all()
        groups: dict[tuple[str, str], list[Incident]] = defaultdict(list)
        for incident in incidents:
            primary_service_id = (incident.affected_service_ids_json or [""])[0]
            groups[(incident.incident_category or "unclassified", primary_service_id)].append(incident)
        service_names = await self._service_names(application_id)
        signals: list[DetectedSignal] = []
        for (category, service_id), grouped_incidents in groups.items():
            if len(grouped_incidents) < 2 or not service_id:
                continue
            service_label = service_names.get(service_id, "the service")
            numbers = ", ".join(incident.external_incident_number or incident.incident_id[:8] for incident in grouped_incidents[:6])
            signals.append(DetectedSignal(
                detector_name="recurring_incident", signal_title=f"{service_label}: {len(grouped_incidents)} '{category.replace('_', ' ')}' incidents in 30 days", signal_severity="warning" if len(grouped_incidents) >= 3 else "info",
                confidence_score=min(0.9, 0.6 + 0.1 * len(grouped_incidents)), metric_name=f"incidents:{category}", service_id=service_id, observed_value=float(len(grouped_incidents)), expected_value=1.0,
                evidence_series=[{"t": incident.opened_at.isoformat(), "v": index + 1} for index, incident in enumerate(grouped_incidents)],
                facts_text=f"{len(grouped_incidents)} incidents of category {category} affected {service_label} within 30 days ({numbers}). A permanent fix is probably cheaper than repeated response.",
            ))
        return signals

    # ── Change risk ────────────────────────────────────────────────────────────
    async def change_risks(self, application_id: str) -> list[DetectedSignal]:
        component = await self.session.scalar(select(ApplicationComponent).where(ApplicationComponent.application_id == application_id, ApplicationComponent.azure_subscription_id.is_not(None)).limit(1))
        if component is None:
            return []
        now = utc_now()
        changes = await application_context.telemetry_gateway().query_activity_changes(
            application_id, component.azure_tenant_id, component.azure_subscription_id, component.azure_resource_group_name, now - timedelta(hours=48), now,
            use_simulation=bool((component.component_configuration_json or {}).get("simulated")),
        )
        slis = [sli for sli in await self._enabled_slis(application_id) if sli.sli_kind == "availability"]
        signals: list[DetectedSignal] = []
        for change in changes:
            if change.change_kind not in ("deployment", "configuration_change") or change.occurred_at > now - timedelta(minutes=45):
                continue
            before_ratio = await self._error_ratio(slis, change.occurred_at - timedelta(hours=2), change.occurred_at)
            after_ratio = await self._error_ratio(slis, change.occurred_at, min(now, change.occurred_at + timedelta(hours=2)))
            if before_ratio is None or after_ratio is None or after_ratio < 0.002 or after_ratio < 2 * max(before_ratio, 1e-6):
                continue
            signals.append(DetectedSignal(
                detector_name="change_risk", signal_title=f"Error rate rose {after_ratio / max(before_ratio, 1e-6):.1f}x after: {change.operation_name}"[:400], signal_severity="warning", confidence_score=0.65,
                metric_name=f"change:{change.operation_name}"[:200], observed_value=round(after_ratio * 100, 3), expected_value=round(before_ratio * 100, 3), deviation_score=round(after_ratio / max(before_ratio, 1e-6), 2),
                evidence_series=[{"t": (change.occurred_at - timedelta(hours=2)).isoformat(), "v": round(before_ratio * 100, 3)}, {"t": change.occurred_at.isoformat(), "v": round(after_ratio * 100, 3)}],
                facts_text=f"{change.description} at {change.occurred_at:%Y-%m-%d %H:%M} UTC ({change.operation_name}). Error ratio two hours before {before_ratio * 100:.3f}%, two hours after {after_ratio * 100:.3f}%.",
            ))
        return signals

    async def _error_ratio(self, slis: list[ServiceLevelIndicator], start: datetime, end: datetime) -> float | None:
        if not slis or end <= start:
            return None
        rows = (await self.session.execute(select(SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(
            SliMeasurement.sli_id.in_([sli.sli_id for sli in slis]), SliMeasurement.measurement_window_start >= start, SliMeasurement.measurement_window_start < end))).all()
        total = sum(float(row[1] or 0) for row in rows)
        return 1 - sum(float(row[0] or 0) for row in rows) / total if total >= 200 else None

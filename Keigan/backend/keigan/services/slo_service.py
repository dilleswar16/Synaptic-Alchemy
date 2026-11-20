"""SLIs, SLOs, collection, backfill, error budgets, burn-rate alerts and the SLO dashboard views.

Counts (good, total) are stored per SLI at 5-minute granularity so any window can be recomputed (sample plan 7.4). Proposals and accept live in
``SliProposalService``; this class owns everything that happens after an SLO exists.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, insert, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.slo_dtos import (
    EcosystemHeatmapResponse, HeatmapCell, HeatmapRow, SeriesPoint, SliCreateRequest, SliResponse, SliUpdateRequest, SloCreateRequest, SloResponse, SloSeriesResponse, SloSummaryResponse, SloUpdateRequest,
)
from keigan.entities.alert_entities import Alert, AlertEvent
from keigan.entities.application_entities import Application, MonitoredService
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement, SloBurnAlert
from keigan.exceptions.keigan_exceptions import BusinessValidationException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services import alert_rules
from keigan.services.audit_service import AuditService
from keigan.services.authorization_service import AuthorizationService
from keigan.services.sli_measurement_reader import SliMeasurementReader, SliSample, validate_custom_sli_query
from keigan.utils.query_safety import QueryRejectedError
from keigan.utils.statistics_utils import burn_rate, error_budget_minutes
from keigan.utils.time_utils import floor_to_interval

logger = logging.getLogger(__name__)
SAMPLE_INTERVAL_MINUTES = 5
PAGE_BURN_RATE, TICKET_BURN_RATE = 14.4, 6.0
MINIMUM_EVENTS_IN_LONG_WINDOW = 50  # low-volume SLIs (synthetic probes, batch) need enough events before a burn rate means anything
INSERT_CHUNK_SIZE = 800


class SloService:
    def __init__(self, session: AsyncSession, reader: SliMeasurementReader | None = None):
        self.session = session
        self.reader = reader or SliMeasurementReader(session)

    # ── Job handlers ───────────────────────────────────────────────────────────
    async def measure_proposals(self, application_id: str) -> dict[str, Any] | None:
        from keigan.services.sli_proposal_service import SliProposalService

        return await SliProposalService(self.session, self.reader).measure(application_id)

    async def backfill_sli(self, sli_id: str) -> dict[str, Any] | None:
        sli = await self.session.get(ServiceLevelIndicator, sli_id)
        if sli is None or not sli.service_id:
            return {"inserted": 0}
        settings = get_settings()
        days = settings.slo_supporting_signal_backfill_days if sli.sli_kind == "supporting_signal" else settings.slo_backfill_days
        end = floor_to_interval(alert_rules.utc_now(), SAMPLE_INTERVAL_MINUTES)
        try:
            inserted = await self._collect(sli, end - timedelta(days=days), end)
        except QueryRejectedError as rejection:
            logger.warning("Backfill of SLI %s failed: its stored query was rejected (%s)", sli.sli_id, rejection.detail)
            return {"inserted": 0, "days": days, "rejected": rejection.detail}
        return {"inserted": inserted, "days": days}

    async def collect_due_measurements(self, application_id: str) -> dict[str, Any] | None:
        end = floor_to_interval(alert_rules.utc_now(), SAMPLE_INTERVAL_MINUTES)
        total_inserted = 0
        for sli in (await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id, ServiceLevelIndicator.is_enabled.is_(True)))).all():
            if not sli.service_id:
                continue
            start = (sli.last_collected_window_start + timedelta(minutes=SAMPLE_INTERVAL_MINUTES)) if sli.last_collected_window_start else end - timedelta(hours=1)
            start = max(start, end - timedelta(hours=24))
            if start >= end:
                continue
            try:
                total_inserted += await self._collect(sli, start, end)
            except QueryRejectedError as rejection:
                logger.warning("Collection failed for SLI %s: its stored query was rejected (%s)", sli.sli_id, rejection.detail)
            except Exception:  # noqa: BLE001
                logger.warning("Collection failed for SLI %s", sli.sli_id, exc_info=True)
        return {"inserted": total_inserted}

    async def _collect(self, sli: ServiceLevelIndicator, start: datetime, end: datetime) -> int:
        samples = await self.reader.read_samples(
            sli.service_id, sli_kind=sli.sli_kind, catalog_entry_key=sli.catalog_entry_key, start=start, end=end, interval_minutes=SAMPLE_INTERVAL_MINUTES,
            latency_threshold_milliseconds=sli.latency_threshold_milliseconds, query_definition=sli.query_definition_json,
        )
        samples = [sample for sample in samples if start <= sample.window_start < end]
        if not samples:
            return 0
        existing_starts = set((await self.session.scalars(select(SliMeasurement.measurement_window_start).where(
            SliMeasurement.sli_id == sli.sli_id, SliMeasurement.measurement_window_start >= start, SliMeasurement.measurement_window_start < end))).all())
        rows = [{"sli_id": sli.sli_id, "measurement_window_start": sample.window_start, "good_event_count": sample.good, "total_event_count": sample.total, "measured_value": sample.value, "collected_at": alert_rules.utc_now()}
                for sample in samples if sample.window_start not in existing_starts]
        for chunk_start in range(0, len(rows), INSERT_CHUNK_SIZE):
            await self.session.execute(insert(SliMeasurement), rows[chunk_start:chunk_start + INSERT_CHUNK_SIZE])
        newest = max(sample.window_start for sample in samples)
        sli.last_collected_window_start = max(newest, sli.last_collected_window_start) if sli.last_collected_window_start else newest
        return len(rows)

    # ── Burn rates ─────────────────────────────────────────────────────────────
    async def _burn_rate_for(self, sli_id: str, target_percentage: float, anchor: datetime, window: timedelta, minimum_event_count: int = 0) -> float | None:
        """Burn rate over the window; None when fewer than ``minimum_event_count`` events (one failed probe is not a page)."""
        since = anchor - window + timedelta(minutes=SAMPLE_INTERVAL_MINUTES)
        good, total = (await self.session.execute(select(func.coalesce(func.sum(SliMeasurement.good_event_count), 0), func.coalesce(func.sum(SliMeasurement.total_event_count), 0)).where(
            SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start >= since))).one()
        if float(total) < minimum_event_count:
            return None
        return burn_rate(float(good), float(total), target_percentage)

    async def is_service_burning_budget(self, service_id: str, threshold: float = 2.0) -> bool:
        rows = (await self.session.execute(select(ServiceLevelObjective, ServiceLevelIndicator).join(ServiceLevelIndicator, ServiceLevelIndicator.sli_id == ServiceLevelObjective.sli_id).where(
            ServiceLevelIndicator.service_id == service_id, ServiceLevelIndicator.is_enabled.is_(True)))).all()
        for slo, sli in rows:
            anchor = sli.last_collected_window_start
            if anchor is None:
                continue
            rate = await self._burn_rate_for(sli.sli_id, slo.target_percentage, anchor, timedelta(hours=1))
            if rate is not None and rate > threshold:
                return True
        return False

    async def evaluate_burn_rates(self, application_id: str) -> dict[str, Any] | None:
        fired = resolved = 0
        rows = (await self.session.execute(select(ServiceLevelObjective, ServiceLevelIndicator).join(ServiceLevelIndicator, ServiceLevelIndicator.sli_id == ServiceLevelObjective.sli_id).where(
            ServiceLevelObjective.application_id == application_id, ServiceLevelIndicator.is_enabled.is_(True), ServiceLevelIndicator.sli_kind != "supporting_signal"))).all()
        for slo, sli in rows:
            anchor = sli.last_collected_window_start
            if anchor is None:
                continue
            rates = {
                name: await self._burn_rate_for(sli.sli_id, slo.target_percentage, anchor, window, minimum_event_count)
                for name, window, minimum_event_count in (
                    ("5m", timedelta(minutes=5), 0), ("30m", timedelta(minutes=30), 0),
                    ("1h", timedelta(hours=1), MINIMUM_EVENTS_IN_LONG_WINDOW), ("6h", timedelta(hours=6), MINIMUM_EVENTS_IN_LONG_WINDOW),
                )
            }
            conditions = {
                "page": (rates["1h"], rates["5m"], rates["1h"] is not None and rates["5m"] is not None and rates["1h"] > PAGE_BURN_RATE and rates["5m"] > PAGE_BURN_RATE),
                "ticket": (rates["6h"], rates["30m"], rates["6h"] is not None and rates["30m"] is not None and rates["6h"] > TICKET_BURN_RATE and rates["30m"] > TICKET_BURN_RATE),
            }
            for severity, (long_rate, short_rate, is_burning) in conditions.items():
                open_alert = await self.session.scalar(select(SloBurnAlert).where(SloBurnAlert.slo_id == slo.slo_id, SloBurnAlert.burn_alert_severity == severity, SloBurnAlert.resolved_at.is_(None)).limit(1))
                if is_burning and open_alert is None:
                    burn_alert = SloBurnAlert(slo_id=slo.slo_id, application_id=application_id, burn_alert_severity=severity, long_window_burn_rate=round(long_rate, 2), short_window_burn_rate=round(short_rate, 2))
                    self.session.add(burn_alert)
                    await self.session.flush()
                    burn_alert.alert_group_id = await self._send_internal_alert(slo, sli, burn_alert, severity, long_rate, "firing")
                    await self._notify(burn_alert)
                    fired += 1
                elif not is_burning and open_alert is not None:
                    open_alert.resolved_at = alert_rules.utc_now()
                    await self._send_internal_alert(slo, sli, open_alert, severity, long_rate or 0.0, "resolved")
                    resolved += 1
        return {"fired": fired, "resolved": resolved}

    async def _send_internal_alert(self, slo: ServiceLevelObjective, sli: ServiceLevelIndicator, burn_alert: SloBurnAlert, severity: str, burn_rate_value: float | None, status: str) -> str | None:
        from keigan.services.alert_pipeline_service import AlertPipelineService
        from keigan.services.alert_source_service import AlertSourceService

        source = await AlertSourceService(self.session).get_or_create_internal_source(slo.application_id)
        now = alert_rules.utc_now()
        windows = "1 h and 5 min above 14.4x" if severity == "page" else "6 h and 30 min above 6x"
        identifier = f"slo-burn-{slo.slo_id}-{severity}"
        payload = {
            "externalId": identifier, "ruleId": identifier, "ruleName": f"SLO burn ({severity}): {sli.sli_name}", "status": status, "severity": 1 if severity == "page" else 2, "service": sli.service_id or "",
            "summary": f"Error budget of '{sli.sli_name}' is burning {burn_rate_value or 0:.1f}x too fast ({windows}); target {slo.target_percentage} %.", "startedAt": now.isoformat(),
            "labels": {"sloId": slo.slo_id, "burnAlertSeverity": severity, "source": "keigan_slo"},
        }
        event = AlertEvent(alert_source_id=source.alert_source_id, application_id=slo.application_id, received_at=now, raw_payload_json=payload, payload_size_bytes=len(str(payload)))
        self.session.add(event)
        await self.session.flush()
        result = await AlertPipelineService(self.session).process_event(event.alert_event_id)
        alert = await self.session.get(Alert, result["alertId"]) if result.get("alertId") else None
        return alert.alert_group_id if alert else None

    async def _notify(self, burn_alert: SloBurnAlert) -> None:
        try:
            from keigan.services.notification_service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).notify_slo_burn_alert(burn_alert.slo_burn_alert_id)
        except Exception:  # noqa: BLE001 - notifications are optional until S4 lands
            logger.debug("SLO burn notification skipped", exc_info=True)

    # ── Summaries (aggregated in SQL) ──────────────────────────────────────────
    def _day_bucket(self, column: Any) -> Any:
        dialect = self.session.get_bind().dialect.name
        if dialect == "sqlite":
            return func.strftime("%Y-%m-%d", column)
        if dialect == "postgresql":
            return func.to_char(column, "YYYY-MM-DD")
        return func.convert(literal_column("varchar(10)"), column, literal_column("23"))  # SQL Server: style 23 = yyyy-mm-dd

    async def summarize_slos(self, application_ids: list[str]) -> list[dict[str, Any]]:
        return [summary.model_dump(by_alias=True) for summary in await self._summaries(application_ids)]

    async def _summaries(self, application_ids: list[str]) -> list[SloSummaryResponse]:
        if not application_ids:
            return []
        rows = (await self.session.execute(
            select(ServiceLevelObjective, ServiceLevelIndicator).join(ServiceLevelIndicator, ServiceLevelIndicator.sli_id == ServiceLevelObjective.sli_id).where(
                ServiceLevelObjective.application_id.in_(application_ids), ServiceLevelIndicator.is_enabled.is_(True)).order_by(ServiceLevelIndicator.is_headline.desc(), ServiceLevelIndicator.sli_name)
        )).all()
        if not rows:
            return []
        now = alert_rules.utc_now()
        sli_ids = [sli.sli_id for _, sli in rows]
        totals: dict[str, tuple[float, float, float, float, float, float]] = {}
        for window_days in sorted({slo.rolling_window_days for slo, _ in rows}):
            ids_for_window = [sli.sli_id for slo, sli in rows if slo.rolling_window_days == window_days]
            for sli_id, good, total, good_1h, total_1h, good_6h, total_6h in (await self.session.execute(
                select(
                    SliMeasurement.sli_id, func.sum(SliMeasurement.good_event_count), func.sum(SliMeasurement.total_event_count),
                    func.sum(case((SliMeasurement.measurement_window_start >= now - timedelta(hours=1), SliMeasurement.good_event_count), else_=0)),
                    func.sum(case((SliMeasurement.measurement_window_start >= now - timedelta(hours=1), SliMeasurement.total_event_count), else_=0)),
                    func.sum(case((SliMeasurement.measurement_window_start >= now - timedelta(hours=6), SliMeasurement.good_event_count), else_=0)),
                    func.sum(case((SliMeasurement.measurement_window_start >= now - timedelta(hours=6), SliMeasurement.total_event_count), else_=0)),
                ).where(SliMeasurement.sli_id.in_(ids_for_window), SliMeasurement.measurement_window_start >= now - timedelta(days=window_days)).group_by(SliMeasurement.sli_id)
            )).all():
                totals[sli_id] = tuple(float(value or 0) for value in (good, total, good_1h, total_1h, good_6h, total_6h))  # type: ignore[assignment]
        day = self._day_bucket(SliMeasurement.measurement_window_start)
        sparklines: dict[str, list[float]] = defaultdict(list)
        for sli_id, _, good, total in (await self.session.execute(
            select(SliMeasurement.sli_id, day.label("day"), func.sum(SliMeasurement.good_event_count), func.sum(SliMeasurement.total_event_count)).where(
                SliMeasurement.sli_id.in_(sli_ids), SliMeasurement.measurement_window_start >= now - timedelta(days=14)).group_by(SliMeasurement.sli_id, day).order_by(day)
        )).all():
            if total:
                sparklines[sli_id].append(round(100 * float(good or 0) / float(total), 3))
        service_names = {service.service_id: service.service_name for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id.in_(application_ids)))).all()}
        application_names = {app.application_id: app.application_name for app in (await self.session.scalars(select(Application).where(Application.application_id.in_(application_ids)))).all()}
        summaries: list[SloSummaryResponse] = []
        for slo, sli in rows:
            good, total, good_1h, total_1h, good_6h, total_6h = totals.get(sli.sli_id, (0, 0, 0, 0, 0, 0))
            budget_minutes = error_budget_minutes(slo.target_percentage, slo.rolling_window_days)
            compliance = round(100 * good / total, 3) if total else None
            remaining_percentage = remaining_minutes = None
            if total:
                allowed_ratio = 1 - slo.target_percentage / 100
                remaining_percentage = round(max(-100.0, (1 - ((1 - good / total) / allowed_ratio)) * 100), 1)
                remaining_minutes = round(remaining_percentage / 100 * budget_minutes, 1)
            rate_1h, rate_6h = burn_rate(good_1h, total_1h, slo.target_percentage), burn_rate(good_6h, total_6h, slo.target_percentage)
            if compliance is None:
                status = "no_data"
            elif compliance < slo.target_percentage:
                status = "breached"
            elif (remaining_percentage is not None and remaining_percentage < 30) or (rate_6h is not None and rate_6h > 2):
                status = "at_risk"
            else:
                status = "healthy"
            summaries.append(SloSummaryResponse(
                slo_id=slo.slo_id, sli_id=sli.sli_id, application_id=slo.application_id, application_name=application_names.get(slo.application_id), service_id=sli.service_id, service_name=service_names.get(sli.service_id or ""),
                sli_name=sli.sli_name, sli_kind=sli.sli_kind, is_headline=sli.is_headline, is_approximate=sli.is_approximate, target_percentage=slo.target_percentage, rolling_window_days=slo.rolling_window_days,
                compliance_percentage=compliance, error_budget_remaining_percentage=remaining_percentage, error_budget_remaining_minutes=remaining_minutes, error_budget_total_minutes=round(budget_minutes, 1),
                burn_rate_one_hour=round(rate_1h, 2) if rate_1h is not None else None, burn_rate_six_hours=round(rate_6h, 2) if rate_6h is not None else None, status=status, sparkline=sparklines.get(sli.sli_id, []),
            ))
        return summaries

    async def get_dashboard(self, current_user: CurrentUser, application_ids: list[str] | None) -> list[SloSummaryResponse]:
        return await self._summaries(await AuthorizationService(self.session).scoped_application_ids(current_user, application_ids))

    async def get_series(self, current_user: CurrentUser, slo_id: str, period_start: datetime | None, period_end: datetime | None, resolution_minutes: int) -> SloSeriesResponse:
        slo = await self.session.get(ServiceLevelObjective, slo_id)
        if slo is None:
            raise NotFoundException("SLO not found.")
        await AuthorizationService(self.session).ensure_application_reader(current_user, slo.application_id)
        sli = await self.session.get(ServiceLevelIndicator, slo.sli_id)
        end = period_end or alert_rules.utc_now()
        start = period_start or end - timedelta(days=slo.rolling_window_days)
        resolution_minutes = max(5, min(resolution_minutes, 1440))
        buckets: dict[datetime, list[int]] = {}
        for window_start, good, total in (await self.session.execute(select(SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(
                SliMeasurement.sli_id == slo.sli_id, SliMeasurement.measurement_window_start >= start, SliMeasurement.measurement_window_start <= end).order_by(SliMeasurement.measurement_window_start))).all():
            bucket = buckets.setdefault(floor_to_interval(window_start, resolution_minutes), [0, 0])
            bucket[0] += good or 0
            bucket[1] += total or 0
        allowed_ratio = 1 - slo.target_percentage / 100
        average_total = (sum(total for _, total in buckets.values()) / len(buckets)) if buckets else 0
        expected_window_total = average_total * (slo.rolling_window_days * 1440 / resolution_minutes)
        points, cumulative_errors, total_good, total_all = [], 0, 0, 0
        for timestamp in sorted(buckets):
            good, total = buckets[timestamp]
            cumulative_errors += total - good
            total_good, total_all = total_good + good, total_all + total
            remaining = round(max(-100.0, (1 - cumulative_errors / (allowed_ratio * expected_window_total)) * 100), 2) if expected_window_total and allowed_ratio else None
            points.append(SeriesPoint(timestamp=timestamp, sli_percentage=round(100 * good / total, 3) if total else None, good_event_count=good, total_event_count=total, budget_remaining_percentage=remaining))
        return SloSeriesResponse(slo_id=slo_id, sli_name=sli.sli_name, target_percentage=slo.target_percentage, rolling_window_days=slo.rolling_window_days, resolution_minutes=resolution_minutes, points=points,
                                 compliance_percentage=round(100 * total_good / total_all, 3) if total_all else None)

    async def get_ecosystem_heatmap(self, current_user: CurrentUser, days: int) -> EcosystemHeatmapResponse:
        days = max(1, min(days, 90))
        readable_ids = sorted(await AuthorizationService(self.session).readable_application_ids(current_user))
        summaries = await self._summaries(readable_ids)
        now = alert_rules.utc_now()
        dates = [(now - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(days - 1, -1, -1)]
        day = self._day_bucket(SliMeasurementAlias.measurement_window_start)
        daily: dict[tuple[str, str], float] = {}
        sli_ids = [summary.sli_id for summary in summaries]
        if sli_ids:
            for sli_id, bucket_day, good, total in (await self.session.execute(select(SliMeasurementAlias.sli_id, day, func.sum(SliMeasurementAlias.good_event_count), func.sum(SliMeasurementAlias.total_event_count)).where(
                    SliMeasurementAlias.sli_id.in_(sli_ids), SliMeasurementAlias.measurement_window_start >= now - timedelta(days=days)).group_by(SliMeasurementAlias.sli_id, day))).all():
                if total:
                    daily[(sli_id, bucket_day)] = round(100 * float(good or 0) / float(total), 3)
        rows = [HeatmapRow(
            application_id=summary.application_id, application_name=summary.application_name or "", slo_id=summary.slo_id, row_label=summary.sli_name, service_name=summary.service_name, target_percentage=summary.target_percentage,
            overall_compliance_percentage=summary.compliance_percentage, status=summary.status, cells=[HeatmapCell(date=date, compliance_percentage=daily.get((summary.sli_id, date))) for date in dates]) for summary in summaries]
        return EcosystemHeatmapResponse(days=days, dates=dates, rows=rows)

    # ── CRUD ───────────────────────────────────────────────────────────────────
    def _slo_response(self, slo: ServiceLevelObjective) -> SloResponse:
        return SloResponse(slo_id=slo.slo_id, sli_id=slo.sli_id, application_id=slo.application_id, target_percentage=slo.target_percentage, rolling_window_days=slo.rolling_window_days,
                           error_budget_minutes=round(error_budget_minutes(slo.target_percentage, slo.rolling_window_days), 1), burn_rate_policy=slo.burn_rate_policy_json)

    @staticmethod
    def _check_custom_query(query_definition: dict[str, Any] | None) -> None:
        """A custom SLI query runs on a schedule with Keigan's identity: refuse it on save when it reads anything but the configured SLI tables."""
        if not query_definition or "kql" not in query_definition:
            return
        now = alert_rules.utc_now()
        try:
            validate_custom_sli_query(str(query_definition["kql"]), now - timedelta(hours=1), now)
        except QueryRejectedError as rejection:
            raise BusinessValidationException(
                f"The log query was not accepted. {rejection.detail} Fix the query and save again.", field_errors=[{"field": "queryDefinition", "message": rejection.detail}]
            ) from rejection

    async def _sli_response(self, sli: ServiceLevelIndicator) -> SliResponse:
        slo = await self.session.scalar(select(ServiceLevelObjective).where(ServiceLevelObjective.sli_id == sli.sli_id).limit(1))
        service = await self.session.get(MonitoredService, sli.service_id) if sli.service_id else None
        return self._build_sli_response(sli, slo, service)

    def _build_sli_response(self, sli: ServiceLevelIndicator, slo: ServiceLevelObjective | None, service: MonitoredService | None) -> SliResponse:
        return SliResponse(
            sli_id=sli.sli_id, application_id=sli.application_id, service_id=sli.service_id, service_name=service.service_name if service else None, catalog_entry_key=sli.catalog_entry_key, sli_name=sli.sli_name, sli_kind=sli.sli_kind,
            data_source_kind=sli.data_source_kind, query_definition=sli.query_definition_json, latency_threshold_milliseconds=sli.latency_threshold_milliseconds, is_approximate=sli.is_approximate, is_enabled=sli.is_enabled,
            is_headline=sli.is_headline, measured_baseline=sli.measured_baseline_json, last_collected_window_start=sli.last_collected_window_start, slo=self._slo_response(slo) if slo else None,
        )

    async def list_slis(self, application_id: str) -> list[SliResponse]:
        slis = (await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id).order_by(ServiceLevelIndicator.sli_name))).all()
        slos_by_sli_id: dict[str, ServiceLevelObjective] = {}
        for slo in (await self.session.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.application_id == application_id))).all():
            slos_by_sli_id.setdefault(slo.sli_id, slo)
        services_by_id = {service.service_id: service for service in (await self.session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id))).all()}
        return [self._build_sli_response(sli, slos_by_sli_id.get(sli.sli_id), services_by_id.get(sli.service_id or "")) for sli in slis]

    async def create_sli(self, current_user: CurrentUser, application_id: str, request: SliCreateRequest) -> SliResponse:
        if request.service_id:
            service = await self.session.get(MonitoredService, request.service_id)
            if service is None or service.application_id != application_id:
                raise BusinessValidationException("The service does not belong to this application.", field_errors=[{"field": "serviceId", "message": "Unknown service."}])
        if request.data_source_kind == "log_query" and not str(request.query_definition.get("kql", "")).strip():
            raise BusinessValidationException("A log query SLI needs a KQL query returning good, total and window_start.", field_errors=[{"field": "queryDefinition", "message": "kql is required."}])
        self._check_custom_query(request.query_definition)
        sli = ServiceLevelIndicator(
            application_id=application_id, service_id=request.service_id, catalog_entry_key="custom", sli_name=request.sli_name.strip(), sli_kind=request.sli_kind, data_source_kind=request.data_source_kind,
            query_definition_json=request.query_definition, latency_threshold_milliseconds=request.latency_threshold_milliseconds, created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name,
        )
        self.session.add(sli)
        await self.session.flush()
        if request.target_percentage:
            self.session.add(ServiceLevelObjective(sli_id=sli.sli_id, application_id=application_id, target_percentage=request.target_percentage, rolling_window_days=request.rolling_window_days,
                                                   created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name))
        from keigan.workers.job_queue import JobQueue

        await JobQueue(self.session).enqueue("backfill_sli", {"sli_id": sli.sli_id}, deduplication_key=f"backfill_sli:{sli.sli_id}", priority_number=40)
        await AuditService(self.session).record(current_user, "sli.create", target_entity_type="service_level_indicator", target_entity_id=sli.sli_id, application_id=application_id, action_details={"name": sli.sli_name})
        await self.session.flush()
        return await self._sli_response(sli)

    async def _editable_sli(self, current_user: CurrentUser, sli_id: str) -> ServiceLevelIndicator:
        sli = await self.session.get(ServiceLevelIndicator, sli_id)
        if sli is None:
            raise NotFoundException("SLI not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, sli.application_id)
        return sli

    async def update_sli(self, current_user: CurrentUser, sli_id: str, request: SliUpdateRequest) -> SliResponse:
        sli = await self._editable_sli(current_user, sli_id)
        if request.sli_name is not None:
            sli.sli_name = request.sli_name.strip()
        if request.is_enabled is not None:
            sli.is_enabled = request.is_enabled
        if request.latency_threshold_milliseconds is not None:
            sli.latency_threshold_milliseconds = request.latency_threshold_milliseconds
        if request.query_definition is not None:
            self._check_custom_query(request.query_definition)
            sli.query_definition_json = request.query_definition
        if request.is_headline is not None:
            if request.is_headline:
                for other in (await self.session.scalars(select(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == sli.application_id, ServiceLevelIndicator.is_headline.is_(True)))).all():
                    other.is_headline = False
            sli.is_headline = request.is_headline
        sli.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "sli.update", target_entity_type="service_level_indicator", target_entity_id=sli_id, application_id=sli.application_id)
        return await self._sli_response(sli)

    async def delete_sli(self, current_user: CurrentUser, sli_id: str) -> None:
        sli = await self._editable_sli(current_user, sli_id)
        for slo in (await self.session.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.sli_id == sli_id))).all():
            await self.session.delete(slo)
        await self.session.execute(SliMeasurement.__table__.delete().where(SliMeasurement.sli_id == sli_id))
        await self.session.delete(sli)
        await AuditService(self.session).record(current_user, "sli.delete", target_entity_type="service_level_indicator", target_entity_id=sli_id, application_id=sli.application_id, action_details={"name": sli.sli_name})

    async def list_slos(self, application_id: str) -> list[SloResponse]:
        return [self._slo_response(slo) for slo in (await self.session.scalars(select(ServiceLevelObjective).where(ServiceLevelObjective.application_id == application_id))).all()]

    async def create_slo(self, current_user: CurrentUser, application_id: str, request: SloCreateRequest) -> SloResponse:
        sli = await self.session.get(ServiceLevelIndicator, request.sli_id)
        if sli is None or sli.application_id != application_id:
            raise NotFoundException("SLI not found in this application.")
        if await self.session.scalar(select(ServiceLevelObjective.slo_id).where(ServiceLevelObjective.sli_id == request.sli_id).limit(1)):
            raise BusinessValidationException("This SLI already has an SLO. Edit it instead.")
        slo = ServiceLevelObjective(sli_id=request.sli_id, application_id=application_id, target_percentage=request.target_percentage, rolling_window_days=request.rolling_window_days,
                                    created_by_user_principal_name=current_user.user_principal_name, updated_by_user_principal_name=current_user.user_principal_name)
        self.session.add(slo)
        await self.session.flush()
        await AuditService(self.session).record(current_user, "slo.create", target_entity_type="service_level_objective", target_entity_id=slo.slo_id, application_id=application_id, action_details={"target": slo.target_percentage})
        return self._slo_response(slo)

    async def update_slo(self, current_user: CurrentUser, slo_id: str, request: SloUpdateRequest) -> SloResponse:
        slo = await self.session.get(ServiceLevelObjective, slo_id)
        if slo is None:
            raise NotFoundException("SLO not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, slo.application_id)
        slo.target_percentage = request.target_percentage or slo.target_percentage
        slo.rolling_window_days = request.rolling_window_days or slo.rolling_window_days
        slo.updated_by_user_principal_name = current_user.user_principal_name
        await AuditService(self.session).record(current_user, "slo.update", target_entity_type="service_level_objective", target_entity_id=slo_id, application_id=slo.application_id, action_details={"target": slo.target_percentage})
        return self._slo_response(slo)

    async def delete_slo(self, current_user: CurrentUser, slo_id: str) -> None:
        slo = await self.session.get(ServiceLevelObjective, slo_id)
        if slo is None:
            raise NotFoundException("SLO not found.")
        await AuthorizationService(self.session).ensure_application_admin(current_user, slo.application_id)
        await self.session.delete(slo)
        await AuditService(self.session).record(current_user, "slo.delete", target_entity_type="service_level_objective", target_entity_id=slo_id, application_id=slo.application_id)


SliMeasurementAlias = SliMeasurement
_ = SliSample

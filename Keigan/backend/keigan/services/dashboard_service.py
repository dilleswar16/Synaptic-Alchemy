"""Home dashboard: one aggregated read model for everything a signed-in person needs first."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.dashboard_dtos import (
    ApplicationHealthCard, HomeDashboardResponse, HomeKpiResponse, IntelligenceFeedItem, LiveIncidentItem, MaintenanceWindowItem, RecentPostmortemItem,
)
from keigan.entities.all_entities import (
    Alert, AlertGroup, Application, ApplicationComponent, Incident, IntelligenceReport, Investigation, MaintenanceWindow, PostmortemReport, PredictiveSignal,
    ServiceLevelIndicator, SliMeasurement,
)
from keigan.entities.status_values import AlertGroupStatus, IncidentStatus, Priority, SignalStatus
from keigan.security.current_user import CurrentUser
from keigan.services.authorization_service import AuthorizationService
from keigan.services.slo_service import SloService
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
OPEN_INCIDENT_STATUSES = (IncidentStatus.NEW, IncidentStatus.INVESTIGATING, IncidentStatus.IDENTIFIED, IncidentStatus.MONITORING)
PRIORITY_PENALTY = {Priority.P1: 30, Priority.P2: 15, Priority.P3: 6, Priority.P4: 2}
SEVERITY_RANK = {"critical": 0, "high": 1, "warning": 2, "medium": 2, "info": 3, "low": 3}


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_home(self, current_user: CurrentUser, requested_application_ids: list[str] | None) -> HomeDashboardResponse:
        application_ids = await AuthorizationService(self.session).scoped_application_ids(current_user, requested_application_ids)
        now = utc_now()
        applications = list((await self.session.scalars(select(Application).where(Application.application_id.in_(application_ids)).order_by(Application.application_name))).all()) if application_ids else []
        names = {item.application_id: item.application_name for item in applications}
        incidents = list((await self.session.scalars(
            select(Incident).where(Incident.application_id.in_(application_ids), Incident.incident_status.in_(OPEN_INCIDENT_STATUSES)).order_by(Incident.opened_at.desc()))).all()) if application_ids else []
        slo_summaries = await self._slo_summaries(application_ids)
        kpis = await self._kpis(application_ids, incidents, slo_summaries, now)
        return HomeDashboardResponse(
            greeting_name=(current_user.display_name or current_user.user_principal_name).split(" ")[0], status_sentence=self._status_sentence(incidents, kpis, len(applications)),
            kpis=kpis, application_cards=await self._application_cards(applications, incidents, slo_summaries, now), live_incidents=await self._live_incidents(incidents[:8], names),
            intelligence_feed=await self._intelligence_feed(application_ids, names), maintenance_windows=await self._maintenance_windows(application_ids, names, now),
            recent_postmortems=await self._recent_postmortems(application_ids, names), generated_at=now)

    async def _slo_summaries(self, application_ids: list[str]) -> list[dict[str, Any]]:
        try:
            return await SloService(self.session).summarize_slos(application_ids)
        except Exception as slo_error:  # noqa: BLE001 — the home page must render even when SLOs are unavailable
            logger.warning("SLO summary unavailable for home: %s", slo_error)
            return []

    async def _kpis(self, application_ids: list[str], incidents: list[Incident], slo_summaries: list[dict[str, Any]], now: Any) -> HomeKpiResponse:
        by_priority: dict[str, int] = defaultdict(int)
        for incident in incidents:
            by_priority[incident.keigan_priority or incident.servicenow_priority or Priority.P3] += 1
        day_ago = now - timedelta(hours=24)
        active_groups = alerts_24h = groups_24h = investigations_24h = 0
        mean_minutes = None
        if application_ids:
            active_groups = await self.session.scalar(select(func.count()).select_from(AlertGroup).where(AlertGroup.application_id.in_(application_ids), AlertGroup.group_status != AlertGroupStatus.RESOLVED)) or 0
            alerts_24h = await self.session.scalar(select(func.count()).select_from(Alert).where(Alert.application_id.in_(application_ids), Alert.first_seen_at >= day_ago)) or 0
            groups_24h = await self.session.scalar(select(func.count()).select_from(AlertGroup).where(AlertGroup.application_id.in_(application_ids), AlertGroup.started_at >= day_ago)) or 0
            investigations_24h = await self.session.scalar(select(func.count()).select_from(Investigation).where(Investigation.application_id.in_(application_ids), Investigation.created_at >= day_ago)) or 0
            timings = (await self.session.execute(select(Incident.detected_by_keigan_at, Incident.first_update_sent_at).where(
                Incident.application_id.in_(application_ids), Incident.first_update_sent_at.is_not(None), Incident.opened_at >= now - timedelta(days=30)))).all()
            if timings:
                mean_minutes = round(sum((sent - detected).total_seconds() for detected, sent in timings) / len(timings) / 60, 1)
        return HomeKpiResponse(
            open_incidents_total=len(incidents), open_incidents_by_priority=dict(by_priority), active_alert_group_count=active_groups, alerts_last_24_hours=alerts_24h,
            noise_reduction_percentage=round(100 * (1 - groups_24h / alerts_24h), 1) if alerts_24h else None, slo_total_count=len(slo_summaries),
            slos_at_risk_count=sum(1 for item in slo_summaries if item.get("status") in ("at_risk", "breached")), investigations_last_24_hours=investigations_24h, mean_minutes_to_first_update=mean_minutes)

    @staticmethod
    def _status_sentence(incidents: list[Incident], kpis: HomeKpiResponse, application_count: int) -> str:
        if application_count == 0:
            return "You are not assigned to any applications yet."
        if not incidents:
            risk = f" {kpis.slos_at_risk_count} SLO{'s' if kpis.slos_at_risk_count != 1 else ''} need attention." if kpis.slos_at_risk_count else ""
            return f"All {application_count} application{'s' if application_count != 1 else ''} look healthy, with no open incidents.{risk}"
        critical = sum(1 for incident in incidents if (incident.keigan_priority or incident.servicenow_priority) in (Priority.P1, Priority.P2))
        lead = f"{len(incidents)} open incident{'s' if len(incidents) != 1 else ''}"
        return f"{lead}, {critical} high priority. Keigan is investigating." if critical else f"{lead}, none high priority."

    async def _application_cards(self, applications: list[Application], incidents: list[Incident], slo_summaries: list[dict[str, Any]], now: Any) -> list[ApplicationHealthCard]:
        if not applications:
            return []
        application_ids = [item.application_id for item in applications]
        component_types: dict[str, set[str]] = defaultdict(set)
        for application_id, component_type in (await self.session.execute(select(ApplicationComponent.application_id, ApplicationComponent.component_type).where(ApplicationComponent.application_id.in_(application_ids)))).all():
            component_types[application_id].add(component_type)
        latest_scores: dict[str, int] = {}
        for report in (await self.session.scalars(select(IntelligenceReport).where(IntelligenceReport.application_id.in_(application_ids), IntelligenceReport.overall_health_score.is_not(None)).order_by(IntelligenceReport.created_at))).all():
            latest_scores[report.application_id] = report.overall_health_score  # type: ignore[assignment]
        signals: dict[str, PredictiveSignal] = {}
        for signal in (await self.session.scalars(select(PredictiveSignal).where(PredictiveSignal.application_id.in_(application_ids), PredictiveSignal.signal_status == SignalStatus.OPEN).order_by(PredictiveSignal.detected_at))).all():
            signals[signal.application_id] = signal  # newest wins
        sparklines = await self._availability_sparklines(application_ids, now)
        cards: list[ApplicationHealthCard] = []
        for application in applications:
            application_incidents = [item for item in incidents if item.application_id == application.application_id]
            application_slos = [item for item in slo_summaries if item["applicationId"] == application.application_id and item.get("errorBudgetRemainingPercentage") is not None]
            worst = min(application_slos, key=lambda item: item["errorBudgetRemainingPercentage"], default=None)
            penalty = sum(PRIORITY_PENALTY.get(item.keigan_priority or item.servicenow_priority or Priority.P3, 6) for item in application_incidents)
            health = latest_scores.get(application.application_id, 100)
            health = max(0, min(100, health - penalty if application_incidents else health))
            if worst is not None and worst["errorBudgetRemainingPercentage"] < 0:
                health = min(health, 60)
            signal = signals.get(application.application_id)
            cards.append(ApplicationHealthCard(
                application_id=application.application_id, application_name=application.application_name, application_code=application.application_code, criticality_tier=application.criticality_tier,
                health_percentage=health, health_status="healthy" if health >= 90 else "watch" if health >= 75 else "degraded" if health >= 50 else "critical",
                worst_budget_remaining_percentage=worst["errorBudgetRemainingPercentage"] if worst else None, worst_budget_slo_name=(worst.get("sliName") if worst else None),
                availability_sparkline=sparklines.get(application.application_id, []), open_incident_count=len(application_incidents), latest_signal_title=signal.signal_title if signal else None,
                latest_signal_severity=signal.signal_severity if signal else None, component_types=sorted(component_types.get(application.application_id, set()))))
        return sorted(cards, key=lambda card: (card.health_percentage, card.application_name))

    async def _availability_sparklines(self, application_ids: list[str], now: Any) -> dict[str, list[float]]:
        slis = (await self.session.execute(select(ServiceLevelIndicator.sli_id, ServiceLevelIndicator.application_id).where(
            ServiceLevelIndicator.application_id.in_(application_ids), ServiceLevelIndicator.sli_kind == "availability", ServiceLevelIndicator.is_enabled.is_(True)))).all()
        owner_by_sli = {sli_id: application_id for sli_id, application_id in slis}
        if not owner_by_sli:
            return {}
        hourly: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for sli_id, window_start, good, total in (await self.session.execute(select(
                SliMeasurement.sli_id, SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count).where(
                SliMeasurement.sli_id.in_(list(owner_by_sli)), SliMeasurement.measurement_window_start >= now - timedelta(hours=24)))).all():
            bucket = hourly[owner_by_sli[sli_id]][window_start.strftime("%Y%m%d%H")]
            bucket[0] += good or 0
            bucket[1] += total or 0
        return {application_id: [round(100 * good / total, 2) for _, (good, total) in sorted(buckets.items()) if total] for application_id, buckets in hourly.items()}

    async def _live_incidents(self, incidents: list[Incident], names: dict[str, str]) -> list[LiveIncidentItem]:
        latest_by_incident: dict[str, Investigation] = {}
        if incidents:
            for investigation in (await self.session.scalars(select(Investigation).where(Investigation.incident_id.in_([item.incident_id for item in incidents])).order_by(Investigation.created_at))).all():
                latest_by_incident[investigation.incident_id or ""] = investigation
        items: list[LiveIncidentItem] = []
        for incident in incidents:
            investigation = latest_by_incident.get(incident.incident_id)
            items.append(LiveIncidentItem(
                incident_id=incident.incident_id, investigation_id=investigation.investigation_id if investigation else None, application_id=incident.application_id, application_name=names.get(incident.application_id, ""),
                incident_title=incident.incident_title, external_incident_number=incident.external_incident_number, priority=incident.keigan_priority or incident.servicenow_priority, incident_status=incident.incident_status,
                investigation_status=investigation.investigation_status if investigation else None, current_stage_name=investigation.current_stage_name if investigation else None,
                progress_percent=investigation.progress_percent if investigation else None, opened_at=incident.opened_at))
        return items

    async def _intelligence_feed(self, application_ids: list[str], names: dict[str, str]) -> list[IntelligenceFeedItem]:
        if not application_ids:
            return []
        signals = (await self.session.scalars(select(PredictiveSignal).where(PredictiveSignal.application_id.in_(application_ids), PredictiveSignal.signal_status == SignalStatus.OPEN).order_by(PredictiveSignal.detected_at.desc()).limit(30))).all()
        ranked = sorted(signals, key=lambda item: SEVERITY_RANK.get(item.signal_severity, 4))[:6]
        return [IntelligenceFeedItem(signal_id=item.predictive_signal_id, application_id=item.application_id, application_name=names.get(item.application_id, ""), signal_title=item.signal_title,
                                     signal_severity=item.signal_severity, forecast_breach_at=item.forecast_breach_at, detected_at=item.detected_at) for item in ranked]

    async def _maintenance_windows(self, application_ids: list[str], names: dict[str, str], now: Any) -> list[MaintenanceWindowItem]:
        if not application_ids:
            return []
        horizon = now + timedelta(days=7)
        windows = (await self.session.scalars(select(MaintenanceWindow).where(MaintenanceWindow.application_id.in_(application_ids), MaintenanceWindow.ends_at >= now, MaintenanceWindow.starts_at <= horizon).order_by(MaintenanceWindow.starts_at).limit(8))).all()
        return [MaintenanceWindowItem(maintenance_window_id=item.maintenance_window_id, application_id=item.application_id, application_name=names.get(item.application_id, ""), window_name=item.window_name,
                                      starts_at=item.starts_at, ends_at=item.ends_at) for item in windows]

    async def _recent_postmortems(self, application_ids: list[str], names: dict[str, str]) -> list[RecentPostmortemItem]:
        if not application_ids:
            return []
        rows = (await self.session.execute(select(PostmortemReport, Incident.application_id).join(Incident, Incident.incident_id == PostmortemReport.incident_id).where(
            Incident.application_id.in_(application_ids)).order_by(PostmortemReport.created_at.desc()).limit(5))).all()
        return [RecentPostmortemItem(postmortem_id=report.postmortem_id, incident_id=report.incident_id, application_name=names.get(application_id, ""), report_title=report.report_title,
                                     report_status=report.report_status, created_at=report.created_at) for report, application_id in rows]

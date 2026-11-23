"""How much of each SLO's error budget an incident used (spec 30, 4.4): reads the SLIs, SLOs and measurements and stores one row per incident and SLO.

An impact is provisional while the incident is open and until ``ERROR_BUDGET_POLICY_FINAL_AFTER_HOURS`` after it was resolved (late SLI data may still arrive), then final and frozen, so
a figure can be cited in a postmortem. The rows are information whether or not the team turned the policy on.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.config.settings import get_settings
from keigan.dtos.error_budget_dtos import BudgetImpactDto
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.error_budget_entities import IncidentBudgetImpact
from keigan.entities.incident_entities import Incident
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
from keigan.entities.status_values import IncidentBudgetImpactState
from keigan.services.error_budget_math import MeasurementTotals, budget_share, impact_window
from keigan.utils.time_utils import ensure_utc, utc_now


SUPPORTING_SIGNAL_KIND = "supporting_signal"  # an SLI kind that only helps diagnosis: burn alerts and budget impacts leave it out


def impact_state_of(is_insufficient: bool, resolved_at: datetime | None, now: datetime, final_after_hours: int) -> IncidentBudgetImpactState:
    if is_insufficient:
        return IncidentBudgetImpactState.INSUFFICIENT_DATA
    if resolved_at is not None and now >= resolved_at + timedelta(hours=final_after_hours):
        return IncidentBudgetImpactState.FINAL
    return IncidentBudgetImpactState.PROVISIONAL


def impact_dto(row: IncidentBudgetImpact) -> BudgetImpactDto:
    return BudgetImpactDto(
        slo_id=row.slo_id, sli_name=row.sli_name_text, target_percentage=row.target_percentage, budget_window_days=row.budget_window_days, impact_window_start=row.impact_window_start,
        impact_window_end=row.impact_window_end, budget_window_start=row.budget_window_start, budget_window_end=row.budget_window_end, bad_event_count=row.bad_event_count,
        impact_total_event_count=row.impact_total_event_count, window_total_event_count=row.window_total_event_count, budget_event_count=row.budget_event_count,
        budget_share_percent=row.budget_share_percent, data_coverage_percent=row.data_coverage_percent, is_service_matched=row.is_service_matched, impact_state=row.impact_state,
        evaluated_at=row.evaluated_at,
    )


class IncidentBudgetImpactService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def impacts_of(self, incident_id: str) -> list[IncidentBudgetImpact]:
        return list((await self.session.scalars(select(IncidentBudgetImpact).where(IncidentBudgetImpact.incident_id == incident_id).order_by(IncidentBudgetImpact.sli_name_text))).all())

    async def evaluate(self, incident: Incident, now: datetime | None = None) -> list[IncidentBudgetImpact]:
        """Writes or updates the incident's impact rows. A frozen set (final, evaluated after it became final) is returned as it is."""
        now = now or utc_now()
        existing = {row.slo_id: row for row in await self.impacts_of(incident.incident_id)}
        resolved_at = ensure_utc(incident.resolved_at)
        if resolved_at is not None and existing:
            final_from = resolved_at + timedelta(hours=self.settings.error_budget_policy_final_after_hours)
            if now >= final_from and all((ensure_utc(row.evaluated_at) or now) >= final_from for row in existing.values()):
                return list(existing.values())
        start, end = impact_window(
            opened_at=ensure_utc(incident.opened_at) or now, detected_at=ensure_utc(incident.detected_by_keigan_at), first_alert_at=await self._first_alert_at(incident.incident_id),
            resolved_at=resolved_at, now=now,
        )
        affected_service_ids = set(incident.affected_service_ids)
        rows: list[IncidentBudgetImpact] = []
        for slo, sli, is_service_matched in await self._matching_slos(incident.application_id, affected_service_ids):
            impact = await self.totals(sli.sli_id, start, end)
            budget_end = end
            budget_start = budget_end - timedelta(days=slo.rolling_window_days)
            window = await self.totals(sli.sli_id, budget_start, budget_end)
            share = budget_share(
                impact, window, slo.target_percentage, slo.rolling_window_days, minimum_coverage_percent=self.settings.error_budget_policy_minimum_data_coverage_percent,
                minimum_window_events=self.settings.error_budget_policy_minimum_window_events,
            )
            row = existing.get(slo.slo_id) or IncidentBudgetImpact(incident_id=incident.incident_id, application_id=incident.application_id, slo_id=slo.slo_id)
            row.sli_name_text, row.target_percentage, row.budget_window_days = sli.sli_name[:200], slo.target_percentage, slo.rolling_window_days
            row.impact_window_start, row.impact_window_end, row.budget_window_start, row.budget_window_end = start, end, budget_start, budget_end
            row.bad_event_count, row.impact_total_event_count, row.window_total_event_count = impact.bad, impact.total, window.total
            row.data_coverage_percent, row.budget_event_count, row.budget_share_percent = share.coverage_percent, share.budget_event_count, share.share_percent
            row.is_service_matched = is_service_matched
            row.impact_state, row.evaluated_at = impact_state_of(share.is_insufficient, resolved_at, now, self.settings.error_budget_policy_final_after_hours), now
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def _first_alert_at(self, incident_id: str) -> datetime | None:
        moment = await self.session.scalar(
            select(func.min(Alert.first_seen_at)).join(AlertGroup, Alert.alert_group_id == AlertGroup.alert_group_id).where(AlertGroup.incident_id == incident_id)
        )
        return ensure_utc(moment)

    async def _matching_slos(self, application_id: str, affected_service_ids: set[str]) -> list[tuple[ServiceLevelObjective, ServiceLevelIndicator, bool]]:
        """Enabled SLIs with an SLO, without supporting signals (as burn alerts). An affected service matches its own SLIs; an application-wide SLI matches every incident; an incident that
        names no service is matched against every SLO of the application. Only the first kind is a service match."""
        pairs = (await self.session.execute(
            select(ServiceLevelObjective, ServiceLevelIndicator).join(ServiceLevelIndicator, ServiceLevelIndicator.sli_id == ServiceLevelObjective.sli_id).where(
                ServiceLevelObjective.application_id == application_id, ServiceLevelIndicator.is_enabled.is_(True), ServiceLevelIndicator.sli_kind != SUPPORTING_SIGNAL_KIND,
            ).order_by(ServiceLevelIndicator.sli_name)
        )).all()
        matched: list[tuple[ServiceLevelObjective, ServiceLevelIndicator, bool]] = []
        for slo, sli in pairs:
            if sli.service_id is not None and sli.service_id in affected_service_ids:
                matched.append((slo, sli, True))
            elif sli.service_id is None or not affected_service_ids:
                matched.append((slo, sli, False))
        return matched

    async def totals(self, sli_id: str, start: datetime, end: datetime) -> MeasurementTotals:
        good, total, windows = (await self.session.execute(
            select(
                func.coalesce(func.sum(SliMeasurement.good_event_count), 0), func.coalesce(func.sum(SliMeasurement.total_event_count), 0),
                func.coalesce(func.sum(case((SliMeasurement.total_event_count > 0, 1), else_=0)), 0),
            ).where(SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start >= start, SliMeasurement.measurement_window_start < end, SliMeasurement.total_event_count.is_not(None))
        )).one()
        return MeasurementTotals(good=int(good), total=int(total), measured_window_count=int(windows))

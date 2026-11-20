"""Demo alert sources, noise policies, maintenance window, mute rule, historical alerts (through the real pipeline) and SLIs/SLOs with 30-day backfill, thinned to hourly rows before the newest days."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.alert_entities import Alert, AlertMuteRule, AlertSource, MaintenanceWindow, NoiseReductionPolicy
from keigan.entities.slo_entities import ServiceLevelIndicator, SliMeasurement
from keigan.entities.status_values import NoisePolicyMode
from keigan.seed.foundation_seed import SeedContext
from keigan.services import alert_rules
from keigan.services.alert_service import AlertService
from keigan.services.alert_source_service import hash_secret
from keigan.services.sli_measurement_reader import SliMeasurementReader
from keigan.services.sli_proposal_service import SliProposalService
from keigan.services.slo_service import SloService
from keigan.utils.time_utils import floor_to_interval

SEED_ORDER = 20
logger = logging.getLogger(__name__)
SYSTEM_ACTOR = "system:seed"
# The newest days keep one row per 5-minute window (the 1-hour and 6-hour burn windows and the dashboard read those). Older history is one row per hour.
DEMO_FINE_GRAINED_HISTORY_DAYS = 2


async def _ensure_source(session: AsyncSession, application_id: str, tool: str, name: str, service_mapping: dict | None = None) -> None:
    exists = await session.scalar(select(AlertSource.alert_source_id).where(AlertSource.application_id == application_id, AlertSource.source_tool == tool, AlertSource.source_name == name).limit(1))
    if exists is None:
        session.add(AlertSource(application_id=application_id, source_tool=tool, source_name=name, webhook_secret_hash=hash_secret(secrets.token_urlsafe(32)), service_mapping_json=service_mapping,
                                created_by_user_principal_name=SYSTEM_ACTOR, updated_by_user_principal_name=SYSTEM_ACTOR))


async def _seed_alert_configuration(session: AsyncSession, seed_context: SeedContext) -> None:
    now = alert_rules.utc_now()
    for code, application_id in seed_context.application_ids_by_code.items():
        await _ensure_source(session, application_id, "azure_monitor", "Azure Monitor")
        if code == "CHAD":
            await _ensure_source(session, application_id, "elastic", "Elastic (CHAD)", {"auto_match": True})
        if code == "PAYAU":
            await _ensure_source(session, application_id, "generic", "Datadog (generic webhook)", {"auto_match": True})
        if await session.get(NoiseReductionPolicy, application_id) is None:
            is_active = code == "CLMJP"
            session.add(NoiseReductionPolicy(
                application_id=application_id, policy_settings_json=dict(alert_rules.DEFAULT_NOISE_POLICY), policy_mode=NoisePolicyMode.ACTIVE if is_active else NoisePolicyMode.OBSERVE,
                observe_mode_started_at=now - timedelta(days=16 if is_active else 10), created_by_user_principal_name=SYSTEM_ACTOR, updated_by_user_principal_name=SYSTEM_ACTOR,
            ))
    await session.flush()
    clmjp_id = seed_context.application_ids_by_code.get("CLMJP")
    if clmjp_id and not await session.scalar(select(func.count()).select_from(MaintenanceWindow).where(MaintenanceWindow.application_id == clmjp_id)):
        days_since_friday = (now.weekday() - 4) % 7
        window_start = (now - timedelta(days=days_since_friday)).replace(hour=13, minute=0, second=0, microsecond=0)
        friday_release = MaintenanceWindow(
            application_id=clmjp_id, window_name="Friday release", applies_to_environments_json=["prod"],
            starts_at=window_start, ends_at=window_start + timedelta(minutes=90), repeats_weekly=True, created_by_user_principal_name=SYSTEM_ACTOR, updated_by_user_principal_name=SYSTEM_ACTOR,
        )
        friday_release.replace_linked_ids("service_links", [seed_context.service_id("CLMJP", "claims-nightly-etl")])
        session.add(friday_release)
    chad_id = seed_context.application_ids_by_code.get("CHAD")
    if chad_id and not await session.scalar(select(func.count()).select_from(AlertMuteRule).where(AlertMuteRule.application_id == chad_id)):
        session.add(AlertMuteRule(
            application_id=chad_id, rule_name="Known certificate warning", matcher_json={"rule_name_contains": "certificate"}, mute_reason="Certificate renewal is tracked in CHG0045512; alerts are noise until the renewal on the vendor side is done.",
            expires_at=now + timedelta(days=20), created_by_user_principal_name=SYSTEM_ACTOR, updated_by_user_principal_name=SYSTEM_ACTOR,
        ))
    await session.flush()


async def _seed_historical_alerts(session: AsyncSession, seed_context: SeedContext) -> None:
    alert_service = AlertService(session)
    for scenario_window in seed_context.historical_scenarios:
        application_id = scenario_window["application_id"]
        already_seeded = await session.scalar(select(func.count()).select_from(Alert).where(Alert.application_id == application_id, Alert.first_seen_at >= alert_rules.parse_timestamp(scenario_window["started_at"]) - timedelta(hours=1)))
        if already_seeded:
            continue
        await alert_service.simulate_alerts_for_scenario(application_id, scenario_window, replay_mode=True)
        await session.flush()


@dataclass
class _HourSummary:
    good: int | None
    total: int | None
    collected_at: datetime


def _sum_or_none(current: int | None, value: int | None) -> int | None:
    """Add two counts, where None means 'no count' (kept as None only when both sides are None)."""
    if value is None:
        return current
    return value if current is None else current + value


async def thin_older_measurements(session: AsyncSession, sli_id: str, now: datetime, fine_grained_days: int = DEMO_FINE_GRAINED_HISTORY_DAYS) -> int:
    """Replace the 5-minute rows older than ``fine_grained_days`` with one row per whole hour. Returns the number of hourly rows.

    Good and total counts are summed, so every reader that adds them up (error budget, burn rate, daily sums, hour-of-week buckets) gets
    the same answer as before. The measured value is dropped: a mean of 5-minute values is not a percentile, and nothing reads that column.
    """
    boundary = floor_to_interval(now - timedelta(days=fine_grained_days), 60)
    old_rows = (await session.execute(select(
        SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count, SliMeasurement.collected_at,
    ).where(SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start < boundary))).all()
    if not old_rows:
        return 0
    hours: dict[datetime, _HourSummary] = {}
    for window_start, good, total, collected_at in old_rows:
        hour = window_start.replace(minute=0, second=0, microsecond=0)
        summary = hours.setdefault(hour, _HourSummary(good=None, total=None, collected_at=collected_at))
        summary.good = _sum_or_none(summary.good, good)
        summary.total = _sum_or_none(summary.total, total)
        summary.collected_at = max(summary.collected_at, collected_at)
    await session.execute(delete(SliMeasurement).where(SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start < boundary))
    session.add_all(
        SliMeasurement(sli_id=sli_id, measurement_window_start=hour, good_event_count=summary.good, total_event_count=summary.total, measured_value=None, collected_at=summary.collected_at)
        for hour, summary in sorted(hours.items())
    )
    await session.flush()
    return len(hours)


async def _seed_slos(session: AsyncSession, seed_context: SeedContext) -> None:
    reader = SliMeasurementReader(session)
    proposal_service = SliProposalService(session, reader)
    slo_service = SloService(session, reader)
    for code, application_id in seed_context.application_ids_by_code.items():
        if await session.scalar(select(func.count()).select_from(ServiceLevelIndicator).where(ServiceLevelIndicator.application_id == application_id)):
            continue
        await proposal_service.measure(application_id)
        proposals = await proposal_service.get_proposals(application_id)
        accept_request = proposal_service.suggested_acceptance(proposals)
        if accept_request is None:
            logger.warning("No SLO proposals for %s", code)
            continue
        _, new_sli_ids = await proposal_service.accept(SYSTEM_ACTOR, application_id, accept_request, enqueue_backfill=False)
        for sli_id in new_sli_ids:
            await slo_service.backfill_sli(sli_id)
            await thin_older_measurements(session, sli_id, alert_rules.utc_now())
        await session.flush()
        logger.info("Seeded %s SLIs for %s", len(new_sli_ids), code)


async def seed(session: AsyncSession, seed_context: SeedContext) -> None:
    await _seed_alert_configuration(session, seed_context)
    await _seed_historical_alerts(session, seed_context)
    await _seed_slos(session, seed_context)

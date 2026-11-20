"""Demo alert sources, noise policies, maintenance window, mute rule, historical alerts (through the real pipeline) and SLIs/SLOs with 30-day backfill."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.entities.alert_entities import Alert, AlertMuteRule, AlertSource, MaintenanceWindow, NoiseReductionPolicy
from keigan.entities.slo_entities import ServiceLevelIndicator
from keigan.seed.foundation_seed import SeedContext
from keigan.services import alert_rules
from keigan.services.alert_service import AlertService
from keigan.services.alert_source_service import hash_secret
from keigan.services.sli_measurement_reader import SliMeasurementReader
from keigan.services.sli_proposal_service import SliProposalService
from keigan.services.slo_service import SloService

SEED_ORDER = 20
logger = logging.getLogger(__name__)
SYSTEM_ACTOR = "system:seed"


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
                application_id=application_id, policy_settings_json=dict(alert_rules.DEFAULT_NOISE_POLICY), policy_mode="active" if is_active else "observe",
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
        await session.flush()
        logger.info("Seeded %s SLIs for %s", len(new_sli_ids), code)


async def seed(session: AsyncSession, seed_context: SeedContext) -> None:
    await _seed_alert_configuration(session, seed_context)
    await _seed_historical_alerts(session, seed_context)
    await _seed_slos(session, seed_context)

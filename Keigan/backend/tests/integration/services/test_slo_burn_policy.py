"""keigan/services/slo_service.py: burn alerts follow the policy stored on each SLO, and the default pair when it has none (roadmap C2 gap)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement, SloBurnAlert
from keigan.services.slo_service import SAMPLE_INTERVAL_MINUTES, SloService

ERROR_BUDGET = 0.001  # a 99.9% target
BURN_RATE_OF_THE_DATA = 10.0  # every five minutes: 1,000 events, 990 good = a 1% error ratio = ten times the budget


async def _slo_burning_at_ten_times(seed_context: Any, policy: dict[str, Any] | None) -> tuple[str, str]:
    """One SLO of the PAYAU application whose last 7 hours all burn at a steady 10x. Returns the application id and the SLO id (other tests leave SLOs and alerts on the same application)."""
    application_id = seed_context.application_ids_by_code["PAYAU"]
    service_id = seed_context.service_id("PAYAU", next(key.split("/", 1)[1] for key in seed_context.service_ids_by_key if key.startswith("PAYAU/")))
    anchor = datetime.now(UTC).replace(second=0, microsecond=0, tzinfo=None)
    anchor -= timedelta(minutes=anchor.minute % SAMPLE_INTERVAL_MINUTES)
    async with open_session() as session:
        sli = ServiceLevelIndicator(
            application_id=application_id, service_id=service_id, catalog_entry_key="custom", sli_name="Pytest burn SLI", sli_kind="availability", data_source_kind="log_query",
            query_definition_json={"kql": "AppRequests | count"}, last_collected_window_start=anchor, created_by_user_principal_name="pytest", updated_by_user_principal_name="pytest",
        )
        session.add(sli)
        await session.flush()
        slo = ServiceLevelObjective(
            sli_id=sli.sli_id, application_id=application_id, target_percentage=100 * (1 - ERROR_BUDGET), burn_rate_policy_json=policy,
            created_by_user_principal_name="pytest", updated_by_user_principal_name="pytest",
        )
        session.add(slo)
        await session.flush()
        for step in range(7 * 60 // SAMPLE_INTERVAL_MINUTES):
            session.add(SliMeasurement(sli_id=sli.sli_id, measurement_window_start=anchor - timedelta(minutes=SAMPLE_INTERVAL_MINUTES * step), good_event_count=990, total_event_count=1000))
    return application_id, slo.slo_id


@pytest.fixture(autouse=True)
def no_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    """The alert groups and the notifications are other tests' business: here only which burn alerts fire."""
    async def nothing(*_arguments: object, **_keywords: object) -> None:
        return None

    monkeypatch.setattr(SloService, "_send_internal_alert", nothing)
    monkeypatch.setattr(SloService, "_notify", nothing)


async def _fired(ids: tuple[str, str]) -> set[str]:
    application_id, slo_id = ids
    async with open_session() as session:
        await SloService(session).evaluate_burn_rates(application_id)
    async with open_session() as session:
        return set((await session.scalars(select(SloBurnAlert.burn_alert_severity).where(SloBurnAlert.slo_id == slo_id, SloBurnAlert.resolved_at.is_(None)))).all())


async def test_an_slo_without_a_policy_uses_the_default_pair(seed_context) -> None:
    # 10x is below the default page threshold (14.4) and above the default ticket threshold (6).
    assert await _fired(await _slo_burning_at_ten_times(seed_context, None)) == {"ticket"}


async def test_a_stricter_policy_on_the_slo_makes_the_page_alert_fire(seed_context) -> None:
    policy = {"page": {"burnRate": 8, "longWindow": "PT1H", "shortWindow": "PT5M"}, "ticket": {"burnRate": 6, "longWindow": "PT6H", "shortWindow": "PT30M"}}
    assert await _fired(await _slo_burning_at_ten_times(seed_context, policy)) == {"page", "ticket"}


async def test_a_looser_policy_on_the_slo_keeps_the_ticket_alert_quiet(seed_context) -> None:
    policy = {"page": {"burnRate": 14.4, "longWindow": "PT1H", "shortWindow": "PT5M"}, "ticket": {"burnRate": 12, "longWindow": "PT6H", "shortWindow": "PT30M"}}
    assert await _fired(await _slo_burning_at_ten_times(seed_context, policy)) == set()


async def test_the_windows_of_the_policy_are_the_windows_that_are_measured(seed_context) -> None:
    # The data covers 7 hours; a 12-hour long window has fewer measurements than its share, so the burn rate over it is still 10x (a ratio), and a policy asking for it is honoured.
    policy = {"page": {"burnRate": 8, "longWindow": "PT12H", "shortWindow": "PT1H"}, "ticket": {"burnRate": 100, "longWindow": "PT6H", "shortWindow": "PT30M"}}
    assert await _fired(await _slo_burning_at_ten_times(seed_context, policy)) == {"page"}


async def test_an_unusable_policy_does_not_silence_the_alerts(seed_context) -> None:
    policy = {"page": {"burnRate": "fast", "longWindow": "soon", "shortWindow": "PT5M"}, "ticket": None}
    assert await _fired(await _slo_burning_at_ten_times(seed_context, policy)) == {"ticket"}

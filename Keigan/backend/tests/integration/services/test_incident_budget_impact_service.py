"""IncidentBudgetImpactService: what an incident cost each SLO's error budget, which SLOs count, and when the figure is provisional, final and frozen (spec 30, AC-5, AC-6, AC-8, AC-16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.error_budget_entities import IncidentBudgetImpact
from keigan.entities.incident_entities import Incident
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
from keigan.entities.status_values import IncidentBudgetImpactState as State
from keigan.services.incident_budget_impact_service import IncidentBudgetImpactService
from keigan.utils.statistics_utils import burn_rate
from support.application_graph import create_application_graph

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = NOW - timedelta(days=1)
DATA_START = NOW - timedelta(days=2)  # two days of data, so the one-day budget window of an incident that ended a few hours ago is fully measured
TRACKED = "tracked availability"  # the test SLI (the application graph has an SLI of its own, with no measurements)


async def add_measurements(sli_id: str, *, bad_between: tuple[datetime, datetime] | None = None, per_window_total: int = 100, bad_per_window: int = 10, every_window: bool = True) -> None:
    """Two days of 5-minute windows of ``per_window_total`` events; the windows inside ``bad_between`` have ``bad_per_window`` bad events."""
    async with open_session() as session:
        moment = DATA_START
        while moment < NOW:
            is_bad = bad_between is not None and bad_between[0] <= moment < bad_between[1]
            if every_window or moment.hour < 6:
                bad = bad_per_window if is_bad else 0
                session.add(SliMeasurement(sli_id=sli_id, measurement_window_start=moment, good_event_count=per_window_total - bad, total_event_count=per_window_total))
            moment += timedelta(minutes=5)


async def a_one_day_slo(sli_name: str = TRACKED, *, service_id: str | None = None, kind: str = "availability", application_id: str | None = None, target: float = 99.0) -> tuple[str, str]:
    """A new SLI and SLO with a one-day window on an application; returns (sli id, slo id)."""
    async with open_session() as session:
        sli = ServiceLevelIndicator(application_id=application_id, service_id=service_id, sli_name=sli_name, sli_kind=kind, data_source_kind="azure_monitor_metrics")
        session.add(sli)
        await session.flush()
        slo = ServiceLevelObjective(sli_id=sli.sli_id, application_id=application_id, target_percentage=target, rolling_window_days=1)
        session.add(slo)
        await session.flush()
        return sli.sli_id, slo.slo_id


async def an_incident(application_id: str, service_ids: list[str], *, opened_at: datetime, resolved_at: datetime | None) -> str:
    async with open_session() as session:
        incident = Incident(application_id=application_id, incident_title="Budget test", opened_at=opened_at, resolved_at=resolved_at, incident_status="resolved" if resolved_at else "investigating")
        incident.replace_linked_ids("affected_service_links", service_ids)
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def evaluate(incident_id: str, now: datetime) -> list[IncidentBudgetImpact]:
    async with open_session() as session:
        incident = await session.get(Incident, incident_id)
        await IncidentBudgetImpactService(session).evaluate(incident, now)
    async with open_session() as session:
        return await IncidentBudgetImpactService(session).impacts_of(incident_id)


async def test_an_incident_uses_the_share_of_the_budget_its_bad_events_cost(seed_context) -> None:
    graph = await create_application_graph()
    sli_id, _ = await a_one_day_slo(service_id=graph.first_service_id, application_id=graph.application_id)
    incident_start, incident_end = NOW - timedelta(hours=6), NOW - timedelta(hours=5)
    await add_measurements(sli_id, bad_between=(incident_start, incident_end))
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=incident_start, resolved_at=incident_end)
    (impact,) = [row for row in await evaluate(incident_id, NOW) if row.sli_name_text == TRACKED]
    # 12 windows of 10 bad events = 120 bad events. The day has 28,800 events; a 99 % target allows 288 bad ones: 120 / 288 = 41.7 %.
    assert impact.bad_event_count == 120 and impact.window_total_event_count == 28_800 and impact.budget_share_percent == 41.7
    assert impact.is_service_matched is True and impact.impact_state == State.PROVISIONAL and impact.data_coverage_percent == 100.0


async def test_with_full_coverage_the_share_equals_the_fall_in_budget_remaining_the_slo_page_shows(seed_context) -> None:
    graph = await create_application_graph()
    sli_id, _ = await a_one_day_slo(service_id=graph.first_service_id, application_id=graph.application_id)
    await add_measurements(sli_id, bad_between=(WINDOW_START, NOW))  # every bad event of the day is inside the incident
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=WINDOW_START, resolved_at=NOW)
    (impact,) = [row for row in await evaluate(incident_id, NOW) if row.sli_name_text == TRACKED]
    assert impact.budget_share_percent == round(burn_rate(good_event_count=25_920, total_event_count=28_800, target_percentage=99.0) * 100, 1)


async def test_too_few_measurements_state_no_share(seed_context) -> None:
    graph = await create_application_graph()
    sli_id, _ = await a_one_day_slo(service_id=graph.first_service_id, application_id=graph.application_id)
    await add_measurements(sli_id, every_window=False)  # only the first six hours were measured: 25 % coverage
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=NOW - timedelta(hours=6), resolved_at=NOW - timedelta(hours=5))
    (impact,) = [row for row in await evaluate(incident_id, NOW) if row.sli_name_text == TRACKED]
    assert impact.impact_state == State.INSUFFICIENT_DATA and impact.budget_share_percent is None and impact.data_coverage_percent == 25.0


async def test_the_figure_is_provisional_then_final_and_then_frozen(seed_context) -> None:
    graph = await create_application_graph()
    sli_id, _ = await a_one_day_slo(service_id=graph.first_service_id, application_id=graph.application_id)
    await add_measurements(sli_id, bad_between=(NOW - timedelta(hours=6), NOW - timedelta(hours=5)))
    resolved_at = NOW - timedelta(hours=5)
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=NOW - timedelta(hours=6), resolved_at=resolved_at)
    assert {row.impact_state for row in await evaluate(incident_id, resolved_at + timedelta(hours=1)) if row.sli_name_text == TRACKED} == {State.PROVISIONAL}
    after_a_day = resolved_at + timedelta(hours=25)
    finalised = [row for row in await evaluate(incident_id, after_a_day) if row.sli_name_text == TRACKED]
    assert finalised[0].impact_state == State.FINAL
    async with open_session() as session:  # late data arrives after the figure is final: it must not change
        late = await session.scalar(select(SliMeasurement).where(SliMeasurement.sli_id == sli_id, SliMeasurement.measurement_window_start == NOW - timedelta(hours=5, minutes=30)))
        late.good_event_count, late.total_event_count = 0, 5_000_000
    frozen = [row for row in await evaluate(incident_id, after_a_day + timedelta(hours=3)) if row.sli_name_text == TRACKED]
    assert frozen[0].budget_share_percent == finalised[0].budget_share_percent and frozen[0].evaluated_at == finalised[0].evaluated_at


async def test_only_the_slos_the_incident_can_have_affected_count(seed_context) -> None:
    graph = await create_application_graph()
    own_service, _ = await a_one_day_slo("own service", service_id=graph.first_service_id, application_id=graph.application_id)
    other_service, _ = await a_one_day_slo("other service", service_id=graph.second_service_id, application_id=graph.application_id)
    application_wide, _ = await a_one_day_slo("application wide", application_id=graph.application_id)
    supporting, _ = await a_one_day_slo("supporting", service_id=graph.first_service_id, kind="supporting_signal", application_id=graph.application_id)
    for sli_id in (own_service, other_service, application_wide, supporting):
        await add_measurements(sli_id)
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=NOW - timedelta(hours=2), resolved_at=NOW - timedelta(hours=1))
    impacts = {row.sli_name_text: row for row in await evaluate(incident_id, NOW)}
    assert {"own service", "application wide"} <= set(impacts)
    assert "other service" not in impacts and "supporting" not in impacts
    assert impacts["own service"].is_service_matched is True and impacts["application wide"].is_service_matched is False


async def test_an_incident_with_no_affected_service_is_matched_against_every_slo_of_the_application(seed_context) -> None:
    graph = await create_application_graph()
    first, _ = await a_one_day_slo("first", service_id=graph.first_service_id, application_id=graph.application_id)
    second, _ = await a_one_day_slo("second", service_id=graph.second_service_id, application_id=graph.application_id)
    for sli_id in (first, second):
        await add_measurements(sli_id)
    incident_id = await an_incident(graph.application_id, [], opened_at=NOW - timedelta(hours=2), resolved_at=NOW - timedelta(hours=1))
    impacts = {row.sli_name_text: row for row in await evaluate(incident_id, NOW)}
    assert {"first", "second"} <= set(impacts) and not impacts["first"].is_service_matched


async def test_deleting_an_slo_keeps_its_impacts_with_their_snapshot(seed_context) -> None:
    from keigan.services.reference_release import release_references

    graph = await create_application_graph()
    sli_id, slo_id = await a_one_day_slo(service_id=graph.first_service_id, application_id=graph.application_id)
    await add_measurements(sli_id)
    incident_id = await an_incident(graph.application_id, [graph.first_service_id], opened_at=NOW - timedelta(hours=2), resolved_at=NOW - timedelta(hours=1))
    await evaluate(incident_id, NOW)
    async with open_session() as session:
        await release_references(session, ServiceLevelObjective.slo_id, [slo_id])
        await session.delete(await session.get(ServiceLevelObjective, slo_id))
    async with open_session() as session:
        rows = (await session.scalars(select(IncidentBudgetImpact).where(IncidentBudgetImpact.incident_id == incident_id, IncidentBudgetImpact.sli_name_text == TRACKED))).all()
    assert len(rows) == 1 and rows[0].slo_id is None and rows[0].target_percentage == 99.0

"""keigan/seed/alert_and_slo_seed.py: demo SLI history keeps 5-minute rows for the newest days and one row per hour before that.

The readers only ever add up good and total counts (or bucket them by hour), so an hourly row holding the summed counts gives the same
answers as the twelve 5-minute rows it replaces. These tests check that the totals do not change, that the newest rows are untouched,
and that thinning is repeatable. The generated demo SQL is checked against the same rule in test_generate_demo_data_sql.py.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.slo_entities import ServiceLevelIndicator, SliMeasurement
from keigan.seed.alert_and_slo_seed import DEMO_FINE_GRAINED_HISTORY_DAYS, thin_older_measurements
from keigan.utils.time_utils import floor_to_interval

REFERENCE_TIME = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
BOUNDARY = floor_to_interval(REFERENCE_TIME - timedelta(days=DEMO_FINE_GRAINED_HISTORY_DAYS), 60)


async def _insert_sli_with_five_minute_history(seed_context, days: int) -> str:
    """One SLI with a 5-minute row for every window in the last ``days`` days. The counts vary from row to row so a wrong sum cannot pass."""
    async with open_session() as session:
        sli = ServiceLevelIndicator(
            application_id=seed_context.application_ids_by_code["CLMJP"], service_id=seed_context.service_id("CLMJP", "claims-api"),
            sli_name="Pytest thinning SLI", sli_kind="availability", data_source_kind="azure_monitor_metrics",
        )
        session.add(sli)
        await session.flush()
        first_window = REFERENCE_TIME - timedelta(days=days)
        rows = []
        for index in range(days * 288 + 1):
            total = 10 + index % 5
            good = total - (1 if index % 3 == 0 else 0)
            rows.append(SliMeasurement(
                sli_id=sli.sli_id, measurement_window_start=first_window + timedelta(minutes=5 * index), good_event_count=good, total_event_count=total,
                measured_value=0.25, collected_at=REFERENCE_TIME,
            ))
        session.add_all(rows)
        await session.flush()
        return sli.sli_id


async def _rows_by_window(sli_id: str) -> dict[datetime, tuple[int, int, float | None]]:
    async with open_session() as session:
        rows = (await session.execute(select(SliMeasurement.measurement_window_start, SliMeasurement.good_event_count, SliMeasurement.total_event_count, SliMeasurement.measured_value).where(SliMeasurement.sli_id == sli_id))).all()
    return {window: (good, total, value) for window, good, total, value in rows}


async def test_newest_rows_are_untouched_and_older_rows_become_one_row_per_hour(seed_context) -> None:
    sli_id = await _insert_sli_with_five_minute_history(seed_context, days=4)
    before = await _rows_by_window(sli_id)
    async with open_session() as session:
        await thin_older_measurements(session, sli_id, REFERENCE_TIME)
    after = await _rows_by_window(sli_id)

    assert {window: values for window, values in after.items() if window >= BOUNDARY} == {window: values for window, values in before.items() if window >= BOUNDARY}

    summed_by_hour: dict[datetime, list[int]] = defaultdict(lambda: [0, 0])
    for window, (good, total, _) in before.items():
        if window < BOUNDARY:
            summed_by_hour[window.replace(minute=0)][0] += good
            summed_by_hour[window.replace(minute=0)][1] += total
    assert {window: (good, total) for window, (good, total, _) in after.items() if window < BOUNDARY} == {hour: (good, total) for hour, (good, total) in summed_by_hour.items()}
    assert summed_by_hour, "the fixture must have old rows to thin"


async def test_thinning_keeps_every_total_the_readers_depend_on(seed_context) -> None:
    sli_id = await _insert_sli_with_five_minute_history(seed_context, days=4)
    before = await _rows_by_window(sli_id)
    async with open_session() as session:
        await thin_older_measurements(session, sli_id, REFERENCE_TIME)
    after = await _rows_by_window(sli_id)
    assert sum(good for good, _, _ in after.values()) == sum(good for good, _, _ in before.values())
    assert sum(total for _, total, _ in after.values()) == sum(total for _, total, _ in before.values())


async def test_hourly_rows_do_not_carry_a_measured_value_that_cannot_be_averaged(seed_context) -> None:
    sli_id = await _insert_sli_with_five_minute_history(seed_context, days=4)
    async with open_session() as session:
        await thin_older_measurements(session, sli_id, REFERENCE_TIME)
    after = await _rows_by_window(sli_id)
    assert all(value is None for window, (_, _, value) in after.items() if window < BOUNDARY)
    assert all(value == 0.25 for window, (_, _, value) in after.items() if window >= BOUNDARY)


async def test_running_it_twice_changes_nothing(seed_context) -> None:
    sli_id = await _insert_sli_with_five_minute_history(seed_context, days=4)
    async with open_session() as session:
        await thin_older_measurements(session, sli_id, REFERENCE_TIME)
    once = await _rows_by_window(sli_id)
    async with open_session() as session:
        await thin_older_measurements(session, sli_id, REFERENCE_TIME)
    assert await _rows_by_window(sli_id) == once



"""keigan/services/alert_pipeline_service.py: deduplication, lifecycle and decision records for incoming alerts."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import Alert, AlertDecision
from support.alerts import AlertSourceFixture, generic_alert_payload, post_alert
from support.jobs import drain_jobs


async def _alerts_for_rule(source: AlertSourceFixture, rule_id: str) -> list[Alert]:
    async with open_session() as session:
        return list((await session.scalars(select(Alert).where(Alert.alert_source_id == source.alert_source_id, Alert.rule_identifier == rule_id))).all())


async def test_repeat_of_a_firing_alert_increments_the_existing_alert(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    for _ in range(2):
        assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-repeat"))).status_code == 202
        await drain_jobs()

    alerts = await _alerts_for_rule(alert_source, "pipeline-repeat")
    assert len(alerts) == 1
    assert alerts[0].occurrence_count == 2


async def test_each_stage_records_its_decision(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-decisions"))).status_code == 202
    await drain_jobs()

    [alert] = await _alerts_for_rule(alert_source, "pipeline-decisions")
    async with open_session() as session:
        stages = set((await session.scalars(select(AlertDecision.pipeline_stage).where(AlertDecision.alert_id == alert.alert_id))).all())
    assert {"normalise", "deduplicate", "suppress"} <= stages


async def test_resolved_notification_closes_the_open_alert(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-resolve"))).status_code == 202
    await drain_jobs()
    assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-resolve", status="resolved"))).status_code == 202
    await drain_jobs()

    [alert] = await _alerts_for_rule(alert_source, "pipeline-resolve")
    assert alert.resolved_at is not None


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="H3: the database allows two open alerts with one fingerprint; dedup is an in-process lock")
async def test_database_rejects_a_second_open_alert_with_the_same_fingerprint(alert_source: AlertSourceFixture) -> None:
    fingerprint = uuid.uuid4().hex
    async with open_session() as session:
        session.add(Alert(application_id=alert_source.application_id, alert_fingerprint=fingerprint, rule_name="duplicate", alert_status="firing"))
    try:
        async with open_session() as session:
            session.add(Alert(application_id=alert_source.application_id, alert_fingerprint=fingerprint, rule_name="duplicate", alert_status="firing"))
    except IntegrityError:
        return
    raise AssertionError("a second open alert with the same fingerprint was stored")

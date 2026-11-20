"""keigan/controllers/alert_intake_controller.py: the public alert webhook and its credential checks."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import AlertEvent
from support.alerts import AlertSourceFixture, generic_alert_payload, post_alert


async def test_valid_token_stores_the_event_and_answers_202(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    response = await post_alert(client, alert_source, generic_alert_payload("intake-accepted"))
    assert response.status_code == 202
    event_id = response.json()["alertEventId"]
    async with open_session() as session:
        event = await session.get(AlertEvent, event_id)
    assert event is not None and event.processing_status == "received"


async def test_wrong_token_is_rejected_and_nothing_is_stored(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    async with open_session() as session:
        stored_before = await session.scalar(select(func.count()).select_from(AlertEvent).where(AlertEvent.alert_source_id == alert_source.alert_source_id))
    response = await post_alert(client, alert_source, generic_alert_payload("intake-wrong-token"), token="wrong-secret")
    assert response.status_code == 401
    async with open_session() as session:
        stored_after = await session.scalar(select(func.count()).select_from(AlertEvent).where(AlertEvent.alert_source_id == alert_source.alert_source_id))
    assert stored_after == stored_before


async def test_unknown_source_is_rejected_like_a_wrong_token(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/alerts/in/does-not-exist", json=generic_alert_payload("x"), headers={"X-Keigan-Token": "anything"})
    assert response.status_code == 401


async def test_body_that_is_not_a_json_object_is_rejected(client: httpx.AsyncClient, alert_source: AlertSourceFixture) -> None:
    response = await client.post(
        f"/api/alerts/in/{alert_source.alert_source_id}", content=b"[1, 2]", headers={"X-Keigan-Token": alert_source.webhook_secret, "Content-Type": "application/json"}
    )
    assert response.status_code == 422

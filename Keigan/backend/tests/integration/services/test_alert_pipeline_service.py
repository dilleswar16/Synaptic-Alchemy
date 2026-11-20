"""keigan/services/alert_pipeline_service.py: deduplication, lifecycle and decision records for incoming alerts."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from keigan.config.database_config import open_session
from keigan.entities.alert_entities import Alert, AlertDecision
from keigan.services.alert_pipeline_service import AlertPipelineService
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


async def test_database_allows_a_new_open_alert_once_the_earlier_one_is_resolved() -> None:
    fingerprint = uuid.uuid4().hex
    async with open_session() as session:
        session.add(Alert(application_id="app-for-history", alert_fingerprint=fingerprint, rule_name="history", alert_status="resolved"))
    async with open_session() as session:
        session.add(Alert(application_id="app-for-history", alert_fingerprint=fingerprint, rule_name="history", alert_status="firing"))


async def test_pod_that_loses_the_insert_race_counts_a_repeat_on_the_winning_alert(client: httpx.AsyncClient, alert_source: AlertSourceFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Another pod stored the alert between our lookup and our insert: the unique index rejects ours and we merge into theirs."""
    assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-race"))).status_code == 202
    assert (await post_alert(client, alert_source, generic_alert_payload("pipeline-race"))).status_code == 202
    original_find_alert = AlertPipelineService._find_alert
    lookups_seen = [0]

    async def second_lookup_is_stale(self, *arguments, **keyword_arguments):  # type: ignore[no-untyped-def]
        lookups_seen[0] += 1
        return None if lookups_seen[0] == 2 else await original_find_alert(self, *arguments, **keyword_arguments)

    monkeypatch.setattr(AlertPipelineService, "_find_alert", second_lookup_is_stale)
    await drain_jobs()

    [alert] = await _alerts_for_rule(alert_source, "pipeline-race")
    assert alert.occurrence_count == 2
    async with open_session() as session:
        repeat_decisions = (await session.scalars(select(AlertDecision).where(AlertDecision.alert_id == alert.alert_id, AlertDecision.decision_outcome == "repeat"))).all()
    assert len(repeat_decisions) == 1


async def test_group_title_prompt_tells_the_model_the_severity_of_the_alerts(alert_source: AlertSourceFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """The alert_group_title prompt promises the model severity; the pipeline must supply it."""
    from keigan.ai.alert_ai_schemas import AlertGroupTitleResult
    from keigan.config import application_context

    captured_sections: list[str] = []

    class RecordingGateway:
        async def generate_structured(self, **keyword_arguments):  # type: ignore[no-untyped-def]
            captured_sections.extend(section.content for section in keyword_arguments["prompt_sections"])
            return AlertGroupTitleResult(group_title="Checkout errors", group_summary="One alert on checkout.")

    monkeypatch.setattr(application_context, "llm_gateway", lambda: RecordingGateway())
    async with open_session() as session:
        pipeline = AlertPipelineService(session)
        context = await pipeline.load_context(alert_source.application_id)
        await pipeline._generate_title(context, ["claims-api"], ["Error rate high"], 1, highest_severity_level=1)  # noqa: SLF001
    assert any("Severity: Sev 1" in content for content in captured_sections), captured_sections

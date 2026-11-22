"""keigan/services/investigation_service.py: a manual investigation end to end on the mock LLM and simulated telemetry."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation, InvestigationEvidence, InvestigationHypothesis
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs


@pytest.fixture(scope="module")
async def completed_investigation_id(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> str:
    response = await client.post(
        "/api/investigations",
        headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Claim submissions are timing out for customers in Japan since 10:00."},
    )
    assert response.status_code == 202, response.text
    investigation_id = response.json()["jobId"]  # the accepted job id is the investigation id
    await drain_jobs()
    return investigation_id


async def test_investigation_completes_with_a_summary(completed_investigation_id: str) -> None:
    async with open_session() as session:
        investigation = await session.get(Investigation, completed_investigation_id)
    assert investigation is not None
    assert investigation.investigation_status == "completed", investigation.failure_reason
    assert investigation.executive_summary


async def test_investigation_has_one_hypothesis_per_perspective(completed_investigation_id: str) -> None:
    async with open_session() as session:
        perspectives = (await session.scalars(select(InvestigationHypothesis.analysis_perspective).where(InvestigationHypothesis.investigation_id == completed_investigation_id))).all()
    assert sorted(perspectives) == ["application", "dependencies", "infrastructure"]


async def test_investigation_collects_evidence(completed_investigation_id: str) -> None:
    async with open_session() as session:
        evidence_count = await session.scalar(select(func.count()).select_from(InvestigationEvidence).where(InvestigationEvidence.investigation_id == completed_investigation_id))
    assert evidence_count > 0


async def test_reader_of_the_application_can_open_the_investigation(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.get(f"/api/investigations/{completed_investigation_id}", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))
    assert response.status_code == 200


async def test_non_member_cannot_open_the_investigation(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.get(f"/api/investigations/{completed_investigation_id}", headers=await auth_headers(users.NO_ACCESS))
    assert response.status_code == 403


async def test_a_reader_cannot_mark_an_investigation_correct(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.post(f"/api/investigations/{completed_investigation_id}/feedback", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER), json={"verdict": "correct"})
    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


async def test_a_reader_can_still_say_an_investigation_was_incorrect(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.post(f"/api/investigations/{completed_investigation_id}/feedback", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER), json={"verdict": "incorrect", "comment": "Not the cause."})
    assert response.status_code == 200


async def test_an_application_admin_can_mark_an_investigation_correct(client: httpx.AsyncClient, auth_headers: AuthHeaders, completed_investigation_id: str) -> None:
    response = await client.post(f"/api/investigations/{completed_investigation_id}/feedback", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"verdict": "correct"})
    assert response.status_code == 200
    assert response.json()["investigationId"] == completed_investigation_id


async def test_a_manual_investigation_window_longer_than_the_maximum_is_rejected_with_a_clear_message(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    response = await client.post(
        "/api/investigations", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Looking at five years of data.", "windowStart": "2021-01-01T00:00:00Z", "windowEnd": "2026-01-01T00:00:00Z"},
    )
    assert response.status_code == 422
    assert "at most 240 minutes" in response.json()["detail"]
    assert response.json()["fieldErrors"][0]["field"] == "windowEnd"


async def test_a_manual_investigation_window_within_the_maximum_is_accepted(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    response = await client.post(
        "/api/investigations", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Looking at the last two hours.", "windowStart": "2026-11-20T08:00:00Z", "windowEnd": "2026-11-20T10:00:00Z"},
    )
    assert response.status_code == 202, response.text


async def test_a_failed_investigation_shows_users_no_internal_error_text(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    from keigan.ai import investigation_graph
    from keigan.config.logging_config import set_correlation_id
    from keigan.services.investigation_service import InvestigationService

    async def explode(self: object) -> dict:
        raise RuntimeError("connection to sql-prod-01.internal.corp:1433 refused (password=hunter2)")

    monkeypatch.setattr(investigation_graph.InvestigationGraphRunner, "run", explode)
    set_correlation_id("corr-fail-42")
    async with open_session() as session:
        investigation_id = await InvestigationService(session).start_investigation(seed_context.application_ids_by_code["CLMJP"], "manual", description="This run will fail on purpose.")
    async with open_session() as session:
        await InvestigationService(session).run_investigation(investigation_id)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
    assert investigation.investigation_status == "failed"
    assert "internal.corp" not in investigation.failure_reason and "hunter2" not in investigation.failure_reason and "RuntimeError" not in investigation.failure_reason
    assert "corr-fail-42" in investigation.failure_reason


async def test_the_alert_group_on_an_investigation_carries_the_structured_grouping_reason(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    """The investigation page shows the same translated sentence as the Alerts page, so it needs the code and parameters, not the stored English string."""
    from keigan.entities.alert_entities import Alert, AlertGroup, AlertSource

    application_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        investigation = Investigation(application_id=application_id)
        session.add(investigation)
        source = AlertSource(application_id=application_id, source_tool="generic", source_name="grouping test source", webhook_secret_hash="hash")
        session.add(source)
        await session.flush()
        group = AlertGroup(application_id=application_id, group_title="Grouping test", investigation_id=investigation.investigation_id, grouping_reason="Stored English text that must not be shown")
        session.add(group)
        await session.flush()
        session.add(Alert(application_id=application_id, alert_source_id=source.alert_source_id, alert_fingerprint="grouping-test", rule_name="rule", alert_group_id=group.alert_group_id))
        investigation_id = investigation.investigation_id
    response = await client.get(f"/api/investigations/{investigation_id}", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))
    assert response.status_code == 200, response.text
    reason = response.json()["alertGroup"]["groupingReason"]
    assert reason == {"code": "single_alert", "parameters": {}}

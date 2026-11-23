"""GET /api/investigations/{id}/trace and its raw-output step: who may read what (spec 28, AC-10, AC-11, AC-15)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import delete, select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import InvestigationTraceStep
from keigan.entities.platform_entities import LlmUsageRecord
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs

READER, APP_ADMIN, KEIGAN_ADMIN, OUTSIDER = users.CLMJP_AND_PAYAU_READER, users.CLMJP_ADMIN_CHAD_READER, users.KEIGAN_ADMIN, users.NO_ACCESS


@pytest.fixture(scope="module")
async def investigation_id(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> str:
    response = await client.post(
        "/api/investigations", headers=await auth_headers(APP_ADMIN),
        json={"applicationId": seed_context.application_ids_by_code["CLMJP"], "description": "Claim submissions are timing out for customers in Japan since 10:00."},
    )
    assert response.status_code == 202, response.text
    await drain_jobs()
    return response.json()["jobId"]


async def get_trace(client: httpx.AsyncClient, auth_headers: AuthHeaders, user: str, investigation_id: str) -> httpx.Response:
    return await client.get(f"/api/investigations/{investigation_id}/trace", headers=await auth_headers(user))


async def a_trace_step_id(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str, feature_name: str = "rca_synthesis") -> str:
    steps = (await get_trace(client, auth_headers, READER, investigation_id)).json()["steps"]
    return next(step["traceStepId"] for step in steps if step["aiCall"] and step["aiCall"]["featureName"] == feature_name)


async def test_a_reader_of_the_application_reads_the_trace_in_order(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    response = await get_trace(client, auth_headers, READER, investigation_id)
    assert response.status_code == 200, response.text
    trace = response.json()
    assert trace["isRecorded"] is True and trace["isComplete"] is True and trace["status"] == "completed" and trace["pipelineVersion"]
    assert [step["sequenceNumber"] for step in trace["steps"]] == list(range(1, len(trace["steps"]) + 1))
    assert trace["steps"][0]["stepKind"] == "inputs" and trace["steps"][-1]["stepKind"] == "outcome"
    synthesis = next(step["aiCall"] for step in trace["steps"] if step["aiCall"] and step["aiCall"]["featureName"] == "rca_synthesis")
    assert synthesis["promptVersion"] == "5" and len(synthesis["promptTemplateSha256"]) == 64 and synthesis["hasRawOutput"] is True
    assert synthesis["inputSections"] and "content" not in synthesis["inputSections"][0] and synthesis["tokenCountsEstimated"] is True
    assert trace["totals"]["aiCallCount"] >= 5 and trace["totals"]["inputTokenCount"] > 0 and trace["outcome"]["code"] in {"cause_identified", "inconclusive", "cause_not_visible"}
    assert {item["promptKey"] for item in trace["prompts"]} >= {"rca_synthesis", "incident_triage"}


async def test_the_raw_answer_is_not_part_of_the_trace_a_reader_receives(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    steps = (await get_trace(client, auth_headers, READER, investigation_id)).json()["steps"]
    assert all("rawOutput" not in step["aiCall"] for step in steps if step["aiCall"]), "only the size and the fact that a raw answer exists are part of the trace"


async def test_a_person_without_access_a_missing_investigation_are_refused(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    assert (await get_trace(client, auth_headers, OUTSIDER, investigation_id)).status_code == 403
    assert (await get_trace(client, auth_headers, READER, "no-such-investigation")).status_code == 404


async def test_an_application_admin_and_a_keigan_admin_read_a_raw_answer(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    step_id = await a_trace_step_id(client, auth_headers, investigation_id)
    for user in (APP_ADMIN, KEIGAN_ADMIN):
        response = await client.get(f"/api/investigations/{investigation_id}/trace/steps/{step_id}/raw-output", headers=await auth_headers(user))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rawOutput"] and body["characterCount"] > 0 and body["isTruncated"] is False and len(body["sha256"]) == 64


async def test_a_reader_who_is_not_an_admin_cannot_read_a_raw_answer(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    step_id = await a_trace_step_id(client, auth_headers, investigation_id)
    response = await client.get(f"/api/investigations/{investigation_id}/trace/steps/{step_id}/raw-output", headers=await auth_headers(READER))
    assert response.status_code == 403 and "admin" in response.text.lower()


async def test_a_step_that_is_not_an_ai_call_or_does_not_exist_has_no_raw_answer(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    steps = (await get_trace(client, auth_headers, READER, investigation_id)).json()["steps"]
    inputs_step_id = steps[0]["traceStepId"]
    for step_id in (inputs_step_id, "no-such-step"):
        response = await client.get(f"/api/investigations/{investigation_id}/trace/steps/{step_id}/raw-output", headers=await auth_headers(APP_ADMIN))
        assert response.status_code == 404


async def test_an_investigation_from_before_traces_returns_what_can_be_rebuilt(client: httpx.AsyncClient, auth_headers: AuthHeaders, investigation_id: str) -> None:
    async with open_session() as session:
        steps = list((await session.scalars(select(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id))).all())
        saved = [(step.__dict__.copy()) for step in steps]
        await session.execute(delete(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id))
        session.add(LlmUsageRecord(investigation_id=investigation_id, feature_name="rca_synthesis", provider_name="gemini", model_name="m-old", model_tier="deep", input_token_count=900, output_token_count=80, outcome_status="succeeded"))
    try:
        trace = (await get_trace(client, auth_headers, READER, investigation_id)).json()
        assert trace["isRecorded"] is False and trace["steps"] == []
        assert trace["callsWithoutStep"][0]["featureName"] == "rca_synthesis" and trace["totals"]["inputTokenCount"] == 900
    finally:
        async with open_session() as session:
            await session.execute(delete(LlmUsageRecord).where(LlmUsageRecord.investigation_id == investigation_id))
            for values in saved:
                session.add(InvestigationTraceStep(**{key: value for key, value in values.items() if not key.startswith("_")}))

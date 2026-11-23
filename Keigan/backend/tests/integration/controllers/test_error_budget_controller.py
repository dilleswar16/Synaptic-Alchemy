"""/api/incidents/{id}/budget-impact and the evaluation job: who may read, what is shown with the policy off, and the triggers (spec 30, AC-1, AC-17)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicy
from keigan.entities.incident_entities import Incident
from keigan.entities.platform_entities import BackgroundJob
from keigan.entities.status_values import ApplicationLifecycleStatus
from keigan.services.error_budget_policy_service import EVALUATION_JOB_TYPE, ErrorBudgetPolicyService
from keigan.workers.schedulers import enqueue_error_budget_policy
from support import users
from support.application_graph import create_application_graph
from support.http import AuthHeaders

READER, APP_ADMIN, OUTSIDER = users.CLMJP_AND_PAYAU_READER, users.CLMJP_ADMIN_CHAD_READER, users.NO_ACCESS


async def a_clmjp_incident_with_an_slo(seed_context) -> str:
    """The seeded Claims application already has SLIs and SLOs; a fresh incident that names no service is matched against all of them."""
    async with open_session() as session:
        incident = Incident(application_id=seed_context.application_ids_by_code["CLMJP"], incident_title="Budget endpoint test", opened_at=datetime.now(UTC) - timedelta(hours=2), incident_status="investigating")
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def test_impacts_are_computed_and_shown_with_the_policy_off_and_reading_writes_no_policy(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:  # the graph's own SLI has no measurements, so its impact says "not enough data"
        incident = Incident(application_id=graph.application_id, incident_title="Budget endpoint test", opened_at=datetime.now(UTC) - timedelta(hours=2), incident_status="investigating")
        session.add(incident)
        await session.flush()
        incident_id = incident.incident_id
    async with open_session() as session:
        counts = await ErrorBudgetPolicyService(session).evaluate_application(graph.application_id)
    assert counts["incidents"] >= 1
    response = await client.get(f"/api/incidents/{incident_id}/budget-impact", headers=await auth_headers(users.KEIGAN_ADMIN))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["incidentId"] == incident_id and body["policy"]["isEnabled"] is False and body["policy"]["singleIncidentThresholdPercent"] == 20.0
    assert body["impacts"] and all(impact["impactState"] == "insufficient_data" and impact["budgetSharePercent"] is None for impact in body["impacts"])
    async with open_session() as session:  # AC-1: reading writes no row
        policy_count_before = len((await session.scalars(select(ErrorBudgetPolicy))).all())
    await client.get(f"/api/incidents/{incident_id}/budget-impact", headers=await auth_headers(users.KEIGAN_ADMIN))
    async with open_session() as session:
        assert len((await session.scalars(select(ErrorBudgetPolicy))).all()) == policy_count_before


async def test_a_reader_of_another_application_is_refused_and_an_unknown_incident_is_not_found(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    incident_id = await a_clmjp_incident_with_an_slo(seed_context)
    assert (await client.get(f"/api/incidents/{incident_id}/budget-impact", headers=await auth_headers(OUTSIDER))).status_code == 403
    assert (await client.get("/api/incidents/does-not-exist/budget-impact", headers=await auth_headers(READER))).status_code == 404


async def test_the_schedule_queues_one_evaluation_per_live_application_with_slos_and_resolving_an_incident_queues_one(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    graph = await create_application_graph()  # has an SLO
    async with open_session() as session:
        (await session.get(Application, graph.application_id)).lifecycle_status = ApplicationLifecycleStatus.LIVE
    async with open_session() as session:
        await enqueue_error_budget_policy(session)
        await enqueue_error_budget_policy(session)
        jobs = [job for job in (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == EVALUATION_JOB_TYPE))).all() if job.job_payload_json.get("application_id") == graph.application_id]
    assert len(jobs) == 1


async def test_resolving_an_incident_queues_an_evaluation_for_its_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    incident_id = await a_clmjp_incident_with_an_slo(seed_context)
    response = await client.post(f"/api/incidents/{incident_id}/resolve", headers=await auth_headers(APP_ADMIN), json={"resolutionNote": "Fixed.", "generatePostmortem": False})
    assert response.status_code == 200, response.text
    application_id = seed_context.application_ids_by_code["CLMJP"]
    async with open_session() as session:
        jobs = [job for job in (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == EVALUATION_JOB_TYPE))).all() if job.job_payload_json.get("application_id") == application_id]
    assert jobs

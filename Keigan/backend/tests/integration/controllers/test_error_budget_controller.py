"""/api/incidents/{id}/budget-impact and the evaluation job: who may read, what is shown with the policy off, and the triggers (spec 30, AC-1, AC-17)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
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


@pytest.fixture(autouse=True)
async def remove_the_applications_these_tests_create(seed_context):
    """The application graphs these tests make are visible to Keigan admins: later tests that count applications must not see them."""
    yield
    from keigan.security.current_user import CurrentUser
    from keigan.services.application_service import ApplicationService

    async with open_session() as session:
        graph_ids = list((await session.scalars(select(Application.application_id).where(Application.application_code.like("GRF%")))).all())
    for application_id in graph_ids:
        async with open_session() as session:
            admin = CurrentUser(user_principal_name="cleanup@example.com", display_name="Cleanup", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)
            (await session.get(Application, application_id)).lifecycle_status = ApplicationLifecycleStatus.DRAFT  # a live application cannot be deleted
            await session.flush()
            await ApplicationService(session).delete_application(admin, application_id)


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


# ── The policy and the breaches ──────────────────────────────────────────────────────────────────


async def test_the_policy_reads_as_off_with_defaults_until_an_admin_saves_it(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application_id = seed_context.application_ids_by_code["PAYAU"]
    before = (await client.get(f"/api/applications/{application_id}/error-budget-policy", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))).json()
    assert before["isEnabled"] is False and before["usesDefault"]["singleIncidentThreshold"] is True and before["singleIncidentThresholdPercent"] == 20.0 and before["maximumOutageClassWindowDays"] == 90 and before["canEdit"] is False
    forbidden = await client.put(f"/api/applications/{application_id}/error-budget-policy", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER), json={"isEnabled": True})
    assert forbidden.status_code == 403
    assert (await client.get(f"/api/applications/{application_id}/error-budget-policy", headers=await auth_headers(users.NO_ACCESS))).status_code == 403


async def test_an_admin_saves_the_policy_with_validation_and_the_guidance_is_sanitised(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    url = f"/api/applications/{application_id}/error-budget-policy"
    bad = await client.put(url, headers=await auth_headers(APP_ADMIN), json={"isEnabled": True, "singleIncidentThresholdPercent": 0, "outageClassWindowDays": 400})
    assert bad.status_code == 422 and {error["field"] for error in bad.json()["fieldErrors"]} >= {"singleIncidentThresholdPercent", "outageClassWindowDays"}
    saved = await client.put(url, headers=await auth_headers(APP_ADMIN), json={
        "isEnabled": True, "singleIncidentThresholdPercent": 25, "outageClassThresholdPercent": None, "outageClassWindowDays": 60,
        "exhaustedBudgetGuidanceText": "Pause feature releases. [click](https://evil.example/x) <script>alert(1)</script>",
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["isEnabled"] is True and body["singleIncidentThresholdPercent"] == 25.0 and body["usesDefault"] == {"singleIncidentThreshold": False, "outageClassThreshold": True, "outageClassWindow": False}
    guidance = body["exhaustedBudgetGuidanceText"]  # links become plain text and markup is escaped, so nothing can run when it is shown or emailed
    assert "[click](" not in guidance and "\<script>" in guidance and "Pause feature releases" in guidance
    assert body["canEdit"] is True and body["updatedBy"] == APP_ADMIN
    again = await client.get(url, headers=await auth_headers(READER))
    assert again.json()["singleIncidentThresholdPercent"] == 25.0 and again.json()["canEdit"] is False


async def test_finalising_a_postmortem_follows_the_policy_end_to_end(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    from datetime import timedelta as delta

    from keigan.entities.error_budget_entities import ErrorBudgetPolicy
    from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
    from keigan.services.communication_service import CommunicationService
    from keigan.utils.time_utils import floor_to_interval, utc_now
    from support.jobs import drain_jobs

    graph = await create_application_graph()
    end = floor_to_interval(utc_now(), 5)
    async with open_session() as session:
        sli = ServiceLevelIndicator(application_id=graph.application_id, service_id=graph.first_service_id, sli_name="tracked availability", sli_kind="availability", data_source_kind="azure_monitor_metrics")
        session.add(sli)
        await session.flush()
        session.add(ServiceLevelObjective(sli_id=sli.sli_id, application_id=graph.application_id, target_percentage=99.0, rolling_window_days=1))
        moment = end - delta(days=3)
        while moment < end:
            bad = 10 if end - delta(hours=3) <= moment < end - delta(hours=2) else 0
            session.add(SliMeasurement(sli_id=sli.sli_id, measurement_window_start=moment, good_event_count=100 - bad, total_event_count=100))
            moment += delta(minutes=5)
        incident = Incident(application_id=graph.application_id, incident_title="Gate test", opened_at=end - delta(hours=4), resolved_at=end - delta(hours=2), incident_status="resolved")
        incident.replace_linked_ids("affected_service_links", [graph.first_service_id])
        session.add(incident)
        await session.execute(ErrorBudgetPolicy.__table__.update().where(ErrorBudgetPolicy.application_id == graph.application_id).values(is_enabled=True))
        await session.flush()
        incident_id = incident.incident_id
    async with open_session() as session:
        await ErrorBudgetPolicyService(session).evaluate_application(graph.application_id, now=utc_now() + delta(hours=23))
    admin = await auth_headers(users.KEIGAN_ADMIN)
    impact = (await client.get(f"/api/incidents/{incident_id}/budget-impact", headers=admin)).json()
    assert impact["breach"]["breachKind"] == "single_incident" and impact["breach"]["isProvisional"] is False and impact["breach"]["requirementStatus"] == "open"
    async with open_session() as session:
        sections = await CommunicationService(session)._error_budget_sections(incident_id)
    assert [section.title for section in sections] == ["Error budget impact", "Error budget policy"] and "41.7" in sections[0].content
    assert (await client.post(f"/api/incidents/{incident_id}/postmortem/generate", headers=admin)).status_code == 202
    await drain_jobs()
    postmortem_id = (await client.get(f"/api/incidents/{incident_id}/postmortem", headers=admin)).json()["postmortemId"]
    items = (await client.get(f"/api/postmortems/{postmortem_id}/action-items", headers=admin)).json()
    top_item = next(item for item in items if item["actionPriority"] == "top")
    assert top_item["actionType"] == "prevent"  # the mock writer follows the policy prompt
    for item in items:
        if item is not top_item:
            await client.delete(f"/api/action-items/{item['actionItemId']}", headers=admin)
    refused = await client.post(f"/api/postmortems/{postmortem_id}/finalize", headers=admin)
    assert refused.status_code == 422 and "actionItems" in refused.text  # the suggestion is not accepted yet
    assert (await client.post(f"/api/action-items/{top_item['actionItemId']}/accept", headers=admin)).status_code == 200
    assert (await client.post(f"/api/postmortems/{postmortem_id}/finalize", headers=admin)).status_code == 200
    met = (await client.get(f"/api/error-budget-breaches?applicationIds={graph.application_id}&statuses=met", headers=admin)).json()
    ours = next(breach for breach in met if breach["incidentId"] == incident_id)  # (the application graph has a met breach of its own)
    assert ours["qualifyingActionItemId"] == top_item["actionItemId"]
    assert (await client.get(f"/api/error-budget-breaches?applicationIds={graph.application_id}", headers=admin)).json() == []  # no longer open
    assert (await client.post(f"/api/error-budget-breaches/{ours['breachId']}/waive", headers=await auth_headers(READER), json={"reasonText": "A reader cannot waive anything at all."})).status_code == 403

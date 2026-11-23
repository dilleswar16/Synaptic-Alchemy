"""Runbook findings (spec 32) are shown where a runbook is weighed: on the application list and next to a runbook an investigation matched."""

from __future__ import annotations

import httpx

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation
from keigan.services.runbook_health_service import RunbookHealthService
from support import users
from support.ask_keigan_tool_data import add_runbook
from support.http import AuthHeaders


async def attention_of(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> int:
    response = await client.get("/api/applications", headers=await auth_headers(users.KEIGAN_ADMIN))
    assert response.status_code == 200, response.text
    return next(item["runbookAttentionCount"] for item in response.json() if item["applicationId"] == application_id)


async def test_the_application_list_counts_the_runbooks_with_a_finding(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application_id = seed_context.application_ids_by_code["PAYAU"]
    async with open_session() as session:
        expected = sum(1 for row in await RunbookHealthService(session).rows(application_id) if row.findings)
    assert await attention_of(client, auth_headers, application_id) == expected
    await add_runbook(application_id, "A runbook with no steps", "timeouts", "")  # a finding of its own: no steps
    assert await attention_of(client, auth_headers, application_id) == expected + 1


async def test_a_matched_runbook_carries_what_is_wrong_with_it(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    runbook_id = await add_runbook(application_id, "Matched but empty", "timeouts", "")
    healthy_id = await add_runbook(application_id, "Matched and complete", "timeouts", "1. Restart the pool.")
    async with open_session() as session:
        investigation = Investigation(application_id=application_id, investigation_status="completed")
        investigation.replace_linked_ids("matched_runbook_links", [runbook_id, healthy_id])
        session.add(investigation)
        await session.flush()
        investigation_id = investigation.investigation_id
    response = await client.get(f"/api/investigations/{investigation_id}", headers=await auth_headers(users.KEIGAN_ADMIN))
    assert response.status_code == 200, response.text
    by_id = {runbook["runbookId"]: runbook for runbook in response.json()["matchedRunbooks"]}
    assert "no_steps" in by_id[runbook_id]["findingKinds"]
    assert "no_steps" not in by_id[healthy_id]["findingKinds"]

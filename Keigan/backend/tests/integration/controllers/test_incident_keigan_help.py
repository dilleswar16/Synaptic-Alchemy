"""POST /api/incidents/{id}/resolve takes the resolver's answer to "how did Keigan's analysis help?", and the incident shows it."""

from __future__ import annotations

import httpx

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Incident
from support import users
from support.http import AuthHeaders

APP_ADMIN = users.CLMJP_ADMIN_CHAD_READER


async def an_open_incident(seed_context) -> str:  # noqa: ANN001
    async with open_session() as session:
        incident = Incident(application_id=seed_context.application_ids_by_code["CLMJP"], incident_title="Answer test", incident_status="investigating")
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def resolve(client: httpx.AsyncClient, auth_headers: AuthHeaders, incident_id: str, **body) -> httpx.Response:
    return await client.post(f"/api/incidents/{incident_id}/resolve", headers=await auth_headers(APP_ADMIN), json={"generatePostmortem": False, **body})


async def test_the_answer_given_when_resolving_is_stored_and_shown(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    incident_id = await an_open_incident(seed_context)
    response = await resolve(client, auth_headers, incident_id, keiganHelp="found_cause")
    assert response.status_code == 200, response.text
    assert response.json()["keiganHelp"] == "found_cause"
    detail = await client.get(f"/api/incidents/{incident_id}", headers=await auth_headers(APP_ADMIN))
    assert detail.json()["keiganHelp"] == "found_cause"
    async with open_session() as session:
        assert (await session.get(Incident, incident_id)).keigan_help == "found_cause"


async def test_resolving_without_an_answer_leaves_it_empty(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    incident_id = await an_open_incident(seed_context)
    response = await resolve(client, auth_headers, incident_id)
    assert response.status_code == 200, response.text
    assert response.json()["keiganHelp"] is None


async def test_a_word_outside_the_four_answers_is_refused_and_the_incident_stays_open(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    incident_id = await an_open_incident(seed_context)
    response = await resolve(client, auth_headers, incident_id, keiganHelp="solved_everything")
    assert response.status_code == 422, response.text
    async with open_session() as session:
        assert (await session.get(Incident, incident_id)).incident_status == "investigating"

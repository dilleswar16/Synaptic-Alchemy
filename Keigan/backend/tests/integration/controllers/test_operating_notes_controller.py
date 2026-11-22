"""keigan/controllers/operating_notes_controller.py: GET and PUT /api/applications/{applicationId}/operating-notes through the real API."""

from __future__ import annotations

import httpx

from keigan.config.settings import get_settings
from support import users
from support.http import AuthHeaders
from support.telemetry_scope import create_scoped_application


def notes_url(application_id: str) -> str:
    return f"/api/applications/{application_id}/operating-notes"


async def test_a_keigan_admin_saves_and_the_notes_read_back_in_camel_case(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application = await create_scoped_application()
    url = notes_url(application.application_id)
    saved = await client.put(url, headers=await auth_headers(users.KEIGAN_ADMIN), json={"text": "  Orders carries revenue.  "})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["text"] == "Orders carries revenue." and body["maximumCharacters"] == get_settings().application_operating_notes_maximum_characters
    assert body["updatedBy"] == users.KEIGAN_ADMIN and body["updatedAt"]
    assert set(body) == {"text", "maximumCharacters", "updatedAt", "updatedBy"}
    assert (await client.get(url, headers=await auth_headers(users.KEIGAN_ADMIN))).json() == body


async def test_a_reader_can_read_but_not_change_the_notes(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    url = notes_url(seed_context.application_ids_by_code["CHAD"])
    reader_headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)  # a reader of CHAD
    assert (await client.get(url, headers=reader_headers)).status_code == 200
    refused = await client.put(url, headers=reader_headers, json={"text": "x"})
    assert refused.status_code == 403
    assert refused.headers["content-type"].startswith("application/problem+json")


async def test_an_application_admin_who_is_not_a_keigan_admin_can_change_the_notes(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    url = notes_url(seed_context.application_ids_by_code["CLMJP"])
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    original = (await client.get(url, headers=headers)).json()["text"]
    try:
        response = await client.put(url, headers=headers, json={"text": "Temporary note from a test."})
        assert response.status_code == 200 and response.json()["updatedBy"] == users.CLMJP_ADMIN_CHAD_READER
    finally:
        await client.put(url, headers=headers, json={"text": original})


async def test_someone_with_no_access_gets_403_for_both_calls(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    url = notes_url(seed_context.application_ids_by_code["CLMJP"])
    headers = await auth_headers(users.NO_ACCESS)
    assert (await client.get(url, headers=headers)).status_code == 403
    assert (await client.put(url, headers=headers, json={"text": "x"})).status_code == 403


async def test_a_request_without_a_token_is_refused(client: httpx.AsyncClient, seed_context) -> None:
    assert (await client.get(notes_url(seed_context.application_ids_by_code["CLMJP"]))).status_code == 401


async def test_notes_over_the_limit_are_refused_with_a_field_error_and_nothing_changes(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application = await create_scoped_application()
    url = notes_url(application.application_id)
    headers = await auth_headers(users.KEIGAN_ADMIN)
    maximum = get_settings().application_operating_notes_maximum_characters
    refused = await client.put(url, headers=headers, json={"text": "x" * (maximum + 1)})
    assert refused.status_code == 422
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert refused.json()["fieldErrors"] == [{"field": "text", "message": f"Operating notes can have at most {maximum} characters; these have {maximum + 1}."}]
    assert (await client.get(url, headers=headers)).json()["text"] == ""


async def test_an_empty_value_clears_the_notes(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    application = await create_scoped_application()
    url = notes_url(application.application_id)
    headers = await auth_headers(users.KEIGAN_ADMIN)
    await client.put(url, headers=headers, json={"text": "Something."})
    cleared = await client.put(url, headers=headers, json={"text": "   "})
    assert cleared.status_code == 200 and cleared.json()["text"] == ""


async def test_a_body_without_text_or_with_a_non_string_is_a_validation_error(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    url = notes_url((await create_scoped_application()).application_id)
    headers = await auth_headers(users.KEIGAN_ADMIN)
    assert (await client.put(url, headers=headers, json={})).status_code == 422
    assert (await client.put(url, headers=headers, json={"text": None})).status_code == 422
    assert (await client.put(url, headers=headers, json={"text": 12})).status_code == 422


async def test_an_unknown_application_is_404(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    assert (await client.get(notes_url("00000000-0000-0000-0000-000000000000"), headers=await auth_headers(users.KEIGAN_ADMIN))).status_code == 404

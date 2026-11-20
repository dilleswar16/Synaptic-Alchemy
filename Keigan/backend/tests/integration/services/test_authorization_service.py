"""keigan/services/authorization_service.py: reader, admin and Keigan-admin checks as enforced on real routes."""

from __future__ import annotations

import httpx

from support.http import AuthHeaders
from support import users

UNKNOWN_APPLICATION_ID = "00000000-0000-0000-0000-000000000000"


async def test_reader_can_read_an_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    response = await client.get(f"/api/applications/{clmjp}/alert-sources", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))
    assert response.status_code == 200


async def test_reader_cannot_change_an_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    response = await client.post(
        f"/api/applications/{clmjp}/alert-sources", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER), json={"sourceTool": "generic", "sourceName": "Reader attempt"}
    )
    assert response.status_code == 403


async def test_admin_of_one_application_cannot_change_another(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    chad = seed_context.application_ids_by_code["CHAD"]  # this user is only a reader of CHAD
    response = await client.post(
        f"/api/applications/{chad}/alert-sources", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"sourceTool": "generic", "sourceName": "Cross-app attempt"}
    )
    assert response.status_code == 403


async def test_non_member_cannot_read_an_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    response = await client.get(f"/api/applications/{clmjp}/alert-sources", headers=await auth_headers(users.NO_ACCESS))
    assert response.status_code == 403


async def test_unknown_application_is_not_found(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    response = await client.get(f"/api/applications/{UNKNOWN_APPLICATION_ID}/alert-sources", headers=await auth_headers(users.CLMJP_AND_PAYAU_READER))
    assert response.status_code == 404


async def test_platform_administration_needs_the_keigan_admin_group(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    assert (await client.get("/api/administration/jobs", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))).status_code == 403
    assert (await client.get("/api/administration/jobs", headers=await auth_headers(users.KEIGAN_ADMIN))).status_code == 200

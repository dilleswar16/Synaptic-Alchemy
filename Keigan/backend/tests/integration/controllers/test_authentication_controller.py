"""keigan/controllers/authentication_controller.py: local sign-in, bearer tokens and the current user."""

from __future__ import annotations

import httpx

from support.http import AuthHeaders
from support import users


async def test_request_without_a_token_gets_a_problem_response(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_tampered_token_is_rejected(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    valid_header = (await auth_headers(users.CLMJP_AND_PAYAU_READER))["Authorization"]
    response = await client.get("/api/auth/me", headers={"Authorization": valid_header[:-4] + "abcd"})
    assert response.status_code == 401


async def test_unknown_local_user_cannot_sign_in(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/local-sign-in", json={"userPrincipalName": "intruder@keigan.local"})
    assert response.status_code == 401


async def test_keigan_admin_group_makes_the_user_admin_of_every_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    me = (await client.get("/api/auth/me", headers=await auth_headers(users.KEIGAN_ADMIN))).json()
    assert me["isKeiganAdmin"] is True
    assert {role["applicationId"]: role["role"] for role in me["applicationRoles"]} == {
        application_id: "admin" for application_id in seed_context.application_ids_by_code.values()
    }


async def test_application_groups_give_per_application_roles(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    ids = seed_context.application_ids_by_code
    me = (await client.get("/api/auth/me", headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER))).json()
    assert me["isKeiganAdmin"] is False
    assert {role["applicationId"]: role["role"] for role in me["applicationRoles"]} == {ids["CLMJP"]: "admin", ids["CHAD"]: "reader"}


async def test_user_without_groups_has_no_roles(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    me = (await client.get("/api/auth/me", headers=await auth_headers(users.NO_ACCESS))).json()
    assert me["isKeiganAdmin"] is False
    assert me["applicationRoles"] == []

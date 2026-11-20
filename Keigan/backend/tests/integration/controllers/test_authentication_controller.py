"""keigan/controllers/authentication_controller.py: local sign-in, bearer tokens and the current user."""

from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from keigan.config.settings import Settings
from keigan.services import authentication_service
from keigan.services.authentication_service import AuthenticationService
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


# ── Entra access tokens through the real API (H8, S5) ─────────────────────────────────────────────────────────────

ENTRA_TENANT_ID = "11111111-1111-1111-1111-111111111111"
ENTRA_API_CLIENT_ID = "22222222-2222-2222-2222-222222222222"
ENTRA_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def entra_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the token validation to Entra with a throw-away signing key (no network)."""
    entra_settings = Settings(
        _env_file=None,
        environment="dev",
        auth_mode="entra",
        entra_tenant_id=ENTRA_TENANT_ID,
        entra_api_client_id=ENTRA_API_CLIENT_ID,
        entra_api_scope=f"api://{ENTRA_API_CLIENT_ID}/access_as_user",
        local_token_signing_secret="a-long-random-value-that-is-not-the-default-0123456789",
        local_secret_encryption_key="a-long-random-value-that-is-not-the-default-0123456789",
    )

    async def no_group_lookup(entra_object_id: str) -> None:
        return None

    monkeypatch.setattr(authentication_service, "get_settings", lambda: entra_settings)
    monkeypatch.setattr(
        authentication_service,
        "_entra_signing_key_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=ENTRA_SIGNING_KEY.public_key())),
    )
    monkeypatch.setattr(AuthenticationService, "_resolve_group_memberships", staticmethod(no_group_lookup))


def entra_token(**claim_overrides: object) -> str:
    claims: dict[str, object] = {
        "iss": f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0",
        "aud": ENTRA_API_CLIENT_ID,
        "tid": ENTRA_TENANT_ID,
        "oid": "33333333-3333-3333-3333-333333333333",
        "preferred_username": "entra.user@example.com",
        "scp": "access_as_user",
        "iat": int(time.time()) - 10,
        "exp": int(time.time()) + 600,
    }
    claims.update(claim_overrides)
    return jwt.encode({name: value for name, value in claims.items() if value is not None}, ENTRA_SIGNING_KEY, algorithm="RS256")


async def test_entra_token_with_the_keigan_scope_signs_in(client: httpx.AsyncClient, entra_mode: None) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {entra_token()}"})
    assert response.status_code == 200
    assert response.json()["userPrincipalName"] == "entra.user@example.com"


async def test_entra_token_without_a_tenant_is_rejected_with_401(client: httpx.AsyncClient, entra_mode: None) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {entra_token(tid=None)}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "The token was issued by an unexpected tenant."


async def test_app_only_entra_token_is_rejected_with_403(client: httpx.AsyncClient, entra_mode: None) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {entra_token(scp=None, roles=['Keigan.Service'])}"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")

"""keigan/services/authorization_service.py: reader, admin and Keigan-admin checks as enforced on real routes."""

from __future__ import annotations

import httpx
import pytest

from keigan.config.database_config import open_session
from keigan.config.settings import AuthenticationMode, get_settings
from keigan.entities.application_entities import Application
from keigan.exceptions.keigan_exceptions import ForbiddenException
from keigan.security.current_user import CurrentUser
from keigan.services.authorization_service import ROLE_ADMIN, ROLE_READER, AuthorizationService
from support.http import AuthHeaders
from support import users

pytestmark = pytest.mark.usefixtures("seed_context")  # creates the schema

UNKNOWN_APPLICATION_ID ="00000000-0000-0000-0000-000000000000"
ADMIN_GROUP_OBJECT_ID = "11111111-1111-1111-1111-111111111111"
READER_GROUP_OBJECT_ID = "22222222-2222-2222-2222-222222222222"


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


# ── H7: Entra mode matches groups by object id, never by display name ──────────────────────────────────────────────────────────
def group_member(group_names: set[str], group_object_ids: set[str]) -> CurrentUser:
    return CurrentUser(
        user_principal_name="group.member@example.com", display_name="Group Member", email_address=None,
        group_names=frozenset(group_names), group_object_ids=frozenset(group_object_ids), is_keigan_admin=False,
    )


async def create_application(code: str, admin_object_id: str | None, reader_object_id: str | None) -> str:
    async with open_session() as session:
        application = Application(
            application_name=f"H7 {code}", application_code=code, lifecycle_status="live", admin_group_name=f"{code}_admin", reader_group_name=f"{code}_reader",
            admin_group_object_id=admin_object_id, reader_group_object_id=reader_object_id, created_by_user_principal_name="system:test",
        )
        session.add(application)
        await session.flush()
        return application.application_id


@pytest.fixture
def entra_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auth_mode", AuthenticationMode.ENTRA)


async def test_entra_group_with_the_same_display_name_but_another_object_id_grants_nothing(entra_mode: None) -> None:
    application_id = await create_application("H7A", ADMIN_GROUP_OBJECT_ID, READER_GROUP_OBJECT_ID)
    impostor = group_member({"H7A_admin", "H7A_reader"}, {"99999999-9999-9999-9999-999999999999"})
    async with open_session() as session:
        assert await AuthorizationService(session).can_read_application(impostor, application_id) is False


async def test_entra_group_object_id_grants_the_role_whatever_the_display_name(entra_mode: None) -> None:
    application_id = await create_application("H7B", ADMIN_GROUP_OBJECT_ID, READER_GROUP_OBJECT_ID)
    async with open_session() as session:
        authorization = AuthorizationService(session)
        admin_roles = await authorization.application_roles(group_member({"renamed group"}, {ADMIN_GROUP_OBJECT_ID.upper()}))
        reader_roles = await authorization.application_roles(group_member(set(), {READER_GROUP_OBJECT_ID}))
    assert admin_roles[application_id].role == ROLE_ADMIN
    assert reader_roles[application_id].role == ROLE_READER


async def test_entra_application_without_object_ids_denies_with_a_message_that_says_what_to_do(entra_mode: None) -> None:
    application_id = await create_application("H7C", None, None)
    member_by_name = group_member({"H7C_admin"}, set())
    async with open_session() as session:
        with pytest.raises(ForbiddenException) as denial:
            await AuthorizationService(session).ensure_application_reader(member_by_name, application_id)
    assert denial.value.detail == (
        "This application's access groups are not linked to Entra yet, so Keigan cannot tell who is a member. "
        "Ask a Keigan admin to run 'Check in Entra' on the application's Access step."
    )


async def test_local_mode_still_matches_groups_by_name() -> None:
    application_id = await create_application("H7D", None, None)
    async with open_session() as session:
        assert (await AuthorizationService(session).application_roles(group_member({"h7d_reader"}, set())))[application_id].role == ROLE_READER

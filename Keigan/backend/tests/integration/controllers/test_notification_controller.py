"""keigan/controllers/notification_controller.py: the application team through the real API (rights, validation, invitations, first sign-in)."""

from __future__ import annotations

import uuid

import httpx

from support import users
from support.http import AuthHeaders


def new_address() -> str:
    return f"member-{uuid.uuid4().hex[:8]}@example.com"


async def team_url(seed_context, code: str = "CLMJP") -> str:  # noqa: ANN001
    return f"/api/applications/{seed_context.application_ids_by_code[code]}/stakeholders"


async def test_a_reader_can_see_the_team_but_cannot_add_invite_or_remove(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    base = await team_url(seed_context, "CHAD")
    reader_headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)  # a reader of CHAD
    assert (await client.get(base, headers=reader_headers)).status_code == 200
    assert (await client.post(base, headers=reader_headers, json={"displayName": "X", "emailAddress": new_address()})).status_code == 403
    assert (await client.post(f"{base}/anything/invitation", headers=reader_headers)).status_code == 403


async def test_someone_with_no_access_cannot_see_the_team(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    assert (await client.get(await team_url(seed_context), headers=await auth_headers(users.NO_ACCESS))).status_code in (403, 404)


async def test_an_admin_adds_a_lead_with_an_invitation_and_the_answer_says_where_they_stand(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    address = new_address()
    response = await client.post(await team_url(seed_context), headers=headers, json={"displayName": "Lena Lead", "emailAddress": address.upper(), "stakeholderRole": "lead", "sendInvitation": True})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["emailAddress"] == address and body["stakeholderRole"] == "lead"
    assert body["teamMemberStatus"] == "invited" and body["canSendInvitation"] is False and body["nextInvitationAllowedAt"] is not None


async def test_an_invitation_sent_twice_in_a_row_is_answered_with_when_to_try_again(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    base = await team_url(seed_context)
    created = (await client.post(base, headers=headers, json={"displayName": "Dan", "emailAddress": new_address(), "stakeholderRole": "devops", "sendInvitation": True})).json()
    again = await client.post(f"{base}/{created['stakeholderId']}/invitation", headers=headers)
    assert again.status_code == 429
    assert again.headers["content-type"].startswith("application/problem+json")
    assert "You can send another in" in again.json()["detail"]


async def test_inviting_someone_who_was_only_listed_works_and_says_email_is_simulated(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    base = await team_url(seed_context)
    created = (await client.post(base, headers=headers, json={"displayName": "Tess", "emailAddress": new_address(), "stakeholderRole": "tester"})).json()
    assert created["teamMemberStatus"] == "listed" and created["canSendInvitation"] is True
    sent = await client.post(f"{base}/{created['stakeholderId']}/invitation", headers=headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()["teamMember"]["teamMemberStatus"] == "invited"
    assert "simulated" in sent.json()["message"]


async def test_an_invalid_address_is_answered_with_a_message_for_the_field(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    response = await client.post(await team_url(seed_context), headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"displayName": "Bad", "emailAddress": "not-an-address"})
    assert response.status_code == 422
    assert "Enter an email address like name@company.com." in response.text


async def test_an_unknown_role_is_refused(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    response = await client.post(await team_url(seed_context), headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER), json={"displayName": "Bad", "emailAddress": new_address(), "stakeholderRole": "astronaut"})
    assert response.status_code == 422


async def test_the_same_address_twice_is_a_conflict_the_screen_can_show(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    base, address = await team_url(seed_context), new_address()
    assert (await client.post(base, headers=headers, json={"displayName": "One", "emailAddress": address})).status_code == 201
    second = await client.post(base, headers=headers, json={"displayName": "Two", "emailAddress": address.upper()})
    assert second.status_code == 422
    assert second.json()["fieldErrors"] == [{"field": "emailAddress", "message": f"{address} is already on this team."}]


async def test_the_first_sign_in_of_a_listed_person_makes_them_active(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    admin_headers = await auth_headers(users.CLMJP_ADMIN_CHAD_READER)
    base = await team_url(seed_context)
    created = (await client.post(base, headers=admin_headers, json={"displayName": "Noa NoAccess", "emailAddress": users.NO_ACCESS, "sendInvitation": True})).json()
    assert created["teamMemberStatus"] == "invited"
    assert (await client.get("/api/auth/me", headers=await auth_headers(users.NO_ACCESS))).status_code == 200
    team = (await client.get(base, headers=admin_headers)).json()
    member = next(row for row in team if row["stakeholderId"] == created["stakeholderId"])
    assert member["teamMemberStatus"] == "active" and member["joinedAt"] is not None and member["canSendInvitation"] is False


async def test_an_application_is_created_with_its_team_through_the_api(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    code = f"T{uuid.uuid4().hex[:6].upper()}"
    headers = await auth_headers(users.KEIGAN_ADMIN)
    created = await client.post(
        "/api/applications", headers=headers,
        json={"applicationName": f"Team {code}", "applicationCode": code, "teamMembers": [{"displayName": "Lena Lead", "emailAddress": new_address(), "stakeholderRole": "lead"}]},
    )
    assert created.status_code == 201, created.text
    team = (await client.get(f"/api/applications/{created.json()['applicationId']}/stakeholders", headers=headers)).json()
    assert [(row["stakeholderRole"], row["teamMemberStatus"]) for row in team] == [("lead", "invited")]


async def test_an_application_request_with_a_duplicate_person_is_refused_before_anything_is_saved(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    code, address = f"D{uuid.uuid4().hex[:6].upper()}", new_address()
    response = await client.post(
        "/api/applications", headers=await auth_headers(users.KEIGAN_ADMIN),
        json={"applicationName": f"Team {code}", "applicationCode": code, "teamMembers": [{"displayName": "A", "emailAddress": address}, {"displayName": "B", "emailAddress": address.upper()}]},
    )
    assert response.status_code == 422 and "listed twice" in response.text

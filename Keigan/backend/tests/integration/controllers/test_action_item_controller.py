"""/api/action-items and the postmortem hook: who may do what, the status rules, and the draft/finalise flow (spec 29, AC-1 to AC-12)."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.status_values import ActionItemStatus, IncidentStatus
from keigan.utils.time_utils import utc_now
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs

READER, APP_ADMIN, KEIGAN_ADMIN, OUTSIDER = users.CLMJP_AND_PAYAU_READER, users.CLMJP_ADMIN_CHAD_READER, users.KEIGAN_ADMIN, users.NO_ACCESS


@pytest.fixture(scope="module")
def application_id(seed_context) -> str:
    return seed_context.application_ids_by_code["CLMJP"]


@pytest.fixture(scope="module")
async def owner_stakeholder_id(application_id: str) -> str:
    """The seeded team member whose address is the reader's: the reader is the owner of the items assigned to them (and so are no other readers)."""
    async with open_session() as session:
        stakeholder = await session.scalar(select(Stakeholder).where(Stakeholder.application_id == application_id, Stakeholder.email_address == READER))
        if stakeholder is None:
            stakeholder = Stakeholder(application_id=application_id, display_name="Rui Reader", email_address=READER, user_principal_name=READER)
            session.add(stakeholder)
            await session.flush()
        return stakeholder.stakeholder_id


def due_in(days: int) -> str:
    return (utc_now() + timedelta(days=days)).date().isoformat()


async def create_item(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str, **overrides: object) -> dict:
    body = {"itemTitle": "Add a connection pool alert", "actionType": "detect", "dueOn": due_in(14), **overrides}
    response = await client.post(f"/api/applications/{application_id}/action-items", headers=await auth_headers(APP_ADMIN), json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def set_status(client: httpx.AsyncClient, auth_headers: AuthHeaders, user: str, item_id: str, status: str, **extra: object) -> httpx.Response:
    return await client.post(f"/api/action-items/{item_id}/status", headers=await auth_headers(user), json={"status": status, **extra})


# ── Create and read (AC-1, AC-10) ────────────────────────────────────────────────────────────────


async def test_an_admin_creates_an_open_item_and_a_reader_sees_it_but_cannot_create(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item = await create_item(client, auth_headers, application_id)
    assert item["itemStatus"] == "open" and item["sourceKind"] == "manual" and item["originalDueOn"] == item["dueOn"] and item["dueOnChangeCount"] == 0
    assert (await client.get(f"/api/action-items/{item['actionItemId']}", headers=await auth_headers(READER))).status_code == 200
    forbidden = await client.post(f"/api/applications/{application_id}/action-items", headers=await auth_headers(READER), json={"itemTitle": "Nope", "actionType": "detect", "dueOn": due_in(7)})
    assert forbidden.status_code == 403
    assert (await client.get(f"/api/action-items/{item['actionItemId']}", headers=await auth_headers(OUTSIDER))).status_code == 403


async def test_the_due_date_must_be_today_or_later_and_within_the_maximum(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    for days in (-1, 1000):
        response = await client.post(
            f"/api/applications/{application_id}/action-items", headers=await auth_headers(APP_ADMIN), json={"itemTitle": "Bad date", "actionType": "prevent", "dueOn": due_in(days)},
        )
        assert response.status_code == 422, response.text


async def test_an_owner_must_be_an_active_person_of_the_same_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str, seed_context) -> None:
    async with open_session() as session:
        other = Stakeholder(application_id=seed_context.application_ids_by_code["PAYAU"], display_name="Elsewhere", email_address="elsewhere@example.com")
        session.add(other)
        await session.flush()
        other_id = other.stakeholder_id
    response = await client.post(
        f"/api/applications/{application_id}/action-items", headers=await auth_headers(APP_ADMIN), json={"itemTitle": "Wrong owner", "actionType": "prevent", "dueOn": due_in(7), "ownerStakeholderId": other_id},
    )
    assert response.status_code == 422 and "owner" in response.text.lower()


async def test_the_default_list_is_the_unfinished_tracked_items_in_the_readers_applications(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item = await create_item(client, auth_headers, application_id, itemTitle="Listed item")
    done = await create_item(client, auth_headers, application_id, itemTitle="Finished item")
    assert (await set_status(client, auth_headers, APP_ADMIN, done["actionItemId"], "done")).status_code == 200
    listed = (await client.get("/api/action-items", headers=await auth_headers(READER))).json()["items"]
    ids = {entry["actionItemId"] for entry in listed}
    assert item["actionItemId"] in ids and done["actionItemId"] not in ids
    assert (await client.get("/api/action-items", headers=await auth_headers(OUTSIDER))).json()["totalCount"] == 0
    with_done = (await client.get("/api/action-items?statuses=done", headers=await auth_headers(READER))).json()["items"]
    assert done["actionItemId"] in {entry["actionItemId"] for entry in with_done}


# ── Status rules (AC-6, AC-7) ────────────────────────────────────────────────────────────────────


async def test_the_owner_may_start_block_and_finish_but_not_drop_or_reassign(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str, owner_stakeholder_id: str) -> None:
    item = await create_item(client, auth_headers, application_id, ownerStakeholderId=owner_stakeholder_id)
    item_id = item["actionItemId"]
    assert item["canEdit"] is True
    as_owner = (await client.get(f"/api/action-items/{item_id}", headers=await auth_headers(READER))).json()
    assert as_owner["canEdit"] is False and set(as_owner["allowedStatuses"]) == {"in_progress", "blocked", "done"}
    assert (await set_status(client, auth_headers, READER, item_id, "in_progress")).status_code == 200
    assert (await set_status(client, auth_headers, READER, item_id, "wont_do", reasonText="we do not want this")).status_code == 422
    assert (await client.patch(f"/api/action-items/{item_id}", headers=await auth_headers(READER), json={"dueOn": due_in(30)})).status_code == 403
    assert (await client.patch(f"/api/action-items/{item_id}", headers=await auth_headers(READER), json={"itemDetailsMarkdown": "Pool size is 20."})).status_code == 200
    done = await set_status(client, auth_headers, READER, item_id, "done", completionNoteText="Alert added in the pool dashboard.")
    assert done.status_code == 200 and done.json()["completedBy"] == READER and done.json()["completedAt"]


async def test_a_reader_who_is_not_the_owner_cannot_change_the_status(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item = await create_item(client, auth_headers, application_id)
    response = await set_status(client, auth_headers, READER, item["actionItemId"], "done")
    assert response.status_code == 422 and (await client.get(f"/api/action-items/{item['actionItemId']}", headers=await auth_headers(READER))).json()["allowedStatuses"] == []


async def test_blocked_and_wont_do_need_a_reason_and_reopening_clears_the_close(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item_id = (await create_item(client, auth_headers, application_id))["actionItemId"]
    assert (await set_status(client, auth_headers, APP_ADMIN, item_id, "blocked")).status_code == 422
    blocked = await set_status(client, auth_headers, APP_ADMIN, item_id, "blocked", reasonText="Waiting for the vendor fix.")
    assert blocked.status_code == 200 and blocked.json()["statusReasonText"] == "Waiting for the vendor fix."
    assert (await set_status(client, auth_headers, APP_ADMIN, item_id, "wont_do", reasonText="Superseded by the new platform.")).json()["completedAt"]
    reopened = (await set_status(client, auth_headers, APP_ADMIN, item_id, "open")).json()
    assert reopened["itemStatus"] == "open" and reopened["completedAt"] is None and reopened["statusReasonText"] is None


async def test_changing_a_tracked_items_due_date_is_counted_and_the_original_is_kept(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item = await create_item(client, auth_headers, application_id, dueOn=due_in(10))
    moved = (await client.patch(f"/api/action-items/{item['actionItemId']}", headers=await auth_headers(APP_ADMIN), json={"dueOn": due_in(40)})).json()
    assert moved["dueOn"] == due_in(40) and moved["originalDueOn"] == due_in(10) and moved["dueOnChangeCount"] == 1


async def test_a_tracked_item_cannot_be_deleted_and_the_change_is_audited(client: httpx.AsyncClient, auth_headers: AuthHeaders, application_id: str) -> None:
    item_id = (await create_item(client, auth_headers, application_id))["actionItemId"]
    refused = await client.delete(f"/api/action-items/{item_id}", headers=await auth_headers(APP_ADMIN))
    assert refused.status_code == 422 and "won't do" in refused.text
    async with open_session() as session:
        from keigan.entities.platform_entities import AuditEvent

        actions = set((await session.scalars(select(AuditEvent.action_name).where(AuditEvent.target_entity_id == item_id))).all())
    assert "action_item.create" in actions


# ── The postmortem hook (AC-2 to AC-4) ───────────────────────────────────────────────────────────


@pytest.fixture
async def resolved_incident_id(application_id: str) -> str:
    async with open_session() as session:
        incident = Incident(application_id=application_id, incident_title="Claims batch failed", incident_status=IncidentStatus.RESOLVED, opened_at=utc_now() - timedelta(hours=3), resolved_at=utc_now() - timedelta(hours=1))
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def draft_postmortem(client: httpx.AsyncClient, auth_headers: AuthHeaders, incident_id: str) -> str:
    response = await client.post(f"/api/incidents/{incident_id}/postmortem/generate", headers=await auth_headers(APP_ADMIN))
    assert response.status_code == 202, response.text
    await drain_jobs()
    postmortem = (await client.get(f"/api/incidents/{incident_id}/postmortem", headers=await auth_headers(APP_ADMIN))).json()
    assert postmortem["reportStatus"] == "draft", postmortem
    return postmortem["postmortemId"]


async def add_extra_suggestion(postmortem_id: str) -> str:
    """The offline model may suggest only one item for a quiet incident; a second suggestion makes the 'discard' and 'replace' rules observable."""
    async with open_session() as session:
        postmortem = await session.get(PostmortemReport, postmortem_id)
        incident = await session.get(Incident, postmortem.incident_id)
        extra = ActionItem(
            application_id=incident.application_id, incident_id=incident.incident_id, postmortem_id=postmortem_id, item_source_kind="postmortem", item_title="Extra suggestion", action_type="mitigate",
            item_status=ActionItemStatus.PROPOSED, due_on=utc_now().date() + timedelta(days=10), display_order=99,
        )
        session.add(extra)
        await session.flush()
        return extra.action_item_id


async def test_a_drafted_postmortem_proposes_items_and_the_first_is_top_priority(client: httpx.AsyncClient, auth_headers: AuthHeaders, resolved_incident_id: str) -> None:
    postmortem_id = await draft_postmortem(client, auth_headers, resolved_incident_id)
    items = (await client.get(f"/api/postmortems/{postmortem_id}/action-items", headers=await auth_headers(READER))).json()
    assert items and {item["itemStatus"] for item in items} == {"proposed"} and items[0]["actionPriority"] == "top" and items[0]["sourceKind"] == "postmortem"
    assert all(item["dueOn"] and item["suggestedOwnerRoleText"] and item["owner"] is None for item in items)
    assert (await client.get("/api/action-items", headers=await auth_headers(READER))).json()["items"] is not None  # proposed items are not in the tracked default list
    assert not {item["actionItemId"] for item in items} & {entry["actionItemId"] for entry in (await client.get("/api/action-items", headers=await auth_headers(READER))).json()["items"]}


async def test_finalising_is_refused_while_suggestions_remain_then_renders_the_accepted_items(client: httpx.AsyncClient, auth_headers: AuthHeaders, resolved_incident_id: str) -> None:
    postmortem_id = await draft_postmortem(client, auth_headers, resolved_incident_id)
    extra_id = await add_extra_suggestion(postmortem_id)
    items = [item for item in (await client.get(f"/api/postmortems/{postmortem_id}/action-items", headers=await auth_headers(APP_ADMIN))).json() if item["actionItemId"] != extra_id]
    refused = await client.post(f"/api/postmortems/{postmortem_id}/finalize", headers=await auth_headers(APP_ADMIN))
    assert refused.status_code == 422 and "actionItems" in refused.text
    accepted = await client.post(f"/api/action-items/{items[0]['actionItemId']}/accept", headers=await auth_headers(APP_ADMIN), json={"itemTitle": "Alert on pool saturation"})
    assert accepted.status_code == 200 and accepted.json()["itemStatus"] == "open" and accepted.json()["itemTitle"] == "Alert on pool saturation" and accepted.json()["acceptedAt"]
    for item in items[1:] + [{"actionItemId": extra_id}]:
        assert (await client.delete(f"/api/action-items/{item['actionItemId']}", headers=await auth_headers(APP_ADMIN))).status_code == 204
    final = await client.post(f"/api/postmortems/{postmortem_id}/finalize", headers=await auth_headers(APP_ADMIN))
    assert final.status_code == 200, final.text
    markdown = final.json()["reportMarkdown"]
    assert "Alert on pool saturation" in markdown and "| Action | Owner role | Due | Type | Priority |" in markdown and "Extra suggestion" not in markdown


async def test_redrafting_replaces_the_suggestions_and_keeps_accepted_items(client: httpx.AsyncClient, auth_headers: AuthHeaders, resolved_incident_id: str) -> None:
    postmortem_id = await draft_postmortem(client, auth_headers, resolved_incident_id)
    first = (await client.get(f"/api/postmortems/{postmortem_id}/action-items", headers=await auth_headers(APP_ADMIN))).json()
    kept_id = first[0]["actionItemId"]
    assert (await client.post(f"/api/action-items/{kept_id}/accept", headers=await auth_headers(APP_ADMIN))).status_code == 200
    extra_id = await add_extra_suggestion(postmortem_id)
    await draft_postmortem(client, auth_headers, resolved_incident_id)
    second = (await client.get(f"/api/postmortems/{postmortem_id}/action-items", headers=await auth_headers(APP_ADMIN))).json()
    statuses = [item["itemStatus"] for item in second]
    assert statuses.count("open") == 1 and statuses.count("proposed") == len(first) and kept_id in {item["actionItemId"] for item in second}
    assert extra_id not in {item["actionItemId"] for item in second}

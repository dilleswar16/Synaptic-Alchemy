"""/api/investigations/{id}/similar-incidents and /api/incident-memory: who sees which past incident, saying whether it was relevant, and hiding it (spec 34, AC-1 to AC-5, AC-10)."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import PostmortemReport
from keigan.entities.incident_memory_entities import IncidentMemoryEntry
from keigan.entities.platform_entities import AuditEvent
from keigan.services.incident_memory_builder import enqueue_memory_refresh_for_incident
from keigan.utils.time_utils import utc_now
from support import users
from support.http import AuthHeaders
from support.jobs import drain_jobs
from tests.integration.services.test_incident_memory import build, entry_of, investigated, unique_error

READER, APP_ADMIN, OUTSIDER = users.CLMJP_AND_PAYAU_READER, users.CLMJP_ADMIN_CHAD_READER, users.NO_ACCESS  # the admin of the Claims application only reads the Chad application


async def a_past_and_a_current_incident(seed_context, past_application: str = "CLMJP") -> tuple[str, str, str]:
    """A remembered incident of ``past_application`` and a later one of the Claims application with the same error: (entry id, current investigation id, past investigation id)."""
    error = unique_error()
    past = await investigated(seed_context.application_ids_by_code[past_application], days_ago=40, title="Past timeout", template=error, verdict="correct", resolution_note="Raised the pool size.")
    current = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Current timeout", template=error)
    await build(past.investigation_id)
    return (await entry_of(past.investigation_id)).incident_memory_entry_id, current.investigation_id, past.investigation_id


async def similar(client: httpx.AsyncClient, auth_headers: AuthHeaders, user: str, investigation_id: str) -> dict:
    response = await client.get(f"/api/investigations/{investigation_id}/similar-incidents", headers=await auth_headers(user))
    assert response.status_code == 200, response.text
    return response.json()


# ── Reading ──────────────────────────────────────────────────────────────────────────────────────


async def test_a_reader_sees_the_past_incident_with_why_it_matched_and_what_fixed_it(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, current_id, past_investigation_id = await a_past_and_a_current_incident(seed_context)
    body = await similar(client, auth_headers, READER, current_id)
    [item] = [item for item in body["items"] if item["memoryEntryId"] == entry_id]
    assert body["isAvailable"] is True and item["isSameApplication"] is True and item["investigationId"] == past_investigation_id
    assert item["verdict"] == "correct" and item["fixText"] == "Raised the pool size." and item["fixSource"] == "resolution_note" and item["causeSource"] == "investigation"
    assert "error_signature" in {reason["keyKind"] for reason in item["matchReasons"]} and item["isStale"] is False and item["myRelevanceVerdict"] is None
    assert "score" not in item and item["canHide"] is False  # a reader cannot hide it


async def test_a_running_investigation_has_nothing_to_match_yet(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    running = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=0, title="Running now", status="running")
    assert await similar(client, auth_headers, READER, running.investigation_id) == {"items": [], "isAvailable": False}


async def test_nobody_outside_the_application_may_ask_and_an_unknown_investigation_is_not_found(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    _, current_id, _ = await a_past_and_a_current_incident(seed_context)
    assert (await client.get(f"/api/investigations/{current_id}/similar-incidents", headers=await auth_headers(OUTSIDER))).status_code == 403
    assert (await client.get("/api/investigations/nope/similar-incidents", headers=await auth_headers(READER))).status_code == 404


async def test_a_past_incident_of_an_application_the_reader_cannot_read_is_not_shown_to_them_but_is_to_someone_who_can(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, current_id, _ = await a_past_and_a_current_incident(seed_context, past_application="CHAD")
    # The same error in the Chad application: only a hard fact lets another application in, and the Claims-only reader may not read Chad.
    assert entry_id not in {item["memoryEntryId"] for item in (await similar(client, auth_headers, READER, current_id))["items"]}
    shown = {item["memoryEntryId"]: item for item in (await similar(client, auth_headers, APP_ADMIN, current_id))["items"]}
    assert entry_id in shown and shown[entry_id]["isSameApplication"] is False and shown[entry_id]["application"]["applicationName"]


async def test_an_incorrect_analysis_is_not_repeated_to_the_reader(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context, monkeypatch) -> None:
    # With the default minimum score an incorrect past analysis never scores high enough to be shown (0.3 times at most 1); a lower minimum shows it, without its cause.
    monkeypatch.setattr(get_settings(), "incident_memory_minimum_score", 0.1)
    monkeypatch.setattr(get_settings(), "incident_memory_maximum_shown", 20)  # the other tests' entries share this application's service and would fill the top five
    error = unique_error()
    past = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=40, title="Wrong analysis", template=error, verdict="incorrect", why="The DNS was down.")
    current = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Now", template=error)
    await build(past.investigation_id)
    [item] = [item for item in (await similar(client, auth_headers, READER, current.investigation_id))["items"] if item["investigationId"] == past.investigation_id]
    assert item["verdict"] == "incorrect" and item["causeText"] is None and item["causeSource"] == "investigation"


# ── Relevance ────────────────────────────────────────────────────────────────────────────────────


async def test_a_reader_says_whether_a_suggestion_was_relevant_changes_their_mind_and_clears_it(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, current_id, _ = await a_past_and_a_current_incident(seed_context)
    path = f"/api/investigations/{current_id}/similar-incidents/{entry_id}/relevance"
    headers = await auth_headers(READER)

    async def mine() -> str | None:
        return next(item for item in (await similar(client, auth_headers, READER, current_id))["items"] if item["memoryEntryId"] == entry_id)["myRelevanceVerdict"]

    assert (await client.put(path, headers=headers, json={"verdict": "relevant"})).status_code == 204 and await mine() == "relevant"
    assert (await client.put(path, headers=headers, json={"verdict": "not_relevant"})).status_code == 204 and await mine() == "not_relevant"
    assert (await client.delete(path, headers=headers)).status_code == 204 and await mine() is None
    assert (await client.put(path, headers=headers, json={"verdict": "maybe"})).status_code == 422


async def test_an_entry_the_reader_cannot_read_is_not_found_never_forbidden(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, current_id, _ = await a_past_and_a_current_incident(seed_context, past_application="CHAD")
    path = f"/api/investigations/{current_id}/similar-incidents/{entry_id}/relevance"
    assert (await client.put(path, headers=await auth_headers(READER), json={"verdict": "relevant"})).status_code == 404
    assert (await client.put(f"/api/investigations/{current_id}/similar-incidents/unknown/relevance", headers=await auth_headers(READER), json={"verdict": "relevant"})).status_code == 404


# ── Hiding ───────────────────────────────────────────────────────────────────────────────────────


async def test_an_admin_hides_an_entry_for_everyone_and_shows_it_again(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, current_id, _ = await a_past_and_a_current_incident(seed_context)
    hide = f"/api/incident-memory/{entry_id}/hide"
    assert (await client.post(hide, headers=await auth_headers(READER), json={"reason": "wrong"})).status_code == 403
    assert (await client.post(hide, headers=await auth_headers(APP_ADMIN), json={"reason": ""})).status_code == 422
    assert (await client.post(hide, headers=await auth_headers(APP_ADMIN), json={"reason": "Mail to ana@example.com says this was a different cause."})).status_code == 204
    assert entry_id not in {item["memoryEntryId"] for item in (await similar(client, auth_headers, READER, current_id))["items"]}
    async with open_session() as session:
        entry = await session.get(IncidentMemoryEntry, entry_id)
        audit = (await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == entry_id, AuditEvent.action_name == "incident_memory.hide"))).all()
    assert entry.entry_status == "hidden" and entry.hidden_by_user_principal_name == APP_ADMIN and "ana@example.com" not in entry.hide_reason_text
    assert len(audit) == 1 and "ana@example.com" not in str(audit[0].action_details_json) and "wrong" not in str(audit[0].action_details_json)
    assert (await client.post(f"/api/incident-memory/{entry_id}/unhide", headers=await auth_headers(APP_ADMIN))).status_code == 204
    assert entry_id in {item["memoryEntryId"] for item in (await similar(client, auth_headers, READER, current_id))["items"]}


async def test_someone_who_cannot_read_an_entry_cannot_hide_it_and_is_not_told_it_exists(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    entry_id, _, _ = await a_past_and_a_current_incident(seed_context, past_application="CHAD")
    for user in (READER, OUTSIDER):
        assert (await client.post(f"/api/incident-memory/{entry_id}/hide", headers=await auth_headers(user), json={"reason": "no"})).status_code == 404
    assert (await client.post(f"/api/incident-memory/{entry_id}/hide", headers=await auth_headers(APP_ADMIN), json={"reason": "reader only"})).status_code == 403  # may read Chad, but only administers Claims
    assert (await client.post("/api/incident-memory/unknown/unhide", headers=await auth_headers(APP_ADMIN))).status_code == 404


# ── What keeps the memory up to date ─────────────────────────────────────────────────────────────


async def test_a_verdict_a_resolution_and_a_final_postmortem_each_refresh_the_entry(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=2, title="Resolved later", incident_status="investigating")
    await build(world.investigation_id)
    assert (await entry_of(world.investigation_id)).fix_source == "none"

    resolved = await client.post(f"/api/incidents/{world.incident_id}/resolve", headers=await auth_headers(APP_ADMIN), json={"resolutionNote": "Raised the pool size to 300.", "generatePostmortem": False})
    assert resolved.status_code == 200, resolved.text
    await drain_jobs()
    entry = await entry_of(world.investigation_id)
    assert (entry.fix_text, entry.fix_source) == ("Raised the pool size to 300.", "resolution_note")

    async with open_session() as session:
        session.add(PostmortemReport(incident_id=world.incident_id, investigation_id=world.investigation_id, report_title="p", report_status="final", report_sections_json={"root_cause": "The pool limit was never raised."}, finalized_at=utc_now()))
        await enqueue_memory_refresh_for_incident(session, world.incident_id)  # what finalising a postmortem does
    await drain_jobs()
    assert (await entry_of(world.investigation_id)).cause_source == "postmortem"

    async with open_session() as session:
        (await session.get(IncidentMemoryEntry, (await entry_of(world.investigation_id)).incident_memory_entry_id)).fix_text = "Out of date text"
    feedback = await client.post(f"/api/investigations/{world.investigation_id}/feedback", headers=await auth_headers(APP_ADMIN), json={"verdict": "correct"})
    assert feedback.status_code == 200, feedback.text
    await drain_jobs()
    assert (await entry_of(world.investigation_id)).fix_text == "Raised the pool size to 300."  # a verdict rebuilt it

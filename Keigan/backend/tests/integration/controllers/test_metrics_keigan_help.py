"""GET /api/metrics/overview: what resolvers said about how far Keigan's analysis helped, and how long those incidents took (the "Resolved with Keigan's help" block)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Incident
from support import users
from support.http import AuthHeaders

# A period no other test uses, so only the rows made here reach these numbers.
PERIOD = {"from": "2021-05-01T00:00:00Z", "to": "2021-05-30T00:00:00Z"}


async def resolved_incident(application_id: str, day: int, minutes_to_resolve: int, answer: str | None) -> None:
    opened = datetime(2021, 5, day, 10, tzinfo=UTC)
    async with open_session() as session:
        session.add(Incident(application_id=application_id, incident_title="Answer", incident_status="resolved", opened_at=opened, resolved_at=opened + timedelta(minutes=minutes_to_resolve), keigan_help=answer))


@pytest.fixture(scope="module", autouse=True)
async def answered_incidents(seed_context) -> None:  # noqa: ANN001
    """CLMJP: found the cause twice (30 and 50 minutes), helped partly once (70), did not help once (200), no answer once (100). PAYAU: not used once (300)."""
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    for day, minutes, answer in ((2, 30, "found_cause"), (3, 50, "found_cause"), (4, 70, "helped_partly"), (5, 200, "did_not_help"), (6, 100, None)):
        await resolved_incident(claims, day, minutes, answer)
    await resolved_incident(payments, 7, 300, "not_used")


async def overview(client: httpx.AsyncClient, auth_headers: AuthHeaders, **query: str) -> dict:
    response = await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params={**PERIOD, **query})
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_answers_are_counted_and_unanswered_incidents_are_not(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    block = (await overview(client, auth_headers))["summary"]["keiganHelp"]
    assert (block["resolvedCount"], block["answeredCount"]) == (6, 5)
    assert {item["answer"]: item["count"] for item in block["answers"]} == {"found_cause": 2, "helped_partly": 1, "did_not_help": 1, "not_used": 1}


async def test_the_resolve_times_are_split_into_with_and_without_help(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    block = (await overview(client, auth_headers))["summary"]["keiganHelp"]
    assert (block["timeToResolveWithHelp"]["sampleCount"], block["timeToResolveWithHelp"]["median"]) == (3, 50 * 60)  # 30, 50 and 70 minutes, in seconds
    assert (block["timeToResolveWithoutHelp"]["sampleCount"], block["timeToResolveWithoutHelp"]["median"]) == (2, 250 * 60)  # 200 and 300 minutes


async def test_the_share_is_withheld_below_the_minimum_sample(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    block = (await overview(client, auth_headers))["summary"]["keiganHelp"]
    assert block["minimumSample"] == get_settings().metrics_minimum_rating_sample
    assert block["answeredCount"] >= block["minimumSample"]
    assert block["shareFoundCause"] == 40.0  # two of five


async def test_one_application_sees_only_its_own_answers(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:
    payments = seed_context.application_ids_by_code["PAYAU"]
    block = (await overview(client, auth_headers, applicationId=payments))["summary"]["keiganHelp"]
    assert (block["resolvedCount"], block["answeredCount"]) == (1, 1)
    assert {item["answer"]: item["count"] for item in block["answers"]}["not_used"] == 1
    assert block["shareFoundCause"] is None  # one answer is below the minimum sample

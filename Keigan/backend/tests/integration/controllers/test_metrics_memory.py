"""GET /api/metrics/overview: how the memory of past incidents is used and judged in the period (spec 34, 4.10, "in the product")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryRelevanceFeedback, InvestigationMemoryReference
from support import users
from support.http import AuthHeaders

# A period no other test uses, so only the rows made here reach these numbers.
PERIOD = {"from": "2021-03-01T00:00:00Z", "to": "2021-03-30T00:00:00Z"}


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2021, 3, day, hour, tzinfo=UTC)


async def completed_investigation(application_id: str, day: int, *, status: str = "completed") -> str:
    async with open_session() as session:
        investigation = Investigation(application_id=application_id, investigation_status=status, created_at=at(day), started_at=at(day), completed_at=at(day) + timedelta(minutes=5))
        session.add(investigation)
        await session.flush()
        return investigation.investigation_id


async def entry_for(application_id: str, *, hidden_on: int | None = None) -> str:
    past = await completed_investigation(application_id, 1)
    async with open_session() as session:
        entry = IncidentMemoryEntry(
            application_id=application_id, investigation_id=past, entry_status="hidden" if hidden_on else "active", occurred_at=at(1), incident_title_text="Past", cause_source="none", fix_source="none",
            search_terms_json={}, service_ids_json=[], hidden_at=at(hidden_on) if hidden_on else None,
        )
        session.add(entry)
        await session.flush()
        return entry.incident_memory_entry_id


@pytest.fixture(scope="module", autouse=True)
async def memory_in_use(seed_context) -> None:  # noqa: ANN001
    """CLMJP: two completed investigations (one given a hint), four answers (three relevant), one entry hidden. PAYAU: one completed investigation given a hint, no answers."""
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    hinted, plain, payments_hinted, failed = (await completed_investigation(claims, 5), await completed_investigation(claims, 6), await completed_investigation(payments, 7), await completed_investigation(claims, 8, status="failed"))
    helpful = await entry_for(claims)
    hidden = await entry_for(claims, hidden_on=9)
    async with open_session() as session:
        for investigation_id in (hinted, payments_hinted, failed):
            session.add(InvestigationMemoryReference(investigation_id=investigation_id, incident_memory_entry_id=helpful, position=0))
        for person, verdict in (("a", "relevant"), ("b", "relevant"), ("c", "relevant"), ("d", "not_relevant")):
            session.add(IncidentMemoryRelevanceFeedback(investigation_id=plain, incident_memory_entry_id=hidden, user_principal_name=f"{person}@example.com", relevance_verdict=verdict, recorded_at=at(10)))


async def overview(client: httpx.AsyncClient, auth_headers: AuthHeaders, **query: str) -> dict:
    response = await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params={**PERIOD, **query})
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_overview_counts_the_hints_the_answers_and_the_hidden_entries_and_withholds_the_share_below_the_minimum_sample(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    memory = (await overview(client, auth_headers))["summary"]["memory"]
    assert (memory["completedInvestigationCount"], memory["investigationsGivenAHintCount"]) == (5, 2)  # five completed (two of them were the investigations the entries were built from); the failed one has a hint but is not counted
    assert (memory["relevanceAnswerCount"], memory["relevantCount"], memory["notRelevantCount"], memory["hiddenEntryCount"]) == (4, 3, 1, 1)
    assert memory["minimumSample"] == get_settings().metrics_minimum_rating_sample


async def test_the_share_relevant_is_given_once_enough_people_answered(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_minimum_rating_sample", 4)
    assert (await overview(client, auth_headers))["summary"]["memory"]["shareRelevant"] == 75.0
    monkeypatch.setattr(get_settings(), "metrics_minimum_rating_sample", 5)
    assert (await overview(client, auth_headers))["summary"]["memory"]["shareRelevant"] is None


async def test_each_application_shows_only_its_own_figures(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    by_code = {row["applicationCode"]: row["memory"] for row in (await overview(client, auth_headers))["applications"]}
    assert (by_code["CLMJP"]["relevanceAnswerCount"], by_code["CLMJP"]["hiddenEntryCount"], by_code["CLMJP"]["investigationsGivenAHintCount"]) == (4, 1, 1)
    assert (by_code["PAYAU"]["relevanceAnswerCount"], by_code["PAYAU"]["hiddenEntryCount"], by_code["PAYAU"]["investigationsGivenAHintCount"]) == (0, 0, 1)

"""keigan/controllers/metrics_controller.py: GET /api/metrics/overview through the real API (who sees which application, the period, and the numbers themselves)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.incident_entities import Incident, Investigation
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.entities.status_values import IncidentStatus, InvestigationFeedbackVerdict, InvestigationStatus, LlmCallOutcome, Priority
from support import users
from support.http import AuthHeaders

# A period far in the past, so incidents other tests create (they use "now") never reach these numbers.
FROM, TO = "2020-03-02T00:00:00Z", "2020-03-30T00:00:00Z"
PERIOD = {"from": FROM, "to": TO}
MODEL = "metrics-test-model"


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2020, 3, day, hour, minute, tzinfo=UTC)


async def add_incident(
    application_id: str, *, priority: str, opened_at: datetime, resolved_after: timedelta | None = None, first_alert_minutes_before: int | None = None, first_update_minutes_after: int | None = None,
    investigation: tuple[str, timedelta | None, str | None] | None = None, calls: tuple[tuple[int, int, int, str], ...] = (),
) -> None:
    """One incident with what hangs off it. ``investigation`` = (status, time it took, verdict); ``calls`` = (input tokens, output tokens, latency ms, outcome)."""
    async with open_session() as session:
        incident = Incident(
            application_id=application_id, incident_title="Metrics test incident", keigan_priority=priority, opened_at=opened_at, detected_by_keigan_at=opened_at + timedelta(minutes=1),
            first_update_sent_at=opened_at + timedelta(minutes=1 + first_update_minutes_after) if first_update_minutes_after is not None else None,
            resolved_at=opened_at + resolved_after if resolved_after is not None else None, incident_status=IncidentStatus.RESOLVED if resolved_after is not None else IncidentStatus.INVESTIGATING,
        )
        session.add(incident)
        await session.flush()
        if first_alert_minutes_before is not None:
            group = AlertGroup(application_id=application_id, group_title="Metrics test group", incident_id=incident.incident_id)
            session.add(group)
            await session.flush()
            for offset in (first_alert_minutes_before, first_alert_minutes_before - 2):  # a second, later alert in the same group: only the earliest counts
                session.add(Alert(application_id=application_id, alert_fingerprint=f"{incident.incident_id}-{offset}", rule_name="rule", alert_group_id=group.alert_group_id, first_seen_at=opened_at - timedelta(minutes=offset)))
        if investigation is not None:
            status, took, verdict = investigation
            started = opened_at + timedelta(minutes=1)
            record = Investigation(
                application_id=application_id, incident_id=incident.incident_id, investigation_status=status, user_feedback_verdict=verdict, created_at=started, started_at=started,
                completed_at=started + took if took is not None else None,
            )
            session.add(record)
            await session.flush()
            for input_tokens, output_tokens, latency, outcome in calls:
                session.add(LlmUsageRecord(
                    application_id=application_id, investigation_id=record.investigation_id, feature_name="synthesis", provider_name="test", model_name=MODEL, model_tier="deep",
                    input_token_count=input_tokens, output_token_count=output_tokens, latency_milliseconds=latency, outcome_status=outcome, created_at=started,
                ))


@pytest.fixture(scope="module", autouse=True)
async def seeded_incidents(seed_context) -> None:  # noqa: ANN001
    """Four incidents in the period (three applications) and one before it.

    CLMJP  A: P1, alert 10 min before it opened, first update 10 min after Keigan saw it, resolved after 1 h, investigation 5 min, rated correct, two AI calls.
    CLMJP  B: P3, still open, no alert; its investigation failed (one failed AI call).
    PAYAU  C: P2, resolved after 2 h, no alert, no investigation.
    CHAD   D: P1, resolved after 5 h, no alert; investigation 10 min, rated incorrect.
    CLMJP  E: before the period.
    """
    codes = seed_context.application_ids_by_code
    completed, failed = InvestigationStatus.COMPLETED, InvestigationStatus.FAILED
    succeeded, call_failed = LlmCallOutcome.SUCCEEDED, LlmCallOutcome.FAILED
    await add_incident(codes["CLMJP"], priority=Priority.P1, opened_at=at(3, 10), resolved_after=timedelta(hours=1), first_alert_minutes_before=10, first_update_minutes_after=10,
                       investigation=(completed, timedelta(minutes=5), InvestigationFeedbackVerdict.CORRECT), calls=((1000, 200, 500, succeeded), (2000, 300, 700, succeeded)))
    await add_incident(codes["CLMJP"], priority=Priority.P3, opened_at=at(10, 9), investigation=(failed, None, None), calls=((0, 0, 100, call_failed),))
    await add_incident(codes["PAYAU"], priority=Priority.P2, opened_at=at(4, 8), resolved_after=timedelta(hours=2))
    await add_incident(codes["CHAD"], priority=Priority.P1, opened_at=at(5, 14), resolved_after=timedelta(hours=5), investigation=(completed, timedelta(minutes=10), InvestigationFeedbackVerdict.INCORRECT))
    await add_incident(codes["CLMJP"], priority=Priority.P1, opened_at=datetime(2020, 2, 1, 10, tzinfo=UTC), resolved_after=timedelta(hours=9))


async def overview(client: httpx.AsyncClient, auth_headers: AuthHeaders, user: str, **query: str) -> httpx.Response:
    return await client.get("/api/metrics/overview", headers=await auth_headers(user), params={**PERIOD, **query})


def by_priority(summary: dict) -> dict[str, tuple[int, int]]:
    return {row["priority"]: (row["openedCount"], row["resolvedCount"]) for row in summary["byPriority"]}


# ── The numbers ────────────────────────────────────────────────────────────────

async def test_a_keigan_admin_sees_every_application_added_up(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    response = await overview(client, auth_headers, users.KEIGAN_ADMIN)
    assert response.status_code == 200, response.text
    summary = response.json()["summary"]
    assert (summary["incidentsOpenedCount"], summary["incidentsResolvedCount"]) == (4, 3)
    assert by_priority(summary) == {"P1": (2, 2), "P2": (1, 1), "P3": (1, 0), "P4": (0, 0), "unassigned": (0, 0)}
    assert (summary["timeToResolve"]["sampleCount"], summary["timeToResolve"]["median"], summary["timeToResolve"]["p90"]) == (3, 7200, 15840)  # 1 h, 2 h, 5 h
    assert (summary["timeToDetect"]["sampleCount"], summary["timeToDetect"]["median"], summary["timeToDetect"]["excludedCount"]) == (1, 600, 3)  # only A has an alert
    assert (summary["timeToFirstUpdate"]["sampleCount"], summary["timeToFirstUpdate"]["median"]) == (1, 600)
    assert (summary["timeToConclusion"]["sampleCount"], summary["timeToConclusion"]["median"]) == (2, 450)  # 5 min and 10 min


async def test_investigations_are_counted_by_status_and_the_share_correct_is_withheld_below_the_minimum_sample(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    summary = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()["summary"]
    assert summary["investigationCount"] == 3
    assert {row["status"]: row["count"] for row in summary["investigationsByStatus"]} == {
        "queued": 0, "running": 0, "completed": 2, "completed_evidence_only": 0, "failed": 1, "cancelled": 0,
    }
    ratings = summary["ratings"]
    assert (ratings["ratedCount"], ratings["correctCount"], ratings["incorrectCount"], ratings["partiallyCorrectCount"]) == (2, 1, 1, 0)
    assert ratings["minimumSample"] == 5 and ratings["shareCorrect"] is None


async def test_ai_usage_is_tokens_per_investigation_with_no_money_when_no_prices_are_configured(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    usage = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()["summary"]["aiUsage"]
    assert (usage["investigationCount"], usage["callCount"], usage["failedCallCount"]) == (2, 3, 1)
    assert (usage["inputTokens"]["sampleCount"], usage["inputTokens"]["median"]) == (2, 1500)  # 3000 for A, 0 for B
    assert usage["latencyMilliseconds"]["median"] == 500
    assert usage["cost"]["isConfigured"] is False and usage["cost"]["totalEstimatedCost"] is None


async def test_a_settings_change_moves_the_minimum_sample_and_prices_add_an_estimated_cost(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    # Change the shared settings object (monkeypatch restores it); clearing get_settings' cache would leave later tests with a different object from the one the gateway holds.
    monkeypatch.setattr(get_settings(), "metrics_minimum_rating_sample", 2)
    monkeypatch.setattr(get_settings(), "llm_model_prices_json", f'{{"{MODEL}": {{"input_per_million": 2000, "output_per_million": 10000}}}}')
    summary = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()["summary"]
    assert summary["ratings"]["shareCorrect"] == 50.0 and summary["ratings"]["minimumSample"] == 2
    cost = summary["aiUsage"]["cost"]
    assert cost["isConfigured"] is True and cost["unpricedModels"] == []
    assert cost["totalEstimatedCost"] == 11.0  # A: (3000 in * 2000 + 500 out * 10000) per million = 6 + 5; B's one failed call used no tokens
    assert (cost["perInvestigation"]["sampleCount"], cost["perInvestigation"]["median"]) == (2, 5.5)


async def test_every_application_the_user_can_read_gets_a_row_with_its_own_numbers(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:  # noqa: ANN001
    body = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()
    rows = {row["applicationCode"]: row for row in body["applications"]}
    assert set(rows) == set(seed_context.application_ids_by_code)
    assert (rows["CLMJP"]["incidentsOpenedCount"], rows["CLMJP"]["incidentsResolvedCount"]) == (2, 1)
    assert (rows["CHAD"]["incidentsOpenedCount"], rows["CHAD"]["timeToResolve"]["median"]) == (1, 18000)
    assert rows["PADMF"]["incidentsOpenedCount"] == 0 and rows["PADMF"]["timeToResolve"]["sampleCount"] == 0 and rows["PADMF"]["timeToResolve"]["median"] is None
    assert [row["applicationName"] for row in body["applications"]] == sorted(row["applicationName"] for row in body["applications"])


async def test_the_weekly_trend_has_one_point_per_week_of_the_period(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    trend = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()["weeklyTrend"]
    assert [point["weekStart"][:10] for point in trend] == ["2020-03-02", "2020-03-09", "2020-03-16", "2020-03-23"]
    assert [point["incidentsOpenedCount"] for point in trend] == [3, 1, 0, 0]
    assert [point["incidentsResolvedCount"] for point in trend] == [3, 0, 0, 0]
    assert trend[0]["timeToResolve"]["sampleCount"] == 3 and trend[2]["timeToResolve"]["sampleCount"] == 0 and trend[2]["timeToResolve"]["median"] is None


async def test_the_answer_names_what_it_cannot_measure_and_the_definitions_it_relies_on(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    body = (await overview(client, auth_headers, users.KEIGAN_ADMIN)).json()
    assert body["notAvailable"] == [{"metric": "timeToAcknowledge", "reason": "no_acknowledgement_timestamp"}]
    assert {"timeToDetect", "timeToResolve", "ratings", "aiCost"} <= set(body["definitionKeys"])
    assert body["periodStart"].startswith("2020-03-02") and body["periodEnd"].startswith("2020-03-30")


# ── Who sees what ──────────────────────────────────────────────────────────────

async def test_one_application_can_be_asked_for_on_its_own(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:  # noqa: ANN001
    body = (await overview(client, auth_headers, users.KEIGAN_ADMIN, applicationId=seed_context.application_ids_by_code["CLMJP"])).json()
    assert body["summary"]["incidentsOpenedCount"] == 2
    assert [row["applicationCode"] for row in body["applications"]] == ["CLMJP"]
    assert body["applicationId"] == seed_context.application_ids_by_code["CLMJP"]


async def test_a_reader_sees_only_the_applications_they_can_read_never_another_applications_numbers(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    body = (await overview(client, auth_headers, users.CLMJP_AND_PAYAU_READER)).json()  # reader of CLMJP and PAYAU, not CHAD
    assert sorted(row["applicationCode"] for row in body["applications"]) == ["CLMJP", "PAYAU"]
    summary = body["summary"]
    assert (summary["incidentsOpenedCount"], summary["incidentsResolvedCount"]) == (3, 2)  # not CHAD's incident D
    assert by_priority(summary)["P1"] == (1, 1)
    assert summary["timeToResolve"]["sampleCount"] == 2 and summary["timeToResolve"]["p90"] != 18000
    assert summary["investigationCount"] == 2  # CLMJP's two, not CHAD's
    assert summary["ratings"]["ratedCount"] == 1 and summary["ratings"]["incorrectCount"] == 0


async def test_asking_for_an_application_the_user_cannot_read_is_forbidden(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:  # noqa: ANN001
    response = await overview(client, auth_headers, users.CLMJP_AND_PAYAU_READER, applicationId=seed_context.application_ids_by_code["CHAD"])
    assert response.status_code == 403


async def test_someone_with_no_access_sees_empty_numbers_and_is_refused_a_named_application(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> None:  # noqa: ANN001
    body = (await overview(client, auth_headers, users.NO_ACCESS)).json()
    assert body["applications"] == [] and body["summary"]["incidentsOpenedCount"] == 0 and body["summary"]["investigationCount"] == 0
    assert body["summary"]["timeToResolve"]["sampleCount"] == 0
    assert (await overview(client, auth_headers, users.NO_ACCESS, applicationId=seed_context.application_ids_by_code["CLMJP"])).status_code == 403


async def test_an_unknown_application_is_not_found(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    assert (await overview(client, auth_headers, users.KEIGAN_ADMIN, applicationId="00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_signing_in_is_required(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/metrics/overview")).status_code == 401


# ── The period ─────────────────────────────────────────────────────────────────

async def test_a_days_window_is_accepted_and_ends_now(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    response = await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params={"days": 7})
    assert response.status_code == 200, response.text
    body = response.json()
    start, end = (datetime.fromisoformat(body[key].replace("Z", "+00:00")) for key in ("periodStart", "periodEnd"))
    assert end - start == timedelta(days=7) and abs(end - datetime.now(UTC)) < timedelta(minutes=1)


async def test_no_period_at_all_uses_the_default_window(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    assert (await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN))).status_code == 200


@pytest.mark.parametrize(
    "params",
    [{"days": 0}, {"days": -1}, {"days": "many"}, {"days": 100000}, {"days": 7, "from": FROM}, {"to": TO}, {"from": TO, "to": FROM}, {"from": FROM, "to": FROM}, {"from": "2000-01-01T00:00:00Z", "to": TO}, {"from": "yesterday"}],
)
async def test_an_invalid_period_is_refused_with_a_message(client: httpx.AsyncClient, auth_headers: AuthHeaders, params: dict[str, object]) -> None:
    response = await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params=params)
    assert response.status_code == 422, response.text


async def test_the_longest_period_comes_from_the_settings(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_maximum_window_days", 10)
    assert (await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params={"days": 11})).status_code == 422
    assert (await client.get("/api/metrics/overview", headers=await auth_headers(users.KEIGAN_ADMIN), params={"days": 10})).status_code == 200

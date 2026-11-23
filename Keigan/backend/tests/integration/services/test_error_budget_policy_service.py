"""ErrorBudgetPolicyService: the three rules, the finalise gate, the waiver and the messages (spec 30, AC-1, AC-4, AC-9 to AC-15)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from keigan.config.database_config import open_session
from keigan.dtos.action_item_dtos import ActionItemCreateRequest, ActionItemStatusRequest
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.error_budget_entities import ErrorBudgetPolicy, ErrorBudgetPolicyBreach
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder
from keigan.entities.platform_entities import BackgroundJob
from keigan.entities.slo_entities import ServiceLevelIndicator, ServiceLevelObjective, SliMeasurement
from keigan.entities.status_values import ActionItemStatus, ErrorBudgetBreachKind, ErrorBudgetRequirementStatus as Requirement
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_service import ActionItemService
from keigan.services.error_budget_policy_service import ErrorBudgetPolicyService
from keigan.services.error_budget_service import ErrorBudgetService
from keigan.utils.time_utils import floor_to_interval, utc_now
from support.application_graph import ApplicationGraph, create_application_graph

ADMIN_UPN = "admin@example.com"


def admin() -> CurrentUser:
    """A Keigan admin. A new object each time: the access check caches the user's roles on it, and applications are created after the first check."""
    return CurrentUser(user_principal_name=ADMIN_UPN, display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)
TRACKED = "tracked availability"


def now_on_the_grid() -> datetime:
    return floor_to_interval(utc_now(), 5)


async def a_tracked_slo(graph: ApplicationGraph, *, target: float = 99.0, window_days: int = 1) -> tuple[str, str]:
    async with open_session() as session:
        sli = ServiceLevelIndicator(application_id=graph.application_id, service_id=graph.first_service_id, sli_name=TRACKED, sli_kind="availability", data_source_kind="azure_monitor_metrics")
        session.add(sli)
        await session.flush()
        slo = ServiceLevelObjective(sli_id=sli.sli_id, application_id=graph.application_id, target_percentage=target, rolling_window_days=window_days)
        session.add(slo)
        await session.flush()
        return sli.sli_id, slo.slo_id


async def add_data(sli_id: str, *, days: int, bad: list[tuple[datetime, datetime, int]] = (), total: int = 100) -> None:
    """``days`` of 5-minute windows ending now with ``total`` events each; ``bad`` lists (from, to, bad events per window) spans."""
    end = now_on_the_grid()
    async with open_session() as session:
        moment = end - timedelta(days=days)
        while moment < end:
            bad_events = next((count for start, stop, count in bad if start <= moment < stop), 0)
            session.add(SliMeasurement(sli_id=sli_id, measurement_window_start=moment, good_event_count=total - bad_events, total_event_count=total))
            moment += timedelta(minutes=5)


async def an_incident(graph: ApplicationGraph, *, opened_hours_ago: float, resolved_hours_ago: float | None, category: str | None = None) -> str:
    async with open_session() as session:
        now = utc_now()
        incident = Incident(
            application_id=graph.application_id, incident_title="Budget test", opened_at=now - timedelta(hours=opened_hours_ago), resolved_at=now - timedelta(hours=resolved_hours_ago) if resolved_hours_ago is not None else None,
            incident_status="resolved" if resolved_hours_ago is not None else "investigating", incident_category=category, external_incident_number=f"INC{abs(hash((opened_hours_ago, category))) % 10**7:07d}",
        )
        incident.replace_linked_ids("affected_service_links", [graph.first_service_id])
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def turn_policy_on(graph: ApplicationGraph, **fields: object) -> None:
    async with open_session() as session:
        policy = await session.scalar(select(ErrorBudgetPolicy).where(ErrorBudgetPolicy.application_id == graph.application_id))
        policy.is_enabled = True
        for name, value in fields.items():
            setattr(policy, name, value)


async def evaluate(graph: ApplicationGraph, *, hours_later: float = 0) -> dict[str, int]:
    """One evaluation, ``hours_later`` after now (a day later the incident's figure is final)."""
    async with open_session() as session:
        return await ErrorBudgetPolicyService(session).evaluate_application(graph.application_id, now=utc_now() + timedelta(hours=hours_later))


GRAPH_OWN_BREACH_IDS: set[str] = set()  # the application graph comes with a breach of its own (for the integrity tests); these tests look at the ones they cause


async def new_graph() -> ApplicationGraph:
    graph = await create_application_graph()
    async with open_session() as session:
        GRAPH_OWN_BREACH_IDS.update((await session.scalars(select(ErrorBudgetPolicyBreach.error_budget_policy_breach_id).where(ErrorBudgetPolicyBreach.application_id == graph.application_id))).all())
    return graph


async def breaches_of(graph: ApplicationGraph, kind: str | None = None) -> list[ErrorBudgetPolicyBreach]:
    async with open_session() as session:
        rows = (await session.scalars(select(ErrorBudgetPolicyBreach).where(ErrorBudgetPolicyBreach.application_id == graph.application_id))).all()
        return [row for row in rows if row.error_budget_policy_breach_id not in GRAPH_OWN_BREACH_IDS and (kind is None or row.breach_kind == kind)]


async def an_incident_that_used_42_percent(graph: ApplicationGraph, *, resolved_hours_ago: float) -> tuple[str, str]:
    """The tracked SLO has a one-day window at 99 % (288 bad events allowed); 12 windows of 10 bad events during the incident use 120 of them: 41.7 %."""
    sli_id, _ = await a_tracked_slo(graph)
    end = now_on_the_grid() - timedelta(hours=resolved_hours_ago)
    await add_data(sli_id, days=3, bad=[(end - timedelta(hours=1), end, 10)])
    return sli_id, await an_incident(graph, opened_hours_ago=resolved_hours_ago + 1, resolved_hours_ago=resolved_hours_ago)


# ── Rule 1: one incident ─────────────────────────────────────────────────────────────────────────


async def test_with_the_policy_off_impacts_are_computed_but_nothing_else_happens(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    counts = await evaluate(graph)
    assert counts["impacts"] >= 1 and counts["breaches"] == 0 and not await breaches_of(graph)
    async with open_session() as session:
        jobs = [job for job in (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == "generate_postmortem"))).all() if job.job_payload_json.get("incident_id") == incident_id]
    assert jobs == []


async def test_a_breach_on_a_resolved_incident_drafts_a_postmortem_once_and_tells_the_leads_once(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    async with open_session() as session:
        session.add(Stakeholder(application_id=graph.application_id, display_name="Lena Lead", email_address="lena.lead@example.com", stakeholder_role="lead"))
    await turn_policy_on(graph)
    await evaluate(graph)
    await evaluate(graph)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    assert breach.measured_share_percent == 41.7 and breach.threshold_percent == 20.0 and breach.is_provisional is True and breach.requirement_status == Requirement.OPEN and breach.notified_at is not None
    async with open_session() as session:
        jobs = [job for job in (await session.scalars(select(BackgroundJob).where(BackgroundJob.job_type == "generate_postmortem"))).all() if job.job_payload_json.get("incident_id") == incident_id]
        emails = (await session.scalars(select(NotificationDelivery).where(NotificationDelivery.application_id == graph.application_id, NotificationDelivery.notification_type == "error_budget_policy"))).all()
    assert len(jobs) == 1 and jobs[0].job_payload_json["generation_trigger"] == "error_budget_policy"
    assert [email.recipient_address for email in emails] == ["lena.lead@example.com"]


async def test_a_provisional_breach_whose_share_falls_back_is_withdrawn(seed_context) -> None:
    graph = await new_graph()
    sli_id, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    assert await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    async with open_session() as session:  # late data shows the errors were fewer
        await session.execute(update(SliMeasurement).where(SliMeasurement.sli_id == sli_id).values(good_event_count=100))
    await evaluate(graph)
    assert not await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)


async def test_too_little_data_makes_no_breach(seed_context) -> None:
    graph = await new_graph()
    sli_id, _ = await a_tracked_slo(graph)
    await add_data(sli_id, days=1, total=1)  # 288 events in the day: below the minimum
    await an_incident(graph, opened_hours_ago=3, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    assert not await breaches_of(graph)


# ── The gate, the requirement and the waiver ─────────────────────────────────────────────────────


async def test_a_final_open_breach_blocks_finalising_until_a_top_prevent_item_is_accepted(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    await evaluate(graph, hours_later=23)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    assert breach.is_provisional is False
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="top-priority 'prevent'"):
            await ErrorBudgetPolicyService(session).ensure_finalising_is_allowed(incident_id)
        session.add(ActionItem(application_id=graph.application_id, incident_id=incident_id, item_source_kind="postmortem", item_title="Proposed only", action_type="prevent", action_priority="top", item_status=ActionItemStatus.PROPOSED))
        await session.flush()
        with pytest.raises(BusinessValidationException):  # a suggestion nobody accepted does not count
            await ErrorBudgetPolicyService(session).ensure_finalising_is_allowed(incident_id)
        item = ActionItem(application_id=graph.application_id, incident_id=incident_id, item_source_kind="postmortem", item_title="Pool alert", action_type="prevent", action_priority="top", item_status=ActionItemStatus.OPEN)
        session.add(item)
        await session.flush()
        await ErrorBudgetPolicyService(session).ensure_finalising_is_allowed(incident_id)  # passes now
        item_id = item.action_item_id
    assert item_id


async def test_a_provisional_breach_does_not_block_finalising(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    async with open_session() as session:
        await ErrorBudgetPolicyService(session).ensure_finalising_is_allowed(incident_id)


async def test_the_requirement_is_met_by_a_final_postmortem_with_the_item_and_reopens_when_the_item_is_dropped(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    await evaluate(graph, hours_later=23)
    async with open_session() as session:
        item = ActionItem(
            application_id=graph.application_id, incident_id=incident_id, item_source_kind="manual", item_title="Pool alert", action_type="prevent", action_priority="top", item_status=ActionItemStatus.OPEN,
            owner_stakeholder_id=None, created_by_user_principal_name="x",
        )
        postmortem = PostmortemReport(incident_id=incident_id, report_title="Postmortem", report_status="final")
        session.add_all([item, postmortem])
        await session.flush()
        item_id = item.action_item_id
        await ErrorBudgetPolicyService(session).refresh_requirement(incident_id)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    assert breach.requirement_status == Requirement.MET and breach.qualifying_action_item_id == item_id
    async with open_session() as session:  # AC-11: turning the item to won't do reopens the requirement at once
        await ActionItemService(session).change_status(admin(), item_id, ActionItemStatusRequest(status=ActionItemStatus.WONT_DO, reason_text="No longer relevant at all."))
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    assert breach.requirement_status == Requirement.OPEN and breach.qualifying_action_item_id is None


async def test_a_waiver_needs_a_reason_of_the_minimum_length_lets_finalising_pass_and_is_audited(seed_context) -> None:
    graph = await new_graph()
    _, incident_id = await an_incident_that_used_42_percent(graph, resolved_hours_ago=2)
    await turn_policy_on(graph)
    await evaluate(graph)
    await evaluate(graph, hours_later=23)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.SINGLE_INCIDENT)
    breach_id = breach.error_budget_policy_breach_id
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="at least 20"):
            await ErrorBudgetService(session).waive(admin(), breach_id, "too short")
        dto = await ErrorBudgetService(session).waive(admin(), breach_id, "The SLI counted a planned load test as errors.")
    assert dto.requirement_status == "waived" and dto.waived_by == ADMIN_UPN
    async with open_session() as session:
        await ErrorBudgetPolicyService(session).ensure_finalising_is_allowed(incident_id)
        with pytest.raises(BusinessValidationException, match="Only an open requirement"):
            await ErrorBudgetService(session).waive(admin(), breach_id, "Trying to waive it a second time.")
        from keigan.entities.platform_entities import AuditEvent

        actions = set((await session.scalars(select(AuditEvent.action_name).where(AuditEvent.target_entity_id == breach_id))).all())
    assert "error_budget_breach.waive" in actions


# ── Rule 2: one class of outage ──────────────────────────────────────────────────────────────────


async def test_a_class_of_outage_over_the_threshold_opens_one_breach_that_a_top_item_meets(seed_context) -> None:
    graph = await new_graph()
    sli_id, _ = await a_tracked_slo(graph)
    end = now_on_the_grid()
    first_window, second_window = (end - timedelta(hours=4), end - timedelta(hours=3)), (end - timedelta(hours=2), end - timedelta(hours=1))
    await add_data(sli_id, days=4, bad=[(*first_window, 20), (*second_window, 20)])
    for hours_ago in (3, 1):
        await an_incident(graph, opened_hours_ago=hours_ago + 1, resolved_hours_ago=hours_ago, category="capacity")
    await turn_policy_on(graph, outage_class_window_days=7)
    await evaluate(graph)
    await evaluate(graph)  # a second evaluation does not open a second breach
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.OUTAGE_CLASS)
    assert breach.recurrence_category == "capacity" and breach.requirement_status == Requirement.OPEN and breach.measured_share_percent > 20.0
    async with open_session() as session:
        item = await ErrorBudgetService(session).create_class_item(
            admin(), breach.error_budget_policy_breach_id, ActionItemCreateRequest(item_title="Add a connection pool limit", action_type="prevent", action_priority="low", due_on=(utc_now() + timedelta(days=14)).date()),
        )
    assert item.action_priority == "top" and item.source_kind == "error_budget_policy"
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.OUTAGE_CLASS)
    assert breach.requirement_status == Requirement.MET and breach.qualifying_action_item_id == item.action_item_id
    await evaluate(graph)
    assert len(await breaches_of(graph, ErrorBudgetBreachKind.OUTAGE_CLASS)) == 1  # met is not re-opened by the same quarter


# ── Rule 3: a budget used up ─────────────────────────────────────────────────────────────────────


async def test_a_used_up_budget_opens_a_breach_with_the_teams_own_words_and_ends_when_the_slo_is_back_in_target(seed_context) -> None:
    graph = await new_graph()
    sli_id, _ = await a_tracked_slo(graph, target=99.9)
    await add_data(sli_id, days=2, bad=[(now_on_the_grid() - timedelta(hours=12), now_on_the_grid(), 10)])  # 10 % bad in the last half day: below the 99.9 % target
    await turn_policy_on(graph, exhausted_budget_guidance_text="Pause feature releases until the SLO is met again.")
    await evaluate(graph)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.BUDGET_EXHAUSTED)
    assert breach.requirement_status == Requirement.OPEN and breach.sli_name_text == TRACKED
    async with open_session() as session:
        listed = await ErrorBudgetService(session).list_breaches(admin(), [graph.application_id], None, [ErrorBudgetBreachKind.BUDGET_EXHAUSTED.value])
    assert listed[0].guidance_text == "Pause feature releases until the SLO is met again."
    async with open_session() as session:
        await session.execute(update(SliMeasurement).where(SliMeasurement.sli_id == sli_id).values(good_event_count=100))
    await evaluate(graph)
    (breach,) = await breaches_of(graph, ErrorBudgetBreachKind.BUDGET_EXHAUSTED)
    assert breach.requirement_status == Requirement.ENDED

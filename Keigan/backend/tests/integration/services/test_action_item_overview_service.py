"""ActionItemOverviewService: completion figures, the needs-attention list and the repeated incidents view (spec 29, 4.4; AC-18, AC-19)."""

from __future__ import annotations

import json
from datetime import timedelta
from itertools import count

import pytest
from sqlalchemy import update

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.dtos.action_item_dtos import ActionItemOverviewResponse
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach
from keigan.entities.incident_entities import Incident, PostmortemReport
from keigan.exceptions.keigan_exceptions import BusinessValidationException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_overview_service import ActionItemOverviewService
from keigan.services.action_item_rules import local_today
from keigan.utils.time_utils import utc_now
from support.application_graph import ApplicationGraph, create_application_graph

_numbers = count(1)


def admin() -> CurrentUser:
    """A Keigan admin. A new object each time: the access check caches the user's roles on it."""
    return CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


def stranger() -> CurrentUser:
    return CurrentUser(user_principal_name="nobody@example.com", display_name="Nobody", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False)


async def a_clean_application() -> ApplicationGraph:
    """The shared graph application comes with one open follow-up of its own (something else refers to it); these tests count items, so it is closed without being accepted."""
    graph = await create_application_graph()
    async with open_session() as session:
        await session.execute(update(ActionItem).where(ActionItem.application_id == graph.application_id).values(item_status="wont_do"))
    return graph


async def overview(application_id: str, *, user: CurrentUser | None = None, days: int | None = None) -> ActionItemOverviewResponse:
    async with open_session() as session:
        return await ActionItemOverviewService(session).overview(user or admin(), [application_id], days)


async def add_item(
    application_id: str, *, status: str = "open", priority: str = "normal", action_type: str = "prevent", due_in_days: int | None = 10, accepted_days_ago: float | None = 5,
    completed_days_ago: float | None = None, incident_id: str | None = None, postmortem_id: str | None = None, owner_id: str | None = None, title: str = "An item", created_days_ago: float = 0,
) -> str:
    async with open_session() as session:
        application = await session.get(Application, application_id)
        today = local_today(application.time_zone_name, utc_now())
        now = utc_now()
        item = ActionItem(
            application_id=application_id, incident_id=incident_id, postmortem_id=postmortem_id, item_source_kind="postmortem" if postmortem_id else "manual", item_title=title,
            action_type=action_type, action_priority=priority, item_status=status, owner_stakeholder_id=owner_id,
            due_on=today + timedelta(days=due_in_days) if due_in_days is not None else None, original_due_on=today + timedelta(days=due_in_days) if due_in_days is not None else None,
            accepted_at=now - timedelta(days=accepted_days_ago) if accepted_days_ago is not None else None, completed_at=now - timedelta(days=completed_days_ago) if completed_days_ago is not None else None,
        )
        item.created_at = now - timedelta(days=created_days_ago)
        session.add(item)
        await session.flush()
        return item.action_item_id


async def add_incident(graph: ApplicationGraph, *, opened_days_ago: float, category: str | None = "capacity", priority: str | None = None, resolved_days_ago: float | None = None, with_service: bool = True) -> str:
    async with open_session() as session:
        now = utc_now()
        incident = Incident(
            application_id=graph.application_id, incident_title="Overview test", opened_at=now - timedelta(days=opened_days_ago), keigan_priority=priority, incident_category=category,
            resolved_at=now - timedelta(days=resolved_days_ago) if resolved_days_ago is not None else None, incident_status="resolved" if resolved_days_ago is not None else "investigating",
            external_incident_number=f"INC{next(_numbers):07d}",
        )
        if with_service:
            incident.replace_linked_ids("affected_service_links", [graph.first_service_id])
        session.add(incident)
        await session.flush()
        return incident.incident_id


async def add_postmortem(incident_id: str, *, status: str = "final", finalized_days_ago: float | None = None) -> str:
    async with open_session() as session:
        postmortem = PostmortemReport(incident_id=incident_id, report_title="Postmortem", report_status=status, finalized_at=utc_now() - timedelta(days=finalized_days_ago) if finalized_days_ago is not None else None)
        session.add(postmortem)
        await session.flush()
        return postmortem.postmortem_id


# ── Completion ───────────────────────────────────────────────────────────────────────────────────


async def test_the_completion_figures_count_this_applications_items_and_say_how_many_they_rest_on(seed_context) -> None:
    graph = await a_clean_application()
    await add_item(graph.application_id, status="done", accepted_days_ago=20, completed_days_ago=10)
    await add_item(graph.application_id, status="done", accepted_days_ago=12, completed_days_ago=8)
    await add_item(graph.application_id, status="open", due_in_days=-3)
    await add_item(graph.application_id, status="wont_do", accepted_days_ago=9, completed_days_ago=2)
    await add_item(graph.application_id, status="open", accepted_days_ago=300, due_in_days=4)  # accepted before the period, still open: counted as open, not as accepted
    result = await overview(graph.application_id, days=90)
    figures = result.completion
    assert (figures.accepted_count, figures.done_count, figures.wont_do_count, figures.open_count, figures.overdue_count) == (4, 2, 1, 2, 1)
    assert figures.completion_rate == pytest.approx(66.7, abs=0.05) and figures.completion_rate_sample_count == 3
    assert figures.median_days_to_complete == 7.0 and figures.median_sample_count == 2
    assert [row.application_id for row in result.by_application] == [graph.application_id] and result.by_application[0].done_count == 2


async def test_an_item_older_than_the_period_is_left_out_of_the_rate_but_never_out_of_the_open_count(seed_context) -> None:
    graph = await a_clean_application()
    await add_item(graph.application_id, status="done", accepted_days_ago=200, completed_days_ago=150)
    result = await overview(graph.application_id, days=30)
    assert result.completion.accepted_count == 0 and result.completion.completion_rate is None and result.completion.completion_rate_sample_count == 0


async def test_a_period_outside_the_allowed_range_is_refused_with_the_limit(seed_context) -> None:
    graph = await a_clean_application()
    maximum = get_settings().action_items_overview_maximum_days
    for days in (0, maximum + 1):
        with pytest.raises(BusinessValidationException, match=str(maximum)):
            await overview(graph.application_id, days=days)


async def test_the_default_period_is_the_setting(seed_context) -> None:
    graph = await a_clean_application()
    result = await overview(graph.application_id)
    assert result.period_days == get_settings().action_items_overview_default_days


async def test_someone_who_may_read_no_application_gets_an_empty_overview(seed_context) -> None:
    graph = await a_clean_application()
    await add_item(graph.application_id, due_in_days=-4, priority="top")
    result = await overview(graph.application_id, user=stranger())
    assert result.needs_attention == [] and result.by_application == [] and result.repeats == [] and result.completion.accepted_count == 0


async def test_the_overview_names_applications_and_incidents_never_people(seed_context) -> None:
    graph = await a_clean_application()
    await add_item(graph.application_id, due_in_days=-4, priority="top")
    text = json.dumps((await overview(graph.application_id)).model_dump(by_alias=True, mode="json")).lower()
    assert "owner" not in text and "stakeholder" not in text and "display" not in text


# ── Needs attention ──────────────────────────────────────────────────────────────────────────────


def kinds(result: ActionItemOverviewResponse) -> list[tuple[str, str]]:
    return [(entry.kind, entry.record_id) for entry in result.needs_attention]


async def test_overdue_items_and_top_priority_items_without_an_owner_are_listed_most_urgent_first(seed_context) -> None:
    graph = await a_clean_application()
    late_normal = await add_item(graph.application_id, due_in_days=-9)
    late_top = await add_item(graph.application_id, due_in_days=-2, priority="top", owner_id=None)
    fine = await add_item(graph.application_id, due_in_days=5)
    closed_late = await add_item(graph.application_id, status="done", due_in_days=-20, completed_days_ago=1)
    result = await overview(graph.application_id)
    assert kinds(result) == [("overdue_item", late_top), ("overdue_item", late_normal), ("top_priority_unowned", late_top)]
    assert fine not in {entry.record_id for entry in result.needs_attention} and closed_late not in {entry.record_id for entry in result.needs_attention}
    assert result.needs_attention[0].parameters["daysOverdue"] == 2 and result.needs_attention[0].parameters["priority"] == "top"


async def test_an_open_policy_requirement_is_listed_and_a_met_one_is_not(seed_context) -> None:
    graph = await a_clean_application()  # its own breach, on its incident, is already met
    breached_incident = await add_incident(graph, opened_days_ago=3)
    async with open_session() as session:
        open_breach = ErrorBudgetPolicyBreach(
            application_id=graph.application_id, breach_kind="single_incident", incident_id=breached_incident, incident_reference_text="INC0001234", measured_share_percent=31.5, threshold_percent=20.0, window_days=30,
            detected_at=utc_now(), requirement_status="open", requirement_changed_at=utc_now(),
        )
        met_breach = ErrorBudgetPolicyBreach(
            application_id=graph.application_id, breach_kind="budget_exhausted", sli_name_text="Availability", window_days=30, detected_at=utc_now(), requirement_status="met", requirement_changed_at=utc_now(),
        )
        session.add_all([open_breach, met_breach])
        await session.flush()
        open_id = open_breach.error_budget_policy_breach_id
    result = await overview(graph.application_id)
    entry = next(entry for entry in result.needs_attention if entry.kind == "policy_breach_open")
    assert entry.record_id == open_id and entry.record_kind == "error_budget_policy_breach" and entry.title == "INC0001234"
    assert entry.parameters["breachKind"] == "single_incident" and entry.parameters["sharePercent"] == 31.5
    assert sum(1 for each in result.needs_attention if each.kind == "policy_breach_open") == 1


async def test_a_resolved_serious_incident_without_a_final_postmortem_is_listed_after_the_grace_days(seed_context) -> None:
    graph = await a_clean_application()
    grace = get_settings().action_items_postmortem_grace_days
    missing = await add_incident(graph, opened_days_ago=grace + 4, resolved_days_ago=grace + 2, priority="P1", category="network")
    recent = await add_incident(graph, opened_days_ago=2, resolved_days_ago=0.5, priority="P1", category="deploy")
    minor = await add_incident(graph, opened_days_ago=grace + 4, resolved_days_ago=grace + 2, priority="P4", category="cert")
    done = await add_incident(graph, opened_days_ago=grace + 5, resolved_days_ago=grace + 3, priority="P2", category="dns")
    await add_postmortem(done, status="final", finalized_days_ago=1)
    drafted = await add_incident(graph, opened_days_ago=grace + 5, resolved_days_ago=grace + 3, priority="P2", category="disk")
    await add_postmortem(drafted, status="draft")
    flagged = {entry.record_id for entry in (await overview(graph.application_id)).needs_attention if entry.kind == "postmortem_missing"}
    assert flagged == {missing, drafted} and recent not in flagged and minor not in flagged and done not in flagged


async def test_suggestions_nobody_has_answered_for_a_while_are_listed_once_per_postmortem(seed_context) -> None:
    graph = await a_clean_application()
    grace = get_settings().action_items_postmortem_grace_days
    postmortem_id = await add_postmortem(graph.incident_id, status="draft")
    for _ in range(3):
        await add_item(graph.application_id, status="proposed", postmortem_id=postmortem_id, incident_id=graph.incident_id, accepted_days_ago=None, created_days_ago=grace + 2)
    fresh_postmortem = await add_postmortem(await add_incident(graph, opened_days_ago=1), status="draft")
    await add_item(graph.application_id, status="proposed", postmortem_id=fresh_postmortem, accepted_days_ago=None, created_days_ago=0)
    waiting = [entry for entry in (await overview(graph.application_id)).needs_attention if entry.kind == "proposed_waiting"]
    assert [entry.record_id for entry in waiting] == [postmortem_id] and waiting[0].parameters["proposedCount"] == 3 and waiting[0].record_kind == "postmortem"


# ── Repeats ──────────────────────────────────────────────────────────────────────────────────────


async def test_a_repeat_reports_what_had_happened_to_the_earlier_follow_ups_at_that_moment(seed_context) -> None:
    graph = await a_clean_application()
    first = await add_incident(graph, opened_days_ago=60, resolved_days_ago=59)
    second = await add_incident(graph, opened_days_ago=30, resolved_days_ago=29)
    third = await add_incident(graph, opened_days_ago=5, resolved_days_ago=4)
    await add_postmortem(first, finalized_days_ago=55)
    await add_postmortem(second, finalized_days_ago=25)
    fixed_after_first = await add_item(graph.application_id, status="done", incident_id=first, accepted_days_ago=55, completed_days_ago=40, title="Raise the pool size")
    open_after_second = await add_item(graph.application_id, status="open", incident_id=second, accepted_days_ago=25, title="Add a pool alert")
    await add_item(graph.application_id, status="open", incident_id=second, action_type="detect", accepted_days_ago=25, title="Not a prevent item")
    groups = (await overview(graph.application_id)).repeats
    assert len(groups) == 1
    group = groups[0]
    assert group.recurrence_category == "capacity" and group.service_name == "first" and [each.incident_id for each in group.incidents] == [first, second, third]
    assert group.incidents[0].outcome is None
    assert group.incidents[1].outcome == "repeated_after_done" and [(each.action_item_id, each.status_at_repeat) for each in group.incidents[1].earlier_prevent_items] == [(fixed_after_first, "done")]
    assert group.incidents[2].outcome == "repeated_while_open"
    assert {(each.action_item_id, each.status_at_repeat) for each in group.incidents[2].earlier_prevent_items} == {(fixed_after_first, "done"), (open_after_second, "not_done")}


async def test_a_repeat_without_a_postmortem_or_without_a_tracked_prevent_item_says_so(seed_context) -> None:
    graph = await a_clean_application()
    network = [await add_incident(graph, opened_days_ago=40, category="network"), await add_incident(graph, opened_days_ago=10, category="network")]
    deploy_first = await add_incident(graph, opened_days_ago=40, category="deploy")
    await add_postmortem(deploy_first, finalized_days_ago=35)
    deploy_second = await add_incident(graph, opened_days_ago=10, category="deploy")
    groups = {group.recurrence_category: group for group in (await overview(graph.application_id)).repeats}
    assert groups["network"].incidents[1].outcome == "no_postmortem" and [each.incident_id for each in groups["network"].incidents] == network
    assert groups["deploy"].incidents[1].outcome == "no_prevent_item" and groups["deploy"].incidents[1].incident_id == deploy_second


async def test_a_follow_up_finished_after_the_repeat_was_still_open_when_it_came_back(seed_context) -> None:
    graph = await a_clean_application()
    first = await add_incident(graph, opened_days_ago=50, category="memory")
    await add_postmortem(first, finalized_days_ago=45)
    await add_incident(graph, opened_days_ago=10, category="memory")
    await add_item(graph.application_id, status="done", incident_id=first, accepted_days_ago=45, completed_days_ago=3)
    assert (await overview(graph.application_id)).repeats[0].incidents[1].outcome == "repeated_while_open"


async def test_incidents_with_no_named_service_and_single_incidents_are_not_repeats(seed_context) -> None:
    graph = await a_clean_application()
    await add_incident(graph, opened_days_ago=20, category="cert", with_service=False)
    await add_incident(graph, opened_days_ago=10, category="cert", with_service=False)
    await add_incident(graph, opened_days_ago=10, category="queue")
    assert (await overview(graph.application_id)).repeats == []


async def test_repeats_look_back_only_as_far_as_the_window(seed_context) -> None:
    graph = await a_clean_application()
    window = get_settings().action_items_repeat_window_days
    await add_incident(graph, opened_days_ago=window + 5, category="disk")
    await add_incident(graph, opened_days_ago=window - 5, category="disk")
    assert (await overview(graph.application_id)).repeats == []

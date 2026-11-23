"""The weekly review sections of the digest and the review record (spec 31, AC-1 to AC-7)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.action_item_entities import ActionItem
from keigan.entities.application_entities import Application
from keigan.entities.error_budget_entities import ErrorBudgetPolicyBreach, IncidentBudgetImpact
from keigan.entities.incident_entities import Incident
from keigan.entities.notification_entities import Stakeholder
from keigan.entities.platform_entities import AuditEvent
from keigan.entities.slo_entities import IntelligenceReport
from keigan.exceptions.keigan_exceptions import BusinessValidationException, ForbiddenException
from keigan.security.current_user import CurrentUser
from keigan.services.action_item_rules import local_today
from keigan.services.intelligence_service import IntelligenceService
from keigan.services.weekly_review_facts import review_fact_lines, weekly_review_sections
from keigan.utils.time_utils import utc_now
from support.application_graph import create_application_graph


def admin() -> CurrentUser:
    return CurrentUser(user_principal_name="admin@example.com", display_name="Admin", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=True)


async def sections_for(application_id: str, maximum: int = 10) -> dict:
    now = utc_now()
    async with open_session() as session:
        application = await session.get(Application, application_id)
        return await weekly_review_sections(session, application, now - timedelta(days=7), now, now, maximum)


async def item(application_id: str, title: str, *, due_days: int, status: str = "open", priority: str = "normal", owner_id: str | None = None, **fields: object) -> None:
    async with open_session() as session:
        application = await session.get(Application, application_id)
        today = local_today(application.time_zone_name, utc_now())
        session.add(ActionItem(
            application_id=application_id, item_source_kind="manual", item_title=title, action_type="prevent", action_priority=priority, item_status=status, owner_stakeholder_id=owner_id,
            due_on=today + timedelta(days=due_days), **fields,
        ))


async def test_the_budget_section_lists_the_weeks_incidents_by_share_and_the_open_breaches(seed_context) -> None:
    graph = await create_application_graph()
    now = utc_now()
    async with open_session() as session:
        for number, share in (("INC1", 12.0), ("INC2", 41.7)):
            incident = Incident(application_id=graph.application_id, incident_title=f"Incident {number}", opened_at=now - timedelta(days=2), external_incident_number=number)
            session.add(incident)
            await session.flush()
            session.add(IncidentBudgetImpact(
                incident_id=incident.incident_id, application_id=graph.application_id, slo_id=None, sli_name_text="availability", target_percentage=99.0, budget_window_days=1, impact_window_start=now, impact_window_end=now,
                budget_window_start=now, budget_window_end=now, bad_event_count=1, impact_total_event_count=2, window_total_event_count=3, data_coverage_percent=100.0, budget_share_percent=share, is_service_matched=True,
                impact_state="final", evaluated_at=now,
            ))
        session.add(Incident(application_id=graph.application_id, incident_title="No figure", opened_at=now - timedelta(days=1), external_incident_number="INC3"))
        session.add(Incident(application_id=graph.application_id, incident_title="Last month", opened_at=now - timedelta(days=30), external_incident_number="INC0"))
        session.add(ErrorBudgetPolicyBreach(
            application_id=graph.application_id, breach_kind="single_incident", slo_id=None, sli_name_text="availability", measured_share_percent=41.7, window_days=1, detected_at=now - timedelta(days=1),
            requirement_status="open", requirement_changed_at=now, incident_reference_text="INC2",
        ))
    budget = (await sections_for(graph.application_id))["budget"]
    assert [row["incidentNumber"] for row in budget["incidents"]] == ["INC2", "INC1"] and budget["incidentsWithoutFigureCount"] >= 1
    # (two breaches were detected this week: the application graph comes with a met one of its own)
    assert budget["breachesOpenedCount"] == 2 and [row["incidentNumber"] for row in budget["openBreaches"]] == ["INC2"]
    assert budget["policyIsEnabled"] is False


async def test_the_action_item_section_counts_and_lists_overdue_longest_first_up_to_the_maximum(seed_context) -> None:
    graph = await create_application_graph()
    now = utc_now()
    async with open_session() as session:
        owner = Stakeholder(application_id=graph.application_id, display_name="Olive Owner", email_address="olive@example.com")
        session.add(owner)
        await session.flush()
        owner_id = owner.stakeholder_id
    await item(graph.application_id, "Late by 3", due_days=-3, owner_id=owner_id)
    await item(graph.application_id, "Late by 10", due_days=-10, owner_id=owner_id, priority="high")
    await item(graph.application_id, "Late by 1", due_days=-1)
    await item(graph.application_id, "Due next week", due_days=5)
    await item(graph.application_id, "Top and nobody's", due_days=20, priority="top")
    await item(graph.application_id, "Done this week", due_days=-2, status="done", completed_at=now - timedelta(days=1))
    await item(graph.application_id, "Done long ago", due_days=-90, status="done", completed_at=now - timedelta(days=60))
    await item(graph.application_id, "Accepted this week", due_days=9, accepted_at=now - timedelta(days=2))
    await item(graph.application_id, "A suggestion", due_days=9, status="proposed")
    section = (await sections_for(graph.application_id, maximum=2))["actionItems"]
    graph_own = 1  # the application graph comes with one open item of its own
    assert section["openCount"] == 6 + graph_own and section["overdueCount"] == 3
    assert [row["title"] for row in section["overdue"]] == ["Late by 10", "Late by 3"] and section["overdue"][0]["owner"] == "Olive Owner" and section["overdue"][0]["daysOverdue"] == 10
    assert section["doneThisWeekCount"] == 1 and section["acceptedThisWeekCount"] >= 1 and section["suggestedWaitingCount"] == 1
    assert section["topPriorityWithoutOwner"] == ["Top and nobody's"]


async def test_overdue_follows_the_applications_time_zone(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        (await session.get(Application, graph.application_id)).time_zone_name = "Pacific/Kiritimati"  # UTC+14: it is already tomorrow there
        today_there = local_today("Pacific/Kiritimati", utc_now())
        session.add(ActionItem(application_id=graph.application_id, item_source_kind="manual", item_title="Due yesterday there", action_type="prevent", action_priority="normal", item_status="open", due_on=today_there - timedelta(days=1)))
    section = (await sections_for(graph.application_id))["actionItems"]
    assert [row["daysOverdue"] for row in section["overdue"]] == [1]


async def test_the_facts_carry_both_sections_and_the_weekly_digest_stores_them(seed_context) -> None:
    graph = await create_application_graph()
    await item(graph.application_id, "Late by 3", due_days=-3)
    sections = await sections_for(graph.application_id)
    lines = review_fact_lines(sections)
    assert any(line.startswith("Error budget:") for line in lines) and any("overdue" in line for line in lines) and any(line.startswith("Policy:") for line in lines)
    async with open_session() as session:
        report = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "weekly_digest", None)
        assert {"budget", "actionItems"} <= set(report.report_sections_json) and "## Error budget" in report.report_markdown and "## Follow-ups" in report.report_markdown
        proactive = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "proactive_alert", None)
        assert "budget" not in proactive.report_sections_json and "## Follow-ups" not in proactive.report_markdown


async def test_an_admin_reviews_a_weekly_digest_once_and_the_note_is_sanitised_and_audited(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        report = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "weekly_digest", None)
        report_id = report.intelligence_report_id
        before = report.report_markdown
    async with open_session() as session:
        reviewed = await IntelligenceService(session).review_report(admin(), report_id, "Went through it. Mail me at someone@example.com <script>x</script>")
    assert reviewed.reviewed_by == "admin@example.com" and reviewed.reviewed_at is not None and "someone@example.com" not in reviewed.review_note and "<script>" not in reviewed.review_note.replace("\\<", "")
    assert reviewed.report_markdown == before
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="already reviewed"):
            await IntelligenceService(session).review_report(admin(), report_id, None)
        actions = set((await session.scalars(select(AuditEvent.action_name).where(AuditEvent.target_entity_id == report_id))).all())
    assert "intelligence_report.review" in actions


async def test_a_proactive_alert_is_not_reviewed_and_a_reader_cannot_review(seed_context) -> None:
    graph = await create_application_graph()
    async with open_session() as session:
        proactive = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "proactive_alert", None)
        weekly = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "weekly_digest", None)
        proactive_id, weekly_id = proactive.intelligence_report_id, weekly.intelligence_report_id
    async with open_session() as session:
        with pytest.raises(BusinessValidationException, match="Only a weekly digest"):
            await IntelligenceService(session).review_report(admin(), proactive_id, None)
        outsider = CurrentUser(user_principal_name="nobody@example.com", display_name="Nobody", email_address=None, group_names=frozenset(), group_object_ids=frozenset(), is_keigan_admin=False)
        with pytest.raises(ForbiddenException):
            await IntelligenceService(session).review_report(outsider, weekly_id, None)
        assert (await session.get(IntelligenceReport, weekly_id)).reviewed_at is None

"""RunbookHealthService: the figures behind each runbook's findings, per runbook and per application (spec 32, AC-4, AC-6)."""

from __future__ import annotations

from datetime import timedelta

from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.entities.incident_entities import Investigation
from keigan.entities.knowledge_entities import Runbook
from keigan.services.intelligence_service import IntelligenceService
from keigan.services.runbook_health_service import RunbookHealthService
from keigan.utils.time_utils import utc_now
from support.application_graph import create_application_graph


async def a_runbook(application_id: str, title: str, *, symptoms: str | None = "Timeouts on submit", steps: str | None = "1. Restart the pool", age_days: int = 10, referenced: int = 1) -> str:
    async with open_session() as session:
        runbook = Runbook(
            application_id=application_id, runbook_title=title, trigger_symptoms_text=symptoms, runbook_steps_markdown=steps, times_referenced_count=referenced,
            created_at=utc_now() - timedelta(days=age_days), updated_at=utc_now() - timedelta(days=age_days),
        )
        session.add(runbook)
        await session.flush()
        return runbook.runbook_id


async def investigation_that_matched(application_id: str, runbook_id: str, verdict: str | None) -> None:
    async with open_session() as session:
        investigation = Investigation(application_id=application_id, user_feedback_verdict=verdict)
        session.add(investigation)
        await session.flush()
        investigation.replace_linked_ids("matched_runbook_links", [runbook_id])


async def test_the_counts_belong_to_the_runbook_and_the_findings_follow_the_rules(seed_context) -> None:
    graph = await create_application_graph()
    wrong = await a_runbook(graph.application_id, "Often wrong")
    fine = await a_runbook(graph.application_id, "Fine")
    for verdict in ("incorrect", "incorrect", "incorrect", "correct", None):
        await investigation_that_matched(graph.application_id, wrong, verdict)
    await investigation_that_matched(graph.application_id, fine, "correct")
    await a_runbook(graph.application_id, "Never used and old", age_days=90, referenced=0)
    await a_runbook(graph.application_id, "Empty", symptoms=None, steps="  ")
    async with open_session() as session:
        rows = {row.runbook.runbook_title: row for row in await RunbookHealthService(session).rows(graph.application_id)}
    assert (rows["Often wrong"].matched_count, rows["Often wrong"].rated_count, rows["Often wrong"].incorrect_count) == (5, 4, 3)
    assert [finding.kind for finding in rows["Often wrong"].findings] == ["often_wrong"] and rows["Fine"].findings == []
    assert [finding.kind for finding in rows["Never used and old"].findings] == ["never_used"]
    assert [finding.kind for finding in rows["Empty"].findings] == ["no_trigger_symptoms", "no_steps"]


async def test_the_report_lists_runbooks_with_findings_first(seed_context) -> None:
    graph = await create_application_graph()
    await a_runbook(graph.application_id, "A healthy one")
    await a_runbook(graph.application_id, "Z needs attention", symptoms=None)
    async with open_session() as session:
        report = await RunbookHealthService(session).report(graph.application_id)
    titles = [row.runbook_title for row in report.runbooks]
    assert titles.index("Z needs attention") < titles.index("A healthy one") and report.with_findings_count >= 1 and report.runbook_count == len(titles)


async def test_the_weekly_digest_counts_the_runbooks_with_findings(seed_context) -> None:
    graph = await create_application_graph()
    await a_runbook(graph.application_id, "No symptoms here", symptoms=None)
    async with open_session() as session:
        report = await IntelligenceService(session)._build_report(await session.get(Application, graph.application_id), "weekly_digest", None)
        runbooks = report.report_sections_json["runbooks"]
        assert runbooks["withFindingsCount"] >= 1 and "No symptoms here" in [row["title"] for row in runbooks["runbooks"]] and "## Runbooks" in report.report_markdown

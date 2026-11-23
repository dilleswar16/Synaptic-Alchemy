"""keigan/services/incident_memory_builder.py, incident_memory_retriever.py and incident_memory_retention.py: what is remembered of an investigation, who may be shown it, and when it goes (spec 34)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.alert_entities import Alert, AlertGroup
from keigan.entities.application_entities import MonitoredService
from keigan.entities.incident_entities import Incident, Investigation, InvestigationEvidence, InvestigationHypothesis, InvestigationTimelineEvent, PostmortemReport
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, IncidentMemoryKey, IncidentMemoryRelevanceFeedback
from keigan.entities.status_values import IncidentMemoryCauseSource, IncidentMemoryEntryStatus, IncidentMemoryFixSource
from keigan.services.incident_memory_builder import IncidentMemoryBuilder, load_investigation_facts
from keigan.services.incident_memory_retention import delete_incident_memory
from keigan.services.incident_memory_retriever import CurrentInvestigation, StructuredKeywordRetriever
from keigan.utils.time_utils import utc_now


@dataclass
class World:
    incident_id: str
    investigation_id: str


def unique_error() -> str:
    """A template no other test (or seeded investigation) has, so a match can only be the one made here."""
    return f"quokka{uuid4().hex[:8]} frobnicator failed after 30 ms"


async def a_service_of(application_id: str) -> MonitoredService:
    async with open_session() as session:
        return (await session.scalars(select(MonitoredService).where(MonitoredService.application_id == application_id).limit(1))).one()


async def investigated(
    application_id: str, *, days_ago: int, title: str, template: str | None = None, status: str = "completed", outcome: str | None = "cause_identified", verdict: str | None = None,
    resolution_note: str | None = None, root_cause: str | None = None, why: str | None = "The pool was too small.", resource_identifier: str | None = None, incident_id: str | None = None,
    incident_status: str = "resolved", alert_rule: str | None = None, more_evidence: list[tuple[str, list[dict]]] | None = None,
) -> World:
    service = await a_service_of(application_id)
    opened_at = utc_now() - timedelta(days=days_ago)
    async with open_session() as session:
        if incident_id is None:
            incident = Incident(application_id=application_id, incident_title=title, incident_status=incident_status, opened_at=opened_at, incident_category="database")
            session.add(incident)
            await session.flush()
            incident_id = incident.incident_id
        investigation = Investigation(
            application_id=application_id, incident_id=incident_id, investigation_status=status, investigation_outcome=outcome, why_it_happened_markdown=why, user_feedback_verdict=verdict,
            created_at=opened_at, completed_at=opened_at + timedelta(minutes=5),
        )
        investigation.replace_linked_ids("investigated_service_links", [service.service_id])
        session.add(investigation)
        await session.flush()
        if resource_identifier:
            (await session.get(MonitoredService, service.service_id)).external_resource_identifier = resource_identifier
        if template:
            session.add(InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code="E1", evidence_source_kind="log", evidence_category="errors", evidence_title="errors", signal_strength="high",
                condensed_patterns_json=[{"template": template}],
            ))
        for position, (category, patterns) in enumerate(more_evidence or [], start=2):
            session.add(InvestigationEvidence(
                investigation_id=investigation.investigation_id, evidence_code=f"E{position}", evidence_source_kind="log", evidence_category=category, evidence_title=category, signal_strength="high", condensed_patterns_json=patterns,
            ))
        if alert_rule:
            group = AlertGroup(application_id=application_id, group_title="group", group_status="investigating", investigation_id=investigation.investigation_id)
            session.add(group)
            await session.flush()
            session.add(Alert(application_id=application_id, alert_fingerprint=uuid4().hex, rule_name=alert_rule, alert_group_id=group.alert_group_id))
        if resolution_note:
            session.add(InvestigationTimelineEvent(incident_id=incident_id, event_type="incident_resolved", event_title="Incident resolved", event_details_markdown=resolution_note, event_occurred_at=opened_at))
        if root_cause:
            session.add(PostmortemReport(incident_id=incident_id, investigation_id=investigation.investigation_id, report_title="p", report_status="final", report_sections_json={"root_cause": root_cause}, finalized_at=utc_now()))
        return World(incident_id, investigation.investigation_id)


async def build(investigation_id: str) -> dict[str, str]:
    async with open_session() as session:
        return await IncidentMemoryBuilder(session).refresh_entry(investigation_id)


async def entry_of(investigation_id: str) -> IncidentMemoryEntry | None:
    async with open_session() as session:
        return await session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == investigation_id))


async def keys_of(entry_id: str) -> dict[str, str]:
    async with open_session() as session:
        return {key.key_kind: key.key_display_text for key in (await session.scalars(select(IncidentMemoryKey).where(IncidentMemoryKey.incident_memory_entry_id == entry_id))).all()}


async def similar_to(investigation_id: str, allowed_application_ids: set[str]) -> list[str]:
    """The investigation ids of the past incidents suggested for this one."""
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
        current = CurrentInvestigation(investigation_id, await load_investigation_facts(session, investigation))
        return [found.entry.investigation_id for found in await StructuredKeywordRetriever(session, get_settings()).find(current, allowed_application_ids)]


# ── What is remembered ────────────────────────────────────────────────────────────────────────────


async def test_an_entry_remembers_the_title_the_cause_the_fix_and_the_facts(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    error = unique_error()
    world = await investigated(application_id, days_ago=30, title="Claims API slow, reported by ana@example.com", template=error, resolution_note="Raised the pool size to 200.")
    assert (await build(world.investigation_id))["status"] == "built"
    entry = await entry_of(world.investigation_id)
    assert entry.entry_status == "active" and entry.application_id == application_id and entry.incident_id == world.incident_id
    assert "ana@example.com" not in entry.incident_title_text and "Claims API slow" in entry.incident_title_text
    assert (entry.cause_text, entry.cause_source) == ("The pool was too small.", IncidentMemoryCauseSource.INVESTIGATION)
    assert (entry.fix_text, entry.fix_source) == ("Raised the pool size to 200.", IncidentMemoryFixSource.RESOLUTION_NOTE)
    assert {"claims", "pool", "200"} <= set(entry.search_terms_json) and "ana" not in entry.search_terms_json and entry.service_ids_json  # words of the title, cause and fix; the address is masked first
    assert set(await keys_of(entry.incident_memory_entry_id)) == {"service", "shared_resource", "error_signature", "incident_category"}  # the seeded service sits on a resource of its own


async def test_the_root_cause_of_an_approved_postmortem_is_preferred_to_keigans_analysis(seed_context) -> None:
    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=20, title="Postmortem preferred", root_cause="A deploy removed the retry policy.")
    await build(world.investigation_id)
    entry = await entry_of(world.investigation_id)
    assert (entry.cause_text, entry.cause_source) == ("A deploy removed the retry policy.", IncidentMemoryCauseSource.POSTMORTEM)


async def test_an_investigation_that_found_no_cause_remembers_none(seed_context) -> None:
    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=20, title="Nothing found", outcome="inconclusive")
    await build(world.investigation_id)
    entry = await entry_of(world.investigation_id)
    assert entry.cause_text is None and entry.cause_source == IncidentMemoryCauseSource.NONE


async def test_the_texts_are_cut_to_the_setting(seed_context) -> None:
    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=20, title="Long cause", why="word " * 500)
    await build(world.investigation_id)
    assert len((await entry_of(world.investigation_id)).cause_text) <= get_settings().incident_memory_text_maximum_characters


async def test_an_investigation_that_is_not_complete_or_does_not_exist_has_no_entry(seed_context) -> None:
    running = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Still running", status="running")
    assert (await build(running.investigation_id))["status"] == "skipped" and await entry_of(running.investigation_id) is None
    evidence_only = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=1, title="Evidence only", status="completed_evidence_only")
    assert (await build(evidence_only.investigation_id))["status"] == "skipped"
    assert (await build("no-such-investigation"))["status"] == "missing"


async def test_building_again_replaces_the_entry_and_its_keys_in_place(seed_context) -> None:
    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=10, title="Rebuilt", template=unique_error())
    await build(world.investigation_id)
    first = await entry_of(world.investigation_id)
    async with open_session() as session:
        (await session.get(Investigation, world.investigation_id)).why_it_happened_markdown = "A different cause."
        await session.execute(InvestigationEvidence.__table__.delete().where(InvestigationEvidence.investigation_id == world.investigation_id))
    await build(world.investigation_id)
    second = await entry_of(world.investigation_id)
    assert second.incident_memory_entry_id == first.incident_memory_entry_id and second.cause_text == "A different cause."
    assert "error_signature" not in await keys_of(second.incident_memory_entry_id)
    async with open_session() as session:
        assert await session.scalar(select(func.count()).select_from(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == world.investigation_id)) == 1


async def test_one_live_entry_per_incident_the_latest_with_a_verdict_and_a_hidden_one_stays_hidden(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    first = await investigated(application_id, days_ago=9, title="Investigated twice", verdict="correct")
    second = await investigated(application_id, days_ago=8, title="Investigated twice", incident_id=first.incident_id)  # newer, but nobody judged it
    await build(first.investigation_id)
    await build(second.investigation_id)
    assert (await entry_of(first.investigation_id)).entry_status == IncidentMemoryEntryStatus.ACTIVE
    assert (await entry_of(second.investigation_id)).entry_status == IncidentMemoryEntryStatus.SUPERSEDED
    async with open_session() as session:
        (await session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == first.investigation_id))).entry_status = IncidentMemoryEntryStatus.HIDDEN
    await build(first.investigation_id)
    assert (await entry_of(first.investigation_id)).entry_status == IncidentMemoryEntryStatus.HIDDEN


# ── Who is shown what ─────────────────────────────────────────────────────────────────────────────


async def test_a_later_incident_with_the_same_error_is_shown_the_earlier_one_and_why(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    error = unique_error()
    earlier = await investigated(application_id, days_ago=40, title="Earlier timeout", template=error, verdict="correct")
    later = await investigated(application_id, days_ago=1, title="Later timeout", template=error)
    await build(earlier.investigation_id)
    assert earlier.investigation_id in await similar_to(later.investigation_id, {application_id})
    assert earlier.investigation_id not in await similar_to(earlier.investigation_id, {application_id})  # never itself


async def test_an_incident_is_never_shown_one_that_happened_after_it(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    error = unique_error()
    current = await investigated(application_id, days_ago=30, title="Earlier one", template=error)
    after = await investigated(application_id, days_ago=2, title="Later one", template=error)
    await build(after.investigation_id)
    assert after.investigation_id not in await similar_to(current.investigation_id, {application_id})


async def test_a_hidden_or_superseded_entry_is_not_shown(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    error = unique_error()
    earlier = await investigated(application_id, days_ago=40, title="Hidden timeout", template=error)
    later = await investigated(application_id, days_ago=1, title="Current timeout", template=error)
    await build(earlier.investigation_id)
    async with open_session() as session:
        (await session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == earlier.investigation_id))).entry_status = IncidentMemoryEntryStatus.HIDDEN
    assert earlier.investigation_id not in await similar_to(later.investigation_id, {application_id})


async def test_another_application_is_shown_only_when_it_shares_a_hard_fact_and_only_if_the_reader_may_read_it(seed_context) -> None:
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    error = unique_error()
    elsewhere = await investigated(payments, days_ago=40, title="Same error in payments", template=error)
    here = await investigated(claims, days_ago=1, title="Same error in claims", template=error)
    await build(elsewhere.investigation_id)
    assert elsewhere.investigation_id in await similar_to(here.investigation_id, {claims, payments})
    assert elsewhere.investigation_id not in await similar_to(here.investigation_id, {claims})  # the reader cannot read payments: it is as if it did not exist


async def test_wording_alone_never_matches_another_application(seed_context) -> None:
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    word = f"zebra{uuid4().hex[:8]}"
    elsewhere = await investigated(payments, days_ago=40, title=f"{word} outage in payments", why=f"{word} {word} trouble")
    here = await investigated(claims, days_ago=1, title=f"{word} outage in claims")
    await build(elsewhere.investigation_id)
    assert elsewhere.investigation_id not in await similar_to(here.investigation_id, {claims, payments})


async def test_an_entry_whose_services_are_all_gone_is_marked_out_of_date(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    error = unique_error()
    earlier = await investigated(application_id, days_ago=40, title="Service later removed", template=error)
    later = await investigated(application_id, days_ago=1, title="Current", template=error)
    await build(earlier.investigation_id)
    async with open_session() as session:
        (await session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == earlier.investigation_id))).service_ids_json = ["service-that-was-deleted"]
        investigation = await session.get(Investigation, later.investigation_id)
        current = CurrentInvestigation(later.investigation_id, await load_investigation_facts(session, investigation))
        [found] = [item for item in await StructuredKeywordRetriever(session, get_settings()).find(current, {application_id}) if item.entry.investigation_id == earlier.investigation_id]
    assert found.match.is_stale and "service_removed" in found.match.stale_reasons


# ── When it goes ──────────────────────────────────────────────────────────────────────────────────


async def test_deleting_the_memory_of_an_investigation_removes_its_keys_and_every_answer_about_it(seed_context) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]
    past = await investigated(application_id, days_ago=40, title="To be forgotten", template=unique_error())
    other = await investigated(application_id, days_ago=1, title="Asked about it")
    await build(past.investigation_id)
    entry = await entry_of(past.investigation_id)
    async with open_session() as session:
        session.add(IncidentMemoryRelevanceFeedback(investigation_id=other.investigation_id, incident_memory_entry_id=entry.incident_memory_entry_id, user_principal_name="a@example.com", relevance_verdict="relevant"))
    async with open_session() as session:
        assert await delete_incident_memory(session, [past.investigation_id]) == 1
    assert await entry_of(past.investigation_id) is None and await keys_of(entry.incident_memory_entry_id) == {}
    async with open_session() as session:
        assert await session.scalar(select(func.count()).select_from(IncidentMemoryRelevanceFeedback).where(IncidentMemoryRelevanceFeedback.incident_memory_entry_id == entry.incident_memory_entry_id)) == 0


async def test_the_leading_hypotheses_fix_is_the_last_place_the_fix_text_comes_from(seed_context) -> None:
    """The leading hypothesis's fix summary is the last place the fix text can come from."""
    application_id = seed_context.application_ids_by_code["CLMJP"]
    world = await investigated(application_id, days_ago=3, title="Hypothesis fix only")
    async with open_session() as session:
        session.add(InvestigationHypothesis(investigation_id=world.investigation_id, analysis_perspective="application", hypothesis_title="h", is_leading_hypothesis=True, proposed_fix_json={"summary": "Restart the pool."}))
    await build(world.investigation_id)
    entry = await entry_of(world.investigation_id)
    assert (entry.fix_text, entry.fix_source) == ("Restart the pool.", IncidentMemoryFixSource.HYPOTHESIS_FIX)


async def test_the_rebuild_script_builds_what_is_missing_and_can_run_again(seed_context) -> None:
    from support import scripts_path  # noqa: F401  (puts backend/scripts on sys.path)

    import rebuild_incident_memory

    world = await investigated(seed_context.application_ids_by_code["CLMJP"], days_ago=15, title="Completed before the memory existed")
    assert await entry_of(world.investigation_id) is None
    first = await rebuild_incident_memory.rebuild()
    entry = await entry_of(world.investigation_id)
    assert entry is not None and first["built"] >= 1
    await rebuild_incident_memory.rebuild()
    assert (await entry_of(world.investigation_id)).incident_memory_entry_id == entry.incident_memory_entry_id  # replaced in place, not duplicated


# ── Alert rules, changes and failed dependencies ──────────────────────────────────────────────────

CHANGE = [{"template": "Deployed the web app", "operationName": "Microsoft.Web/sites/config/write", "changeKind": "configuration"}]
DEPENDENCY = [{"template": "Call to dependency partner-api.example.com:443 (HTTP) failed with 503"}]


async def test_the_alert_rule_the_change_and_the_failed_dependency_become_keys_and_a_change_is_not_an_error(seed_context) -> None:
    rule = f"Rule {uuid4().hex[:8]}"
    world = await investigated(
        seed_context.application_ids_by_code["CLMJP"], days_ago=12, title="Rich facts", template=unique_error(), alert_rule=rule, more_evidence=[("change_event", CHANGE), ("dependency_failures", DEPENDENCY)],
    )
    await build(world.investigation_id)
    keys = await keys_of((await entry_of(world.investigation_id)).incident_memory_entry_id)
    assert keys["alert_rule"] == rule and keys["change_operation"] == "microsoft.web/sites/config/write" and keys["dependency_target"] == "partner-api.example.com"
    assert keys["error_signature"] != "deployed the web app"  # the change's text is a change, not an error signature


async def test_another_application_with_the_same_alert_rule_and_failing_dependency_is_shown_though_its_wording_differs(seed_context) -> None:
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    rule = f"Rule {uuid4().hex[:8]}"
    elsewhere = await investigated(payments, days_ago=40, title="Totally different words", verdict="correct", alert_rule=rule, more_evidence=[("dependency_failures", DEPENDENCY)])
    both = await investigated(claims, days_ago=1, title="Another title", alert_rule=rule, more_evidence=[("dependency_failures", DEPENDENCY)])
    await build(elsewhere.investigation_id)
    assert elsewhere.investigation_id in await similar_to(both.investigation_id, {claims, payments})  # 0.25 + 0.15, confirmed


async def test_a_shared_change_alone_is_not_enough_for_another_application(seed_context) -> None:
    """A change operation is a weak fact (the same kind of deployment happens everywhere): it never opens another application's history."""
    claims, payments = seed_context.application_ids_by_code["CLMJP"], seed_context.application_ids_by_code["PAYAU"]
    change = [{"template": "x", "operationName": f"Microsoft.Web/{uuid4().hex[:8]}/write"}]
    elsewhere = await investigated(payments, days_ago=40, title="Unrelated words one", more_evidence=[("change_event", change)])
    here = await investigated(claims, days_ago=1, title="Unrelated words two", more_evidence=[("change_event", change)])
    await build(elsewhere.investigation_id)
    assert elsewhere.investigation_id not in await similar_to(here.investigation_id, {claims, payments})

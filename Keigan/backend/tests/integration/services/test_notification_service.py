"""keigan/services/notification_service.py: what automatic emails may contain (V3 audience rule, V8)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Incident, Investigation
from keigan.entities.notification_entities import NotificationDelivery, Stakeholder
from keigan.services.notification_service import NotificationService

FIX_WITH_COMMAND = "Restart the pool.\n\n```bash\nkubectl -n prod delete pod claims-api-0\n```"


async def prepare(application_id: str) -> tuple[str, str, str, str]:
    marker = uuid.uuid4().hex[:8]
    executive_address, engineer_address = f"exec-{marker}@example.test", f"sre-{marker}@example.test"
    async with open_session() as session:
        incident = Incident(application_id=application_id, incident_title=f"Claims slow {marker}", keigan_priority="P1", incident_status="investigating")
        session.add(incident)
        await session.flush()
        session.add(Investigation(
            application_id=application_id, incident_id=incident.incident_id, investigation_trigger="incident", investigation_status="completed", current_stage_name="completed", progress_percent=100,
            executive_summary="Claims are slow.", what_went_wrong_markdown="Slow [details](https://evil.example/login) ![p](https://evil.example/p.png).", why_it_happened_markdown="Pool exhausted.",
            how_to_fix_markdown=FIX_WITH_COMMAND, overall_confidence_score=0.7,
        ))
        for address, role in ((executive_address, "executive"), (engineer_address, "sre")):
            session.add(Stakeholder(
                application_id=application_id, display_name=role, email_address=address, stakeholder_role=role, notification_channels_json=["email"], minimum_priority="P4",
                subscribed_notification_types_json=["preliminary_report"], preferred_language_code="en",
            ))
        await session.flush()
        investigation_id = await session.scalar(select(Investigation.investigation_id).where(Investigation.incident_id == incident.incident_id))
        return incident.incident_id, investigation_id, executive_address, engineer_address


async def delivered_text(address: str) -> str:
    async with open_session() as session:
        row = await session.scalar(select(NotificationDelivery).where(NotificationDelivery.recipient_address == address))
        return f"{row.body_text}\n{row.body_html}" if row else ""


async def test_business_stakeholders_get_no_fix_commands_but_engineers_do(seed_context) -> None:
    _, investigation_id, executive_address, engineer_address = await prepare(seed_context.application_ids_by_code["CHAD"])
    async with open_session() as session:
        await NotificationService(session).on_investigation_completed(investigation_id)
    executive_email, engineer_email = await delivered_text(executive_address), await delivered_text(engineer_address)
    assert "Claims are slow." in executive_email
    assert "kubectl" not in executive_email and "Suggested fix" not in executive_email
    assert "kubectl -n prod delete pod claims-api-0" in engineer_email


async def test_no_outgoing_email_contains_a_link_or_image_to_a_host_that_is_not_allowed(seed_context) -> None:
    _, investigation_id, executive_address, engineer_address = await prepare(seed_context.application_ids_by_code["CHAD"])
    async with open_session() as session:
        await NotificationService(session).on_investigation_completed(investigation_id)
    for address in (executive_address, engineer_address):
        email = await delivered_text(address)
        assert "https://evil.example/login)" not in email and "href=\"https://evil.example" not in email
        assert "p.png" not in email


# ── What the preliminary report says when the cause is not confirmed (spec 27, AC-16) ────────────

import pytest

from keigan.entities.status_values import InvestigationOutcome

WHAT_WENT_WRONG, WHY, FIX = "Claims are slow since 10:00.", "A pool ran out of connections.", "Restart the pool."


def investigation_with(outcome: str | None, *, gap_count: int = 0) -> Investigation:
    return Investigation(
        application_id="app", investigation_trigger="incident", investigation_status="completed", current_stage_name="completed", investigation_outcome=outcome,
        executive_summary="Claims are slow.", what_went_wrong_markdown=WHAT_WENT_WRONG, why_it_happened_markdown=WHY, how_to_fix_markdown=FIX, overall_confidence_score=0.7,
    )


@pytest.mark.parametrize("language", [None, "ja"])
def test_a_cause_is_only_stated_when_it_was_identified(language: str | None) -> None:
    body = NotificationService.investigation_email_body(investigation_with(InvestigationOutcome.CAUSE_IDENTIFIED), include_fix=True, language_code=language)
    assert WHY in body and FIX in body
    assert (("Likely cause" in body) if language is None else ("考えられる原因" in body))


@pytest.mark.parametrize("outcome", [InvestigationOutcome.INCONCLUSIVE, InvestigationOutcome.CAUSE_NOT_VISIBLE])
def test_without_a_confirmed_cause_the_email_states_no_cause_and_no_fix_but_says_what_is_known(outcome: str) -> None:
    body = NotificationService.investigation_email_body(investigation_with(outcome), include_fix=True)
    assert "Likely cause" not in body and "Suggested fix" not in body
    assert WHAT_WENT_WRONG in body and "What is known so far" in body and "Suggested next checks" in body
    assert "not confirmed" in body or "could not see the cause" in body


def test_business_roles_never_get_next_checks_or_fix_steps_and_the_outcome_still_comes_first() -> None:
    body = NotificationService.investigation_email_body(investigation_with(InvestigationOutcome.CAUSE_NOT_VISIBLE), include_fix=False)
    assert FIX not in body and "Suggested next checks" not in body
    assert body.startswith("Keigan could not see the cause in the monitoring data it can read.")


def test_the_japanese_outcome_sentence_is_used_for_a_japanese_reader() -> None:
    body = NotificationService.investigation_email_body(investigation_with(InvestigationOutcome.CAUSE_NOT_VISIBLE), include_fix=False, language_code="ja")
    assert "監視データ" in body and "Likely cause" not in body and "Suggested" not in body


def test_an_investigation_with_no_recorded_outcome_keeps_the_earlier_wording() -> None:
    body = NotificationService.investigation_email_body(investigation_with(None), include_fix=True)
    assert "Likely cause" in body and FIX in body


def test_the_outcome_replaces_the_confidence_fact_unless_a_cause_was_identified() -> None:
    assert NotificationService.confidence_or_outcome_fact(investigation_with(InvestigationOutcome.CAUSE_IDENTIFIED), None) == ("Confidence", "70%")
    label, value = NotificationService.confidence_or_outcome_fact(investigation_with(InvestigationOutcome.INCONCLUSIVE), None)
    assert (label, value) == ("Outcome", "Inconclusive")
    assert NotificationService.confidence_or_outcome_fact(investigation_with(InvestigationOutcome.CAUSE_NOT_VISIBLE), "ja")[0] == "結果"

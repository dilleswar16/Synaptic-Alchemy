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
            application_id=application_id, incident_id=incident.incident_id, investigation_trigger="servicenow", investigation_status="completed", current_stage_name="completed", progress_percent=100,
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

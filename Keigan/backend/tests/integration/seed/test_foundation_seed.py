"""keigan/seed/foundation_seed.py: the demo applications comply with the telemetry access rules (V2), so the simulated demo keeps working."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.entities.application_entities import ApplicationComponent, LogToolConnection, MonitoredService, ServiceLogSource
from keigan.integrations.telemetry_gateway import TelemetryTarget

pytestmark = pytest.mark.usefixtures("seed_context")


async def test_every_seeded_log_source_and_metric_is_allowed_by_the_access_policy() -> None:
    policy = application_context.telemetry_access_policy()
    checked_source_count = 0
    async with open_session() as session:
        services = (await session.scalars(select(MonitoredService).where(MonitoredService.created_by_user_principal_name == "system:seed"))).all()
        for service in services:
            component = await session.get(ApplicationComponent, service.component_id)
            for log_source in (await session.scalars(select(ServiceLogSource).where(ServiceLogSource.service_id == service.service_id))).all():
                connection = await session.get(LogToolConnection, log_source.log_tool_connection_id) if log_source.log_tool_connection_id else None
                target = TelemetryTarget.from_entities(service, log_source, component, connection)
                await policy.ensure_can_read_source(target, session)
                checked_source_count += 1
            await policy.ensure_can_read_metrics(TelemetryTarget.from_entities(service, None, component), session)
            if component.azure_subscription_id:
                await policy.ensure_can_read_activity(service.application_id, component.azure_subscription_id, component.azure_resource_group_name, session)
    assert checked_source_count > 30


async def test_the_flagship_and_one_other_demo_application_have_plain_operating_notes_within_the_limit() -> None:
    from keigan.ai.prompt_safety import assess_prompt_injection
    from keigan.config.settings import get_settings
    from keigan.entities.application_entities import Application
    from keigan.utils.pii_masker import PiiMasker

    async with open_session() as session:
        notes_by_code = {application.application_code: application.operating_notes_text for application in (await session.scalars(select(Application))).all()}
    for application_code in ("CLMJP", "CHAD"):
        notes = notes_by_code[application_code]
        assert notes and notes == notes.strip(), application_code
        assert len(notes) <= get_settings().application_operating_notes_maximum_characters
        assert not assess_prompt_injection(notes).is_suspicious
        assert PiiMasker().mask_text(notes) == notes, "demo notes must hold no personal data"
        assert notes.isascii(), "demo notes are plain English"

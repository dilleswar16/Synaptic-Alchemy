"""keigan/services/intelligence_service.py: AI narratives and reports are sanitised before storage and sending (V8)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from keigan.ai.llm_gateway import LlmGateway
from keigan.ai.notification_ai_schemas import IntelligenceNarrativeResult, IntelligenceReportResult
from keigan.config.database_config import open_session
from keigan.entities.application_entities import Application
from keigan.services.intelligence_service import IntelligenceService

HOSTILE = "Open [the console](https://evil.example/c) ![p](https://evil.example/p.png) now"


async def application_of(seed_context: Any) -> Application:
    async with open_session() as session:
        return await session.get(Application, seed_context.application_ids_by_code["CLMJP"])


async def test_a_signal_narrative_has_no_links_or_images(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(self: LlmGateway, **kwargs: Any) -> IntelligenceNarrativeResult:
        return IntelligenceNarrativeResult(narrative_markdown=HOSTILE)

    monkeypatch.setattr(LlmGateway, "generate_structured", fake)
    application = await application_of(seed_context)
    async with open_session() as session:
        narrative = await IntelligenceService(session)._narrate(application, SimpleNamespace(facts_text="CPU 91 percent"))
    assert "](https://evil.example" not in narrative and "![" not in narrative


async def test_a_report_summary_and_recommendations_have_no_links_or_images(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(self: LlmGateway, **kwargs: Any) -> IntelligenceReportResult:
        return IntelligenceReportResult(executive_summary=HOSTILE, recommendations=[HOSTILE, "Check <https://evil.example/r>"])

    monkeypatch.setattr(LlmGateway, "generate_structured", fake)
    application = await application_of(seed_context)
    async with open_session() as session:
        summary, recommendations = await IntelligenceService(session)._narrate_report(application, "weekly_digest", "- Health score 90")
    assert "](https://evil.example" not in summary and "![" not in summary
    assert not any("evil.example" in item and "`" not in item for item in recommendations)


class TestNarrativeFallbacksAreLoggedNotHidden:
    async def test_a_failed_signal_narrative_uses_the_numbers_and_logs_a_warning_that_names_the_application(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from types import SimpleNamespace

        from keigan.config import application_context
        from keigan.services.intelligence_service import IntelligenceService

        class RefusingGateway:
            async def generate_structured(self, **arguments: object) -> None:
                raise RuntimeError("model quota exhausted")

        monkeypatch.setattr(application_context, "llm_gateway", lambda: RefusingGateway())
        application = SimpleNamespace(application_id="application-7", application_name="Claims")
        detection = SimpleNamespace(facts_text="- error ratio rose to 4%")
        text = await IntelligenceService._narrate(SimpleNamespace(), application, detection)  # type: ignore[arg-type]
        assert text == detection.facts_text
        assert any(record.levelno == logging.WARNING and "application-7" in record.getMessage() for record in caplog.records)

    async def test_a_failed_report_summary_uses_the_facts_and_logs_a_warning_that_names_the_application(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        from types import SimpleNamespace

        from keigan.config import application_context
        from keigan.services.intelligence_service import IntelligenceService

        class RefusingGateway:
            async def generate_structured(self, **arguments: object) -> None:
                raise RuntimeError("model quota exhausted")

        monkeypatch.setattr(application_context, "llm_gateway", lambda: RefusingGateway())
        application = SimpleNamespace(application_id="application-8", application_name="Payments")
        summary, recommendations = await IntelligenceService._narrate_report(SimpleNamespace(), application, "weekly_digest", "- Health 80")  # type: ignore[arg-type]
        assert summary == "Health 80" and recommendations
        assert any(record.levelno == logging.WARNING and "application-8" in record.getMessage() for record in caplog.records)

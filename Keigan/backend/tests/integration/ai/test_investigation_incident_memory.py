"""keigan/ai/investigation_graph.py: confirmed past incidents of the same application reach the hypotheses as a hint (spec 34, 4.5 and 4.6).

The first run is the "past" incident: it is rated, remembered, and the second run (the same simulated incident, a moment later) is the one that receives it.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from keigan.ai.incident_memory_prompt import NONE_RECORDED, SIMILAR_INCIDENTS_TITLE
from keigan.ai.investigation_ai_caller import InvestigationAiCaller
from keigan.ai.llm_gateway import PromptSection
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Investigation
from keigan.entities.incident_memory_entities import IncidentMemoryEntry, InvestigationMemoryReference
from keigan.services.incident_memory_builder import IncidentMemoryBuilder
from keigan.services.investigation_service import InvestigationService

HYPOTHESES = ("hypothesis_application", "hypothesis_dependencies", "hypothesis_infrastructure")


@pytest.fixture
def prompt_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[PromptSection]]]:
    calls: list[tuple[str, list[PromptSection]]] = []
    original_ask = InvestigationAiCaller.ask

    async def recording_ask(self: InvestigationAiCaller, feature_name: str, prompt_sections: list[PromptSection], output_schema: type, **template_variables: Any) -> Any:
        calls.append((feature_name, list(prompt_sections)))
        return await original_ask(self, feature_name, prompt_sections, output_schema, **template_variables)

    monkeypatch.setattr(InvestigationAiCaller, "ask", recording_ask)
    return calls


async def run_investigation(seed_context) -> str:  # noqa: ANN001
    async with open_session() as session:
        investigation_id = await InvestigationService(session).start_investigation(seed_context.application_ids_by_code["CLMJP"], "manual", description="Claim submissions are timing out for customers in Japan since 10:00.")
    async with open_session() as session:
        await InvestigationService(session).run_investigation(investigation_id)
    return investigation_id


async def remember(investigation_id: str, verdict: str | None) -> IncidentMemoryEntry:
    async with open_session() as session:
        (await session.get(Investigation, investigation_id)).user_feedback_verdict = verdict
    async with open_session() as session:
        await IncidentMemoryBuilder(session).refresh_entry(investigation_id)
    async with open_session() as session:
        return await session.scalar(select(IncidentMemoryEntry).where(IncidentMemoryEntry.investigation_id == investigation_id))


def memory_sections(calls: list[tuple[str, list[PromptSection]]], investigation_calls_from: int) -> dict[str, PromptSection]:
    return {name: section for name, sections in calls[investigation_calls_from:] if name in HYPOTHESES for section in sections if section.title == SIMILAR_INCIDENTS_TITLE}


async def references_of(investigation_id: str) -> list[str]:
    async with open_session() as session:
        rows = (await session.scalars(select(InvestigationMemoryReference).where(InvestigationMemoryReference.investigation_id == investigation_id).order_by(InvestigationMemoryReference.position))).all()
        return [row.incident_memory_entry_id for row in rows]


async def test_a_confirmed_past_incident_reaches_all_three_hypotheses_and_is_recorded_as_given(seed_context, prompt_calls) -> None:
    past_id = await run_investigation(seed_context)
    entry = await remember(past_id, "correct")
    started = len(prompt_calls)
    current_id = await run_investigation(seed_context)
    sections = memory_sections(prompt_calls, started)
    assert set(sections) == set(HYPOTHESES)
    for section in sections.values():
        assert section.is_untrusted is True and "confirmed by an application admin" in section.content and "matched on:" in section.content and "[" not in section.content
    assert entry.incident_memory_entry_id in await references_of(current_id)


async def test_an_unreviewed_or_incorrect_past_incident_is_not_given_to_the_ai(seed_context, prompt_calls) -> None:
    for verdict in (None, "incorrect", "partially_correct"):
        past_id = await run_investigation(seed_context)
        entry = await remember(past_id, verdict)
        started = len(prompt_calls)
        current_id = await run_investigation(seed_context)
        assert entry.incident_memory_entry_id not in await references_of(current_id), verdict
        assert all(section.content == NONE_RECORDED or "confirmed by an application admin" in section.content for section in memory_sections(prompt_calls, started).values())


async def test_nothing_is_given_when_the_setting_is_zero(seed_context, prompt_calls, monkeypatch: pytest.MonkeyPatch) -> None:
    await remember(await run_investigation(seed_context), "correct")
    monkeypatch.setattr(get_settings(), "incident_memory_maximum_in_prompt", 0)
    started = len(prompt_calls)
    current_id = await run_investigation(seed_context)
    assert await references_of(current_id) == [] and all(section.content == NONE_RECORDED for section in memory_sections(prompt_calls, started).values())


async def test_the_most_given_is_the_setting(seed_context, prompt_calls, monkeypatch: pytest.MonkeyPatch) -> None:
    for _ in range(3):
        await remember(await run_investigation(seed_context), "correct")
    monkeypatch.setattr(get_settings(), "incident_memory_maximum_in_prompt", 2)
    assert len(await references_of(await run_investigation(seed_context))) == 2

"""The investigation engine under spec 27, through the real graph and the offline model: an investigation on a window with no scenario ends "cause not visible" with no lead,
every hypothesis has a state, what Keigan could not check is stored and told to the model (AC-5, AC-10, AC-12, AC-14)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from keigan.ai.investigation_ai_caller import InvestigationAiCaller
from keigan.ai.llm_gateway import PromptSection
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Investigation, InvestigationCoverageGap, InvestigationEvidence, InvestigationHypothesis
from keigan.entities.status_values import CoverageGapKind, EvidenceCheckOutcome, HypothesisState, InvestigationOutcome, InvestigationStatus
from keigan.services.investigation_service import InvestigationService

PROBLEM = "Claim submissions are timing out for customers in Japan and the claims screen shows errors."


@pytest.fixture
def prompt_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[PromptSection]]]:
    calls: list[tuple[str, list[PromptSection]]] = []
    original_ask = InvestigationAiCaller.ask

    async def recording_ask(self: InvestigationAiCaller, feature_name: str, prompt_sections: list[PromptSection], output_schema: type, **template_variables: Any) -> Any:
        calls.append((feature_name, list(prompt_sections)))
        return await original_ask(self, feature_name, prompt_sections, output_schema, **template_variables)

    monkeypatch.setattr(InvestigationAiCaller, "ask", recording_ask)
    return calls


async def run_manual_investigation(seed_context) -> str:  # noqa: ANN001
    async with open_session() as session:
        investigation_id = await InvestigationService(session).start_investigation(seed_context.application_ids_by_code["CLMJP"], "manual", description=PROBLEM)
    async with open_session() as session:
        await InvestigationService(session).run_investigation(investigation_id)
    return investigation_id


async def stored(model: type, investigation_id: str) -> list[Any]:
    async with open_session() as session:
        return list((await session.scalars(select(model).where(model.investigation_id == investigation_id))).all())


async def test_a_window_with_no_scenario_ends_cause_not_visible_with_no_lead_and_every_hypothesis_has_a_state(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
    assert investigation.investigation_status == InvestigationStatus.COMPLETED
    assert (investigation.investigation_outcome, investigation.proposed_investigation_outcome) == (InvestigationOutcome.CAUSE_NOT_VISIBLE, InvestigationOutcome.CAUSE_NOT_VISIBLE)
    assert investigation.outcome_guard_code is None and investigation.leading_hypothesis_id is None
    assert investigation.outcome_reason_markdown and investigation.leading_perspective_reason_markdown
    hypotheses = await stored(InvestigationHypothesis, investigation_id)
    assert len(hypotheses) == 3 and not any(hypothesis.is_leading_hypothesis for hypothesis in hypotheses)
    assert all(hypothesis.hypothesis_state == HypothesisState.INCONCLUSIVE and hypothesis.state_reason_markdown for hypothesis in hypotheses)


async def test_every_evidence_row_says_what_its_check_found_and_no_unread_source_became_evidence(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    rows = await stored(InvestigationEvidence, investigation_id)
    assert rows
    assert {row.check_outcome for row in rows} <= {EvidenceCheckOutcome.SIGNAL, EvidenceCheckOutcome.NO_SIGNAL}
    assert all(row.baseline_comparison is not None for row in rows)


async def test_checks_cut_by_the_limit_are_stored_as_gaps_and_the_model_is_told(seed_context, monkeypatch: pytest.MonkeyPatch, prompt_calls) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "investigation_max_checks_per_service", 1)
    investigation_id = await run_manual_investigation(seed_context)
    gaps = await stored(InvestigationCoverageGap, investigation_id)
    cut = [gap for gap in gaps if gap.gap_kind == CoverageGapKind.CHECKS_BEYOND_LIMIT]
    assert cut and all(gap.service_name and gap.parameters_json["limit"] == 1 for gap in cut)
    assert [gap.display_order for gap in gaps] == sorted(gap.display_order for gap in gaps)
    hypothesis_calls = [sections for name, sections in prompt_calls if name.startswith("hypothesis_")]
    assert hypothesis_calls
    for sections in hypothesis_calls:
        section = next(section for section in sections if section.title == "What Keigan could not check")
        assert section.is_untrusted is False and "were not run because of the limit of 1 checks per service" in section.content


async def test_the_model_is_told_the_two_confidence_bands_from_the_settings(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(get_settings(), "investigation_supported_minimum_confidence", 0.65)
    monkeypatch.setattr(get_settings(), "investigation_ruled_out_maximum_confidence", 0.15)
    seen: list[dict[str, Any]] = []
    original_ask = InvestigationAiCaller.ask

    async def recording_ask(self: InvestigationAiCaller, feature_name: str, prompt_sections: list[PromptSection], output_schema: type, **template_variables: Any) -> Any:
        if feature_name.startswith("hypothesis_"):
            seen.append(template_variables)
        return await original_ask(self, feature_name, prompt_sections, output_schema, **template_variables)

    monkeypatch.setattr(InvestigationAiCaller, "ask", recording_ask)
    await run_manual_investigation(seed_context)
    assert seen and all(variables == {"supported_minimum_confidence": 0.65, "ruled_out_maximum_confidence": 0.15, "maximum_fix_steps": get_settings().suggested_fix_maximum_steps} for variables in seen)

"""keigan/services/intelligence_detectors.py: the wording of an exhausted error budget, and the offline narrative."""

from __future__ import annotations

from keigan.services.intelligence_detectors import forecast_sentence


def test_a_budget_that_is_already_used_up_says_so_instead_of_forecasting_zero_days() -> None:
    assert forecast_sentence(minutes_until_exhaustion=0.0) == "the error budget is already exhausted."


def test_a_budget_that_is_burning_is_forecast_in_days() -> None:
    assert forecast_sentence(minutes_until_exhaustion=3600.0) == "forecast exhaustion in 2.5 days."


def test_the_offline_narrative_is_the_facts_and_adds_no_recommendation_of_its_own() -> None:
    from keigan.ai.notification_ai_schemas import IntelligenceNarrativeResult, _mock_narrative
    from keigan.ai.llm_gateway import PromptSection

    narrative = _mock_narrative(IntelligenceNarrativeResult, [PromptSection("Signal facts", "SLO claims-api target 99.9%.")])
    assert narrative.narrative_markdown == "SLO claims-api target 99.9%."

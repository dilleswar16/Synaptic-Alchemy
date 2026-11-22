"""keigan/services/investigation_trace_adjustments.py: what Keigan changed in a model's answer, as codes (spec 28, AC-12)."""

from __future__ import annotations

from keigan.ai.investigation_outcome_rules import OutcomeDecision, StateDecision
from keigan.entities.status_values import HypothesisState, HypothesisStateGuard, InvestigationOutcome, InvestigationOutcomeGuard
from keigan.services.investigation_trace_adjustments import hypothesis_adjustments, removed_citation_codes, synthesis_adjustments

UNCHANGED = StateDecision(HypothesisState.SUPPORTED, HypothesisState.SUPPORTED, None, ("E1",))
GUARDED = StateDecision(HypothesisState.INCONCLUSIVE, HypothesisState.SUPPORTED, HypothesisStateGuard.SUPPORT_NOT_IN_EVIDENCE, ())


def test_only_codes_that_do_not_exist_are_reported_as_removed() -> None:
    assert removed_citation_codes(["See [E1] and [E14].", None, "Also [K9] [R1]"], {"E1", "R1"}) == ["E14", "K9"]


def test_an_answer_the_checks_left_alone_has_no_adjustments() -> None:
    assert hypothesis_adjustments(
        raw_texts=["Cites [E1]"], valid_codes={"E1"}, dropped_evidence_codes=[], replaced_file_path_count=0, risk_from="medium", risk_to="medium", state_decision=UNCHANGED,
    ) == []


def test_every_kind_of_change_is_reported_with_its_code_and_small_parameters() -> None:
    adjustments = hypothesis_adjustments(
        raw_texts=["Cites [E14]"], valid_codes={"E1"}, dropped_evidence_codes=["E14", "E14", "E9"], replaced_file_path_count=2, risk_from="medium", risk_to="high", state_decision=GUARDED,
    )
    assert [item["code"] for item in adjustments] == ["invalid_citations_removed", "evidence_codes_dropped", "file_path_replaced", "command_risk_raised", "hypothesis_state_guarded"]
    by_code = {item["code"]: item["parameters"] for item in adjustments}
    assert by_code["invalid_citations_removed"] == {"codes": ["E14"]} and by_code["evidence_codes_dropped"] == {"codes": ["E14", "E9"]}
    assert by_code["file_path_replaced"] == {"count": 2} and by_code["command_risk_raised"] == {"from": "medium", "to": "high"}
    assert by_code["hypothesis_state_guarded"] == {"proposed": "supported", "final": "inconclusive", "guard": "support_not_in_evidence"}


def test_the_synthesis_reports_the_confidence_cap_and_the_outcome_guard() -> None:
    outcome = OutcomeDecision(InvestigationOutcome.CAUSE_NOT_VISIBLE, InvestigationOutcome.CAUSE_IDENTIFIED, InvestigationOutcomeGuard.NOTHING_CHANGED_IN_CHECKED_SOURCES, ())
    adjustments = synthesis_adjustments(raw_texts=["[E5]"], valid_codes={"E1"}, confidence_from=0.9, confidence_to=0.55, outcome_decision=outcome)
    assert [item["code"] for item in adjustments] == ["invalid_citations_removed", "confidence_capped", "outcome_guarded"]
    assert adjustments[1]["parameters"] == {"from": 0.9, "to": 0.55}
    assert adjustments[2]["parameters"] == {"proposed": "cause_identified", "final": "cause_not_visible", "guard": "nothing_changed_in_checked_sources"}


def test_a_synthesis_nothing_changed_has_no_adjustments() -> None:
    outcome = OutcomeDecision(InvestigationOutcome.CAUSE_IDENTIFIED, InvestigationOutcome.CAUSE_IDENTIFIED, None, ("E1",))
    assert synthesis_adjustments(raw_texts=["[E1]"], valid_codes={"E1"}, confidence_from=0.8, confidence_to=0.8, outcome_decision=outcome) == []

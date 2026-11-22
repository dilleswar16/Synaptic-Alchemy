"""keigan/ai/investigation_outcome_rules.py: the rules that can only lower a hypothesis's state and an investigation's outcome (spec 27, 4.4; AC-7 to AC-11, AC-13)."""

from __future__ import annotations

import itertools

import pytest

from keigan.ai.investigation_outcome_rules import (
    EvidenceFacts, StateThresholds, baseline_comparison_of, decide_hypothesis_state, decide_outcome, is_decisive_signal,
)
from keigan.entities.status_values import BaselineComparison, EvidenceCheckOutcome, HypothesisState, HypothesisStateGuard, InvestigationOutcome, InvestigationOutcomeGuard, RiskLevel

THRESHOLDS = StateThresholds(supported_minimum=0.5, ruled_out_maximum=0.2)
SUPPORTED, RULED_OUT, INCONCLUSIVE = HypothesisState.SUPPORTED, HypothesisState.RULED_OUT, HypothesisState.INCONCLUSIVE


def evidence(code: str, *, outcome: EvidenceCheckOutcome = EvidenceCheckOutcome.SIGNAL, strength: RiskLevel = RiskLevel.HIGH, baseline: BaselineComparison = BaselineComparison.COMPARED) -> EvidenceFacts:
    return EvidenceFacts(code=code, check_outcome=outcome, signal_strength=strength, baseline_comparison=baseline)


STRONG = evidence("E1")
WEAK = evidence("E2", strength=RiskLevel.LOW)
HEALTHY = evidence("E3", outcome=EvidenceCheckOutcome.NO_SIGNAL, strength=RiskLevel.LOW)
CHANGE_EVENT = evidence("E4", strength=RiskLevel.LOW, baseline=BaselineComparison.NO_BASELINE_FOR_SOURCE)


# ── What counts as a decisive signal ─────────────────────────────────────────────────────────────


def test_a_strong_or_medium_signal_that_was_compared_with_the_baseline_is_decisive() -> None:
    assert is_decisive_signal(STRONG) and is_decisive_signal(evidence("E", strength=RiskLevel.MEDIUM))


def test_a_weak_signal_that_was_compared_with_the_baseline_is_not_decisive() -> None:
    assert not is_decisive_signal(WEAK)


def test_a_change_event_has_no_baseline_so_it_is_decisive_whatever_its_strength() -> None:
    assert is_decisive_signal(CHANGE_EVENT)


def test_a_healthy_result_and_an_unread_source_are_never_decisive() -> None:
    assert not is_decisive_signal(HEALTHY)
    assert not is_decisive_signal(evidence("E", outcome=EvidenceCheckOutcome.NOT_CHECKED, baseline=BaselineComparison.NO_BASELINE_FOR_SOURCE))


@pytest.mark.parametrize(("category", "expected"), [
    ("change_event", BaselineComparison.NO_BASELINE_FOR_SOURCE), ("synthetic_probe", BaselineComparison.NO_BASELINE_FOR_SOURCE),
    ("failed_requests", BaselineComparison.COMPARED), ("error_logs", BaselineComparison.COMPARED), ("ai_planned_query", BaselineComparison.COMPARED),
])
def test_only_changes_and_probes_have_no_baseline(category: str, expected: BaselineComparison) -> None:
    assert baseline_comparison_of(category) == expected


# ── Hypothesis state (AC-7, AC-8, AC-9) ──────────────────────────────────────────────────────────


def test_a_supported_hypothesis_with_a_decisive_signal_and_enough_confidence_stays_supported() -> None:
    decision = decide_hypothesis_state(SUPPORTED, 0.8, [STRONG], [], THRESHOLDS)
    assert (decision.final, decision.proposed, decision.guard, decision.decisive_codes) == (SUPPORTED, SUPPORTED, None, ("E1",))


def test_support_that_rests_only_on_weak_compared_items_or_rule_outs_becomes_inconclusive() -> None:
    for cited in ([WEAK], [HEALTHY], [WEAK, HEALTHY], []):
        decision = decide_hypothesis_state(SUPPORTED, 0.9, cited, [], THRESHOLDS)
        assert (decision.final, decision.guard) == (INCONCLUSIVE, HypothesisStateGuard.SUPPORT_NOT_IN_EVIDENCE), cited


def test_support_from_a_change_event_stays_supported_even_though_it_is_weak() -> None:
    assert decide_hypothesis_state(SUPPORTED, 0.7, [CHANGE_EVENT], [], THRESHOLDS).final == SUPPORTED


def test_support_below_the_minimum_confidence_becomes_inconclusive_and_equal_stays() -> None:
    lowered = decide_hypothesis_state(SUPPORTED, 0.49, [STRONG], [], THRESHOLDS)
    assert (lowered.final, lowered.guard) == (INCONCLUSIVE, HypothesisStateGuard.CONFIDENCE_BELOW_SUPPORTED_MINIMUM)
    assert decide_hypothesis_state(SUPPORTED, 0.5, [STRONG], [], THRESHOLDS).final == SUPPORTED


def test_a_rule_out_needs_a_read_contradicting_item() -> None:
    lowered = decide_hypothesis_state(RULED_OUT, 0.1, [], [], THRESHOLDS)
    assert (lowered.final, lowered.guard) == (INCONCLUSIVE, HypothesisStateGuard.RULE_OUT_NOT_IN_EVIDENCE)
    unread = evidence("E9", outcome=EvidenceCheckOutcome.NOT_CHECKED, baseline=BaselineComparison.NO_BASELINE_FOR_SOURCE)
    assert decide_hypothesis_state(RULED_OUT, 0.1, [], [unread], THRESHOLDS).guard == HypothesisStateGuard.RULE_OUT_NOT_IN_EVIDENCE
    assert decide_hypothesis_state(RULED_OUT, 0.1, [], [HEALTHY], THRESHOLDS).final == RULED_OUT


def test_a_rule_out_above_the_maximum_confidence_becomes_inconclusive_and_equal_stays() -> None:
    lowered = decide_hypothesis_state(RULED_OUT, 0.21, [], [HEALTHY], THRESHOLDS)
    assert (lowered.final, lowered.guard) == (INCONCLUSIVE, HypothesisStateGuard.CONFIDENCE_ABOVE_RULED_OUT_MAXIMUM)
    assert decide_hypothesis_state(RULED_OUT, 0.2, [], [HEALTHY], THRESHOLDS).final == RULED_OUT


def test_an_inconclusive_proposal_is_kept_whatever_the_evidence_and_confidence() -> None:
    for confidence, supporting, contradicting in itertools.product((0.0, 0.3, 0.9), ([], [STRONG]), ([], [HEALTHY])):
        decision = decide_hypothesis_state(INCONCLUSIVE, confidence, supporting, contradicting, THRESHOLDS)
        assert (decision.final, decision.guard) == (INCONCLUSIVE, None)


# ── Investigation outcome (AC-10, AC-11, AC-13) ──────────────────────────────────────────────────


def outcome_of(proposed: InvestigationOutcome | None, leading_state: HypothesisState | None, rows: list[EvidenceFacts], *, synthesis_was_available: bool = True):
    return decide_outcome(proposed, leading_state=leading_state, evidence=rows, synthesis_was_available=synthesis_was_available)


def test_with_no_decisive_signal_the_outcome_is_cause_not_visible_whatever_the_model_proposed() -> None:
    for proposed in InvestigationOutcome:
        decision = outcome_of(proposed, SUPPORTED, [WEAK, HEALTHY])
        assert decision.final == InvestigationOutcome.CAUSE_NOT_VISIBLE
        expected_guard = None if proposed == InvestigationOutcome.CAUSE_NOT_VISIBLE else InvestigationOutcomeGuard.NOTHING_CHANGED_IN_CHECKED_SOURCES
        assert decision.guard == expected_guard, proposed


def test_no_evidence_at_all_is_also_not_visible() -> None:
    assert outcome_of(InvestigationOutcome.CAUSE_IDENTIFIED, None, []).final == InvestigationOutcome.CAUSE_NOT_VISIBLE


def test_a_cause_with_a_supported_lead_stands() -> None:
    decision = outcome_of(InvestigationOutcome.CAUSE_IDENTIFIED, SUPPORTED, [STRONG])
    assert (decision.final, decision.proposed, decision.guard) == (InvestigationOutcome.CAUSE_IDENTIFIED, InvestigationOutcome.CAUSE_IDENTIFIED, None)


@pytest.mark.parametrize("leading_state", [INCONCLUSIVE, RULED_OUT, None])
def test_a_cause_whose_lead_is_not_supported_becomes_inconclusive(leading_state: HypothesisState | None) -> None:
    decision = outcome_of(InvestigationOutcome.CAUSE_IDENTIFIED, leading_state, [STRONG])
    assert (decision.final, decision.guard) == (InvestigationOutcome.INCONCLUSIVE, InvestigationOutcomeGuard.LEADING_HYPOTHESIS_NOT_SUPPORTED)


def test_the_model_is_believed_when_it_is_more_cautious_than_the_rules() -> None:
    for proposed in (InvestigationOutcome.INCONCLUSIVE, InvestigationOutcome.CAUSE_NOT_VISIBLE):
        decision = outcome_of(proposed, SUPPORTED, [STRONG])
        assert (decision.final, decision.guard) == (proposed, None)


def test_without_a_synthesis_a_supported_lead_gives_a_cause_and_anything_else_is_inconclusive() -> None:
    identified = outcome_of(None, SUPPORTED, [STRONG], synthesis_was_available=False)
    assert (identified.final, identified.proposed, identified.guard) == (InvestigationOutcome.CAUSE_IDENTIFIED, None, InvestigationOutcomeGuard.SYNTHESIS_UNAVAILABLE)
    undecided = outcome_of(None, INCONCLUSIVE, [STRONG], synthesis_was_available=False)
    assert (undecided.final, undecided.guard) == (InvestigationOutcome.INCONCLUSIVE, InvestigationOutcomeGuard.SYNTHESIS_UNAVAILABLE)


def test_without_a_synthesis_and_without_a_decisive_signal_the_cause_is_not_visible() -> None:
    assert outcome_of(None, SUPPORTED, [HEALTHY], synthesis_was_available=False).final == InvestigationOutcome.CAUSE_NOT_VISIBLE


def test_the_decision_names_the_decisive_evidence() -> None:
    assert outcome_of(InvestigationOutcome.CAUSE_IDENTIFIED, SUPPORTED, [STRONG, WEAK, CHANGE_EVENT]).decisive_codes == ("E1", "E4")

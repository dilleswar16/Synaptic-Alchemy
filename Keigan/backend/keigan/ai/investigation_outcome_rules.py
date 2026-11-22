"""The rules that decide how far an investigation got (spec 27, 4.4): pure functions with no database and no model.

The model proposes a state for each hypothesis and an outcome for the investigation, and these rules check what a person could check: is the cited evidence real, did it
change against the healthy window, is the confidence in the band the prompt promised. They can only **lower** a proposal (supported to inconclusive, cause identified to
inconclusive or not visible), never raise one, and every decision keeps the proposal, the rule that changed it and the evidence that decided it, so the screen (and the decision
trace of doc 28) can say exactly what the model said and what Keigan's rules did to it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from keigan.entities.status_values import (
    BaselineComparison, EvidenceCheckOutcome, HypothesisState, HypothesisStateGuard, InvestigationOutcome, InvestigationOutcomeGuard, RiskLevel,
)

# A change event or a failing probe cannot be compared with the hour before: the change read already covers the day before the window, and a probe cannot be sent into the past.
CATEGORIES_WITHOUT_A_BASELINE = frozenset({"change_event", "synthetic_probe"})
_CHANGED_STRENGTHS = frozenset({RiskLevel.MEDIUM, RiskLevel.HIGH})


@dataclass(frozen=True)
class EvidenceFacts:
    """What the rules need to know about one evidence item."""

    code: str
    check_outcome: EvidenceCheckOutcome | str | None
    signal_strength: RiskLevel | str
    baseline_comparison: BaselineComparison | str | None


@dataclass(frozen=True)
class StateThresholds:
    """The confidence band a state promises: supported at least ``supported_minimum``, ruled out at most ``ruled_out_maximum`` (the prompt renders the same two numbers)."""

    supported_minimum: float
    ruled_out_maximum: float


@dataclass(frozen=True)
class StateDecision:
    final: HypothesisState
    proposed: HypothesisState
    guard: HypothesisStateGuard | None
    decisive_codes: tuple[str, ...]


@dataclass(frozen=True)
class OutcomeDecision:
    final: InvestigationOutcome
    proposed: InvestigationOutcome | None
    guard: InvestigationOutcomeGuard | None
    decisive_codes: tuple[str, ...]


def baseline_comparison_of(evidence_category: str) -> BaselineComparison:
    return BaselineComparison.NO_BASELINE_FOR_SOURCE if evidence_category in CATEGORIES_WITHOUT_A_BASELINE else BaselineComparison.COMPARED


def is_decisive_signal(evidence: EvidenceFacts) -> bool:
    """Only a check that found something, and that changed against the baseline (or has no baseline to change against), can support a cause."""
    if evidence.check_outcome != EvidenceCheckOutcome.SIGNAL:
        return False
    return evidence.baseline_comparison == BaselineComparison.NO_BASELINE_FOR_SOURCE or evidence.signal_strength in _CHANGED_STRENGTHS


def _decisive_codes(evidence: Iterable[EvidenceFacts]) -> tuple[str, ...]:
    return tuple(item.code for item in evidence if is_decisive_signal(item))


def decide_hypothesis_state(
    proposed: HypothesisState, confidence: float, supporting: Sequence[EvidenceFacts], contradicting: Sequence[EvidenceFacts], thresholds: StateThresholds,
) -> StateDecision:
    """``supporting`` and ``contradicting`` are the evidence items behind the codes the hypothesis cited that exist (a code the model made up is not evidence)."""
    decisive_codes = _decisive_codes(supporting)
    guard: HypothesisStateGuard | None = None
    if proposed == HypothesisState.SUPPORTED:
        if not decisive_codes:
            guard = HypothesisStateGuard.SUPPORT_NOT_IN_EVIDENCE
        elif confidence < thresholds.supported_minimum:
            guard = HypothesisStateGuard.CONFIDENCE_BELOW_SUPPORTED_MINIMUM
    elif proposed == HypothesisState.RULED_OUT:
        if not any(item.check_outcome != EvidenceCheckOutcome.NOT_CHECKED for item in contradicting):  # only a source that was read can rule a cause out
            guard = HypothesisStateGuard.RULE_OUT_NOT_IN_EVIDENCE
        elif confidence > thresholds.ruled_out_maximum:
            guard = HypothesisStateGuard.CONFIDENCE_ABOVE_RULED_OUT_MAXIMUM
    return StateDecision(HypothesisState.INCONCLUSIVE if guard else proposed, proposed, guard, decisive_codes)


def decide_outcome(
    proposed: InvestigationOutcome | None, *, leading_state: HypothesisState | None, evidence: Sequence[EvidenceFacts], synthesis_was_available: bool,
) -> OutcomeDecision:
    """``leading_state`` is the final state of the leading hypothesis (the synthesis's lead, or the most confident one when it named none); ``evidence`` is every item that was persisted.

    Nothing changed in the sources Keigan could read: the cause is not visible, whatever the model proposed (D-A2-3, the case where weak models invent causes). Without a synthesis
    there is no proposal, and the outcome follows the lead. A cause needs a supported lead; a model more cautious than the rules is believed.
    """
    decisive_codes = _decisive_codes(evidence)
    final, guard = proposed, None
    if not decisive_codes:
        final = InvestigationOutcome.CAUSE_NOT_VISIBLE
        guard = None if proposed == final else InvestigationOutcomeGuard.NOTHING_CHANGED_IN_CHECKED_SOURCES
    elif not synthesis_was_available:
        final = InvestigationOutcome.CAUSE_IDENTIFIED if leading_state == HypothesisState.SUPPORTED else InvestigationOutcome.INCONCLUSIVE
        guard = InvestigationOutcomeGuard.SYNTHESIS_UNAVAILABLE
    elif proposed == InvestigationOutcome.CAUSE_IDENTIFIED and leading_state != HypothesisState.SUPPORTED:
        final, guard = InvestigationOutcome.INCONCLUSIVE, InvestigationOutcomeGuard.LEADING_HYPOTHESIS_NOT_SUPPORTED
    if final is None:
        raise ValueError("A synthesis that was available must have proposed an outcome (the schema requires one).")
    return OutcomeDecision(final, proposed, guard, decisive_codes)

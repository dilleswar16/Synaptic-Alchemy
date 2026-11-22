"""What Keigan's code changed in a model's answer, as small coded records for the decision trace (spec 28, 4.2 ``adjustments_json``).

Pure functions. Each adjustment is ``{"code": ..., "parameters": {...}}`` with ids, codes and numbers only: the screen turns the code into a sentence in the person's language.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from keigan.ai.investigation_outcome_rules import OutcomeDecision, StateDecision
from keigan.ai.prompt_safety import find_citation_codes


def _adjustment(code: str, **parameters: Any) -> dict[str, Any]:
    return {"code": code, "parameters": parameters}


def removed_citation_codes(raw_texts: Iterable[str | None], valid_codes: set[str]) -> list[str]:
    """Codes the model wrote that do not exist for this investigation (they are removed from the text that is stored)."""
    cited: set[str] = set()
    for text in raw_texts:
        cited |= find_citation_codes(text)
    return sorted(cited - valid_codes)


def hypothesis_adjustments(
    *, raw_texts: Iterable[str | None], valid_codes: set[str], dropped_evidence_codes: Iterable[str], replaced_file_path_count: int,
    risk_from: str | None, risk_to: str | None, state_decision: StateDecision,
) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []
    if removed := removed_citation_codes(raw_texts, valid_codes):
        adjustments.append(_adjustment("invalid_citations_removed", codes=removed))
    if dropped := sorted(set(dropped_evidence_codes)):
        adjustments.append(_adjustment("evidence_codes_dropped", codes=dropped))
    if replaced_file_path_count:
        adjustments.append(_adjustment("file_path_replaced", count=replaced_file_path_count))
    if risk_from is not None and risk_to is not None and risk_from != risk_to:
        adjustments.append(_adjustment("command_risk_raised", **{"from": risk_from, "to": risk_to}))
    if state_decision.guard is not None:
        adjustments.append(_adjustment("hypothesis_state_guarded", proposed=state_decision.proposed.value, final=state_decision.final.value, guard=state_decision.guard.value))
    return adjustments


def synthesis_adjustments(
    *, raw_texts: Iterable[str | None], valid_codes: set[str], confidence_from: float, confidence_to: float, outcome_decision: OutcomeDecision,
) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []
    if removed := removed_citation_codes(raw_texts, valid_codes):
        adjustments.append(_adjustment("invalid_citations_removed", codes=removed))
    if round(confidence_from, 2) != round(confidence_to, 2):
        adjustments.append(_adjustment("confidence_capped", **{"from": round(confidence_from, 2), "to": round(confidence_to, 2)}))
    if outcome_decision.guard is not None:
        adjustments.append(_adjustment(
            "outcome_guarded", proposed=outcome_decision.proposed.value if outcome_decision.proposed else None, final=outcome_decision.final.value, guard=outcome_decision.guard.value,
        ))
    return adjustments

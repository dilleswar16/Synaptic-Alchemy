"""The fix plan of an investigation: the steps the synthesis recommends, picked from the three analysts' checked steps (spec 33, 4.5).

The synthesis names steps by analyst and number; nothing is copied, so the plan can only contain a step that passed the validator. A reference that does not resolve, repeats a step or points at a
step whose action was withheld is dropped. When nothing usable is left (or the synthesis failed) the plan is the leading analyst's steps in their own order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

PLAN_SCHEMA_VERSION = 2


def step_is_usable(step: Mapping[str, Any]) -> bool:
    """A step whose action was withheld has nothing to copy or do, so the plan does not recommend it (its description is still on the analyst's card)."""
    return step["action"]["withheld_reason"] is None


def _steps_of(hypothesis: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(hypothesis["proposed_fix"].get("steps", []))


def build_fix_plan(
    overview_markdown: str, references: Sequence[tuple[str, int]], hypotheses: Sequence[Mapping[str, Any]], leading_perspective: str | None, maximum_steps: int,
) -> dict[str, Any]:
    """``references``: (perspective, step number from 1) in the order the synthesis gave. ``hypotheses``: the validated hypotheses (each with ``analysis_perspective`` and ``proposed_fix``)."""
    steps_by_perspective = {hypothesis["analysis_perspective"]: _steps_of(hypothesis) for hypothesis in hypotheses}
    chosen: list[tuple[str, str]] = []
    for perspective, step_number in references:
        steps = steps_by_perspective.get(perspective, [])
        if not 1 <= step_number <= len(steps) or not step_is_usable(steps[step_number - 1]):
            continue
        reference = (perspective, steps[step_number - 1]["step_id"])
        if reference not in chosen:
            chosen.append(reference)
    if not chosen:
        fallback = leading_perspective if leading_perspective in steps_by_perspective else next(iter(steps_by_perspective), None)
        chosen = [(fallback, step["step_id"]) for step in steps_by_perspective.get(fallback or "", []) if step_is_usable(step)] if fallback else []
    return {
        "schema_version": PLAN_SCHEMA_VERSION, "overview_markdown": overview_markdown,
        "step_references": [{"perspective": perspective, "step_id": step_id} for perspective, step_id in chosen[:maximum_steps]],
    }


def resolve_plan_steps(plan: Mapping[str, Any], hypotheses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The stored steps a plan points at, each with its analyst's ``perspective``; a reference that no longer resolves is skipped."""
    steps_by_id = {step["step_id"]: step for hypothesis in hypotheses for step in _steps_of(hypothesis)}
    return [
        {**steps_by_id[reference["step_id"]], "perspective": reference["perspective"]}
        for reference in plan.get("step_references", []) if reference["step_id"] in steps_by_id
    ]

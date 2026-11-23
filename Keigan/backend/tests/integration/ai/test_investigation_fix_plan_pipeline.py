"""Suggested fixes through the real graph and the offline model (spec 33, phase 2; AC-14 to AC-18): each hypothesis stores checked steps, the synthesis recommends steps by reference, the plan
is stored and resolved for the API, and the Markdown other channels read is written by code."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation, InvestigationHypothesis
from keigan.ai.fix_plan import build_fix_plan
from keigan.dtos.investigation_dtos import ProposedFixDto
from keigan.services.investigation_service import InvestigationService
from tests.integration.ai.test_investigation_honest_outcomes import run_manual_investigation
from tests.integration.ai.test_investigation_mock_fixes import validated_steps


async def test_every_hypothesis_of_a_new_investigation_stores_checked_steps_with_ids(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    async with open_session() as session:
        hypotheses = list((await session.scalars(select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation_id))).all())
    assert len(hypotheses) == 3
    for hypothesis in hypotheses:
        fix = hypothesis.proposed_fix_json
        assert fix["schema_version"] == 2 and "verification_steps" not in fix and "rollback_steps" not in fix
        assert [step["step_id"] for step in fix["steps"]] == [f"{hypothesis.analysis_perspective}-{number}" for number in range(1, len(fix["steps"]) + 1)]
        assert all({"title", "purpose", "risk_level", "warnings", "action", "check", "revert"} <= step.keys() for step in fix["steps"])


async def test_the_plan_is_stored_by_reference_and_the_markdown_is_written_from_it(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
    plan = investigation.fix_plan_json
    assert plan["schema_version"] == 2 and plan["overview_markdown"] and plan["step_references"]
    assert all(set(reference) == {"perspective", "step_id"} for reference in plan["step_references"])
    assert investigation.how_to_fix_markdown.startswith(plan["overview_markdown"]) and "**Step 1." in investigation.how_to_fix_markdown


def a_stored_investigation_with_a_cause() -> tuple[SimpleNamespace, list[SimpleNamespace]]:
    """What the service reads: the investigation's plan and the hypotheses' stored fixes, as the offline model's connection pool scenario writes them."""
    steps = validated_steps("database_connection_pool_exhaustion")
    hypotheses = [SimpleNamespace(analysis_perspective="application", proposed_fix_json={"schema_version": 2, "summary": "s", "steps": steps}), SimpleNamespace(analysis_perspective="dependencies", proposed_fix_json={"schema_version": 2, "summary": "s", "steps": []})]
    plan = build_fix_plan("Restore the setting first.", [("application", 1), ("application", 2), ("application", 4)], [{"analysis_perspective": row.analysis_perspective, "proposed_fix": row.proposed_fix_json} for row in hypotheses], "application", 8)
    return SimpleNamespace(fix_plan_json=plan), hypotheses


def test_the_plan_resolves_to_the_leading_analysts_steps_in_the_order_recommended() -> None:
    investigation, hypotheses = a_stored_investigation_with_a_cause()
    plan = InvestigationService._fix_plan(investigation, hypotheses)  # type: ignore[arg-type]
    assert plan is not None and plan.overview_markdown == "Restore the setting first."
    assert [step.step_id for step in plan.steps] == ["application-1", "application-2", "application-4"] and {step.perspective for step in plan.steps} == {"application"}


def test_an_investigation_without_a_plan_has_none() -> None:
    assert InvestigationService._fix_plan(SimpleNamespace(fix_plan_json=None), []) is None  # type: ignore[arg-type]


def test_the_api_shape_of_a_checked_step_carries_the_rules_the_browser_checks_typed_values_with() -> None:
    _, hypotheses = a_stored_investigation_with_a_cause()
    shown = ProposedFixDto.model_validate(hypotheses[0].proposed_fix_json).model_dump(by_alias=True, mode="json")
    assert shown["schemaVersion"] == 2 and shown["steps"] == [] and shown["fixSteps"] and "verificationSteps" in shown
    parameters = [parameter for step in shown["fixSteps"] for action in (step["action"], step["check"], step["revert"]) if action and action["command"] for parameter in action["command"]["parameters"]]
    assert parameters and all({"valuePattern", "barePattern", "maximumLength", "labelKey", "status"} <= parameter.keys() and parameter["valuePattern"] for parameter in parameters)
    renderings = [rendering for step in shown["fixSteps"] for rendering in (step["action"]["command"] or {"renderings": []})["renderings"]]
    assert renderings and all({"dialect", "text", "riskLevel", "segments"} <= rendering.keys() for rendering in renderings)


@pytest.mark.parametrize("field", ["verification_steps", "rollback_steps"])
async def test_an_investigation_written_before_the_plan_still_reads_as_it_did(field: str) -> None:
    """Spec 33, F9: version 1 rows are never rewritten and keep their own shape."""
    from keigan.dtos.investigation_dtos import ProposedFixDto

    old = ProposedFixDto.model_validate({"summary": "s", "steps": [{"description": "d", "command_text": "kubectl get pods"}], field: ["x"]})
    assert old.schema_version == 1 and old.fix_steps == [] and old.steps[0].command_text == "kubectl get pods" and getattr(old, field) == ["x"]

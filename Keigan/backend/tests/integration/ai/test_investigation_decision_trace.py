"""The decision trace through the real investigation graph on the mock model (spec 28, AC-7 to AC-9, AC-13, AC-14)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from keigan.ai.investigation_graph import InvestigationGraphRunner
from keigan.config.database_config import open_session
from keigan.entities.incident_entities import Investigation, InvestigationHypothesis, InvestigationTraceStep
from keigan.entities.platform_entities import AuditEvent
from keigan.services.investigation_service import InvestigationService
from keigan.services.investigation_trace_recorder import InvestigationTraceRecorder

PROBLEM = "Claim submissions are timing out for customers in Japan and the claims screen shows errors."


async def run_manual_investigation(seed_context) -> str:  # noqa: ANN001
    async with open_session() as session:
        investigation_id = await InvestigationService(session).start_investigation(seed_context.application_ids_by_code["CLMJP"], "manual", description=PROBLEM)
    async with open_session() as session:
        await InvestigationService(session).run_investigation(investigation_id)
    return investigation_id


async def trace_of(investigation_id: str) -> list[InvestigationTraceStep]:
    async with open_session() as session:
        return list((await session.scalars(select(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id).order_by(InvestigationTraceStep.sequence_number))).all())


async def audit_rows(investigation_id: str, action_name: str) -> list[AuditEvent]:
    async with open_session() as session:
        return list((await session.scalars(select(AuditEvent).where(AuditEvent.target_entity_id == investigation_id, AuditEvent.action_name == action_name))).all())


async def test_a_run_records_its_inputs_decisions_ai_calls_evidence_and_outcome_in_order(seed_context) -> None:
    steps = await trace_of(await run_manual_investigation(seed_context))
    assert [step.sequence_number for step in steps] == list(range(1, len(steps) + 1))  # no gaps
    kinds = [step.step_kind for step in steps]
    assert kinds[0] == "inputs" and kinds[-1] == "outcome" and kinds.count("inputs") == 1 and kinds.count("outcome") == 1 and kinds.count("evidence") == 1
    assert {step.decision_kind for step in steps if step.step_kind == "decision"} >= {"services_selected", "priority_set"}
    calls = {step.feature_name for step in steps if step.step_kind == "ai_call"}
    assert {"incident_triage", "hypothesis_application", "hypothesis_dependencies", "hypothesis_infrastructure", "rca_synthesis"} <= calls
    assert steps[0].details_json["pipelineVersion"] and steps[0].details_json["settings"]["supportedMinimumConfidence"] == 0.5 and steps[0].details_json["provider"]["isMock"] is True


async def test_each_ai_call_names_its_prompt_and_what_went_in_by_hash(seed_context) -> None:
    steps = await trace_of(await run_manual_investigation(seed_context))
    synthesis = next(step for step in steps if step.feature_name == "rca_synthesis")
    assert synthesis.prompt_version == "6" and len(synthesis.prompt_template_sha256) == 64 and len(synthesis.system_prompt_sha256) == 64
    titles = {section["title"] for section in synthesis.input_manifest_json}
    assert {"Evidence index", "What Keigan could not check", "Hypotheses from the three analysts"} <= titles
    assert all(len(section["sha256"]) == 64 and "content" not in section for section in synthesis.input_manifest_json)
    assert (synthesis.provider_name, synthesis.estimated_input_token_count > 0) == ("mock", True)  # the mock writes no usage rows, so the estimate is kept
    assert synthesis.raw_output_json and synthesis.raw_output_sha256


async def test_each_hypothesis_call_is_linked_to_the_hypothesis_row_it_produced(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    steps = await trace_of(investigation_id)
    async with open_session() as session:
        hypotheses = {row.analysis_perspective: row.hypothesis_id for row in (await session.scalars(select(InvestigationHypothesis).where(InvestigationHypothesis.investigation_id == investigation_id))).all()}
    for perspective, hypothesis_id in hypotheses.items():
        assert next(step for step in steps if step.feature_name == f"hypothesis_{perspective}").hypothesis_id == hypothesis_id


async def test_the_outcome_step_records_the_outcome_and_the_states_with_their_proposals(seed_context) -> None:
    steps = await trace_of(await run_manual_investigation(seed_context))
    outcome = steps[-1].details_json
    assert outcome["status"] == "completed" and outcome["outcome"] == "cause_not_visible" and outcome["proposedOutcome"] == "cause_not_visible"
    assert [item["perspective"] for item in outcome["hypotheses"]] == ["application", "dependencies", "infrastructure"]
    assert all(item["state"] == "inconclusive" and item["proposedState"] == "inconclusive" for item in outcome["hypotheses"])


async def test_a_recorder_that_raises_on_every_call_never_changes_the_investigation(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fails(self: InvestigationTraceRecorder, *arguments: Any, **keyword_arguments: Any) -> None:
        raise RuntimeError("recorder bug")

    original_add = InvestigationTraceRecorder._add
    monkeypatch.setattr(InvestigationTraceRecorder, "_add", always_fails)
    investigation_id = await run_manual_investigation(seed_context)
    monkeypatch.setattr(InvestigationTraceRecorder, "_add", original_add)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
    assert investigation.investigation_status == "completed" and investigation.executive_summary
    assert await trace_of(investigation_id) == []  # recording stopped at its first error; nothing partial and misleading was stored


async def test_the_audit_row_of_a_finished_investigation_has_codes_and_counts_only(seed_context) -> None:
    investigation_id = await run_manual_investigation(seed_context)
    (audit,) = await audit_rows(investigation_id, "investigation.concluded")
    details = audit.action_details_json
    assert details["status"] == "completed" and details["outcome"] == "cause_not_visible" and details["traceStepCount"] >= 10 and details["coverageGapCount"] >= 0
    assert details["hypothesisStates"] == {"application": "inconclusive", "dependencies": "inconclusive", "infrastructure": "inconclusive"}
    assert details["promptVersions"]["rca_synthesis"] == "6" and set(details) >= {"modelNames", "inputTokenCount", "outputTokenCount", "outcomeGuard"}


async def test_a_run_that_fails_keeps_the_committed_steps_and_adds_a_failed_outcome_and_an_audit_row(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_blast_radius(self: InvestigationGraphRunner, state: dict) -> dict:
        raise RuntimeError("the blast radius stage broke")

    monkeypatch.setattr(InvestigationGraphRunner, "blast_radius_node", failing_blast_radius)
    investigation_id = await run_manual_investigation(seed_context)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
    assert investigation.investigation_status == "failed"
    steps = await trace_of(investigation_id)
    assert steps[0].step_kind == "inputs" and any(step.feature_name == "rca_synthesis" for step in steps)  # the stages that were committed before the failure
    assert [step.sequence_number for step in steps] == list(range(1, len(steps) + 1))
    assert (steps[-1].step_kind, steps[-1].step_status) == ("outcome", "failed") and steps[-1].details_json["failedAfterStage"]
    (audit,) = await audit_rows(investigation_id, "investigation.failed")
    assert audit.action_details_json["failedAfterStage"] and audit.action_details_json["traceStepCount"] >= 1

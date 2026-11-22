"""keigan/services/investigation_trace_recorder.py: what the decision trace stores (spec 28, AC-8, AC-12 (storage side), AC-16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from keigan.ai.investigation_ai_caller import InvestigationAiCall
from keigan.ai.llm_gateway import PromptSection
from keigan.config.database_config import open_session
from keigan.config.settings import get_settings
from keigan.entities.incident_entities import Investigation, InvestigationTraceStep
from keigan.entities.status_values import InvestigationAiCallFailure, InvestigationDecisionKind, InvestigationStage, InvestigationTraceStepKind, InvestigationTraceStepStatus
from keigan.exceptions.keigan_exceptions import LlmUnavailableException, TokenBudgetExceededException
from keigan.services.investigation_trace_recorder import TRUNCATED_OUTPUT_KEY, InvestigationTraceRecorder, failure_code_of, section_manifest
from keigan.utils.pii_masker import PiiMasker


async def new_investigation(seed_context) -> str:  # noqa: ANN001
    async with open_session() as session:
        investigation = Investigation(
            application_id=seed_context.application_ids_by_code["CLMJP"], investigation_trigger="manual", investigation_status="running", current_stage_name="triage",
        )
        session.add(investigation)
        await session.flush()
        return investigation.investigation_id


def a_call(feature_name: str = "hypothesis_dependencies", *, raw_output: dict | None = None, failure: Exception | None = None, sections: tuple[PromptSection, ...] = ()) -> InvestigationAiCall:
    return InvestigationAiCall(
        trace_step_id=str(uuid.uuid4()), feature_name=feature_name, prompt_key=feature_name, prompt_version="4", prompt_template_sha256="a" * 64, system_prompt_sha256="b" * 64,
        provider_name="scripted", model_name="m", model_tier="deep", prompt_sections=sections, raw_output=raw_output if failure is None else None, failure=failure,
        started_at=datetime(2026, 11, 23, tzinfo=UTC), duration_milliseconds=1200, estimated_input_tokens=None, estimated_output_tokens=None,
    )


async def with_recorder(seed_context, work) -> list[InvestigationTraceStep]:  # noqa: ANN001
    investigation_id = await new_investigation(seed_context)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
        recorder = InvestigationTraceRecorder(session, investigation, PiiMasker(), get_settings())
        await work(recorder)
    async with open_session() as session:
        return list((await session.scalars(select(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id).order_by(InvestigationTraceStep.sequence_number))).all())


async def test_steps_are_numbered_in_the_order_they_were_recorded(seed_context) -> None:
    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_inputs({"trigger": "manual"})
        recorder.record_decision(InvestigationDecisionKind.SERVICES_SELECTED, {"selected": ["a"]})
        recorder.record_ai_call(a_call("incident_triage"))
        recorder.record_evidence({"kept": 3})
        recorder.record_outcome({"outcome": "cause_identified"})

    steps = await with_recorder(seed_context, work)
    assert [step.sequence_number for step in steps] == [1, 2, 3, 4, 5]
    assert [step.step_kind for step in steps] == ["inputs", "decision", "ai_call", "evidence", "outcome"]
    assert [step.stage_name for step in steps] == ["triage", "triage", "triage", "evidence", "completed"]
    assert steps[1].decision_kind == "services_selected" and steps[0].details_json == {"trigger": "manual"}


async def test_an_ai_call_keeps_its_prompt_facts_and_a_manifest_that_has_hashes_not_text(seed_context) -> None:
    sections = (PromptSection("Evidence index", "A [E1] and [E2]", is_untrusted=True, source_label="telemetry evidence"), PromptSection("Task", "Do it."))

    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_ai_call(a_call(raw_output={"confidence_score": 0.4}, sections=sections))

    (step,) = await with_recorder(seed_context, work)
    assert (step.prompt_key, step.prompt_version, step.prompt_template_sha256, step.system_prompt_sha256) == ("hypothesis_dependencies", "4", "a" * 64, "b" * 64)
    assert (step.provider_name, step.model_name, step.model_tier, step.duration_milliseconds, step.stage_name) == ("scripted", "m", "deep", 1200, "hypotheses")
    evidence_section, task_section = step.input_manifest_json
    assert evidence_section["citationCodes"] == ["E1", "E2"] and evidence_section["isUntrusted"] is True and len(evidence_section["sha256"]) == 64
    assert "A [E1]" not in str(step.input_manifest_json)  # the text itself is never stored
    assert task_section["isTruncated"] is False and step.raw_output_json == {"confidence_score": 0.4}


def test_a_section_the_gateway_cuts_is_marked_truncated() -> None:
    manifest = section_manifest([PromptSection("Big", "x" * 500, is_untrusted=True, maximum_characters=100), PromptSection("Trusted", "y" * 500, maximum_characters=100)])
    assert (manifest[0]["characterCount"], manifest[0]["sentCharacterCount"], manifest[0]["isTruncated"]) == (500, 100, True)
    assert manifest[1]["isTruncated"] is False  # trusted sections are sent whole


async def test_the_raw_answer_is_masked_before_it_is_stored(seed_context) -> None:
    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_ai_call(a_call(raw_output={"hypothesis_statement_markdown": "Ask taro.yamada@example.test about the pool"}))

    (step,) = await with_recorder(seed_context, work)
    assert "taro.yamada@example.test" not in str(step.raw_output_json) and "@example.test" not in str(step.raw_output_json)


async def test_a_long_raw_answer_is_cut_to_the_setting_and_marked(seed_context, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "investigation_trace_raw_output_stored_characters", 1000)

    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_ai_call(a_call(raw_output={"reasoning_markdown": "x" * 5000}))

    (step,) = await with_recorder(seed_context, work)
    assert step.raw_output_is_truncated is True and step.raw_output_character_count > 1000
    assert list(step.raw_output_json) == [TRUNCATED_OUTPUT_KEY] and len(step.raw_output_json[TRUNCATED_OUTPUT_KEY]) == 1000 and len(step.raw_output_sha256) == 64


async def test_a_failed_call_is_a_failed_step_with_a_code_and_no_exception_text(seed_context) -> None:
    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_ai_call(a_call("rca_synthesis", failure=LlmUnavailableException("secret-host-name:443 refused")))

    (step,) = await with_recorder(seed_context, work)
    assert (step.step_status, step.failure_code, step.raw_output_json, step.stage_name) == ("failed", "ai_unavailable", None, "synthesis")
    assert "secret-host-name" not in str(step.__dict__)


def test_failures_map_to_codes() -> None:
    assert failure_code_of(TokenBudgetExceededException("x")) == InvestigationAiCallFailure.TOKEN_BUDGET_EXCEEDED
    assert failure_code_of(RuntimeError("x")) == InvestigationAiCallFailure.FAILED


async def test_adjustments_and_the_hypothesis_link_attach_to_the_call_of_that_feature(seed_context) -> None:
    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_ai_call(a_call("hypothesis_application", raw_output={}))
        recorder.record_ai_call(a_call("hypothesis_dependencies", raw_output={}))
        recorder.add_adjustments("hypothesis_dependencies", [{"code": "invalid_citations_removed", "parameters": {"codes": ["E14"]}}])
        recorder.add_adjustments("hypothesis_dependencies", [{"code": "hypothesis_state_guarded", "parameters": {"guard": "support_not_in_evidence"}}])
        recorder.link_hypothesis("hypothesis_dependencies", "hypothesis-7")

    application_step, dependencies_step = await with_recorder(seed_context, work)
    assert application_step.adjustments_json is None and application_step.hypothesis_id is None
    assert [item["code"] for item in dependencies_step.adjustments_json] == ["invalid_citations_removed", "hypothesis_state_guarded"] and dependencies_step.hypothesis_id == "hypothesis-7"


async def test_a_recorder_that_breaks_stops_recording_and_never_raises(seed_context) -> None:
    async def work(recorder: InvestigationTraceRecorder) -> None:
        recorder.record_inputs({"ok": True})
        recorder.record_ai_call(None)  # type: ignore[arg-type]  # a bug in the recorder or its input
        assert recorder.is_recording is False
        recorder.record_decision(InvestigationDecisionKind.PRIORITY_SET, {"final": "P2"})  # ignored after the first error

    steps = await with_recorder(seed_context, work)
    assert [step.step_kind for step in steps] == ["inputs"]


async def test_a_failure_is_one_failed_outcome_numbered_after_the_committed_steps(seed_context) -> None:
    investigation_id = await new_investigation(seed_context)
    async with open_session() as session:
        investigation = await session.get(Investigation, investigation_id)
        first = InvestigationTraceRecorder(session, investigation, PiiMasker(), get_settings())
        first.record_inputs({"ok": True})
        first.record_decision(InvestigationDecisionKind.PRIORITY_SET, {"final": "P2"})
    async with open_session() as session:  # a later run of the same investigation: the in-memory counter starts again
        investigation = await session.get(Investigation, investigation_id)
        second = InvestigationTraceRecorder(session, investigation, PiiMasker(), get_settings())
        await second.record_failure(InvestigationStage.EVIDENCE, "corr-1")
    async with open_session() as session:
        steps = list((await session.scalars(select(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id).order_by(InvestigationTraceStep.sequence_number))).all())
    assert [step.sequence_number for step in steps] == [1, 2, 3]
    assert (steps[2].step_kind, steps[2].step_status, steps[2].details_json) == (InvestigationTraceStepKind.OUTCOME, InvestigationTraceStepStatus.FAILED, {"failedAfterStage": "evidence", "correlationId": "corr-1"})

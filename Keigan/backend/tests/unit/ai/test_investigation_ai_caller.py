"""keigan/ai/investigation_ai_caller.py: the call observer (spec 28, seam S1; AC-2)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from keigan.ai.investigation_ai_caller import InvestigationAiCall, InvestigationAiCaller
from keigan.ai.llm_gateway import LlmUsageContext, PromptSection
from keigan.exceptions.keigan_exceptions import LlmUnavailableException


class Answer(BaseModel):
    text: str


class ScriptedGateway:
    is_mock = False
    provider_name = "scripted"

    def __init__(self, result: Answer | None = None, error: Exception | None = None):
        self.result, self.error = result, error
        self.usage_contexts: list[LlmUsageContext] = []

    def model_name_for(self, tier: object) -> str:
        return "scripted-model"

    async def generate_structured(self, *, usage_context: LlmUsageContext, **_: object) -> Answer:
        self.usage_contexts.append(usage_context)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def caller_with(gateway: ScriptedGateway, calls: list[InvestigationAiCall] | None = None) -> InvestigationAiCaller:
    caller = InvestigationAiCaller("app", "Claims", "tier_1", "investigation-1", "someone", None, call_observer=calls.append if calls is not None else None)
    caller.gateway = gateway  # type: ignore[assignment]
    return caller


SECTIONS = [PromptSection("Incident", "Claims are slow [E1]", is_untrusted=True, source_label="incident")]


async def test_one_call_is_observed_with_the_step_id_the_usage_rows_carry() -> None:
    calls: list[InvestigationAiCall] = []
    gateway = ScriptedGateway(Answer(text="ok"))
    await caller_with(gateway, calls).ask("incident_triage", SECTIONS, Answer)
    (call,) = calls
    assert gateway.usage_contexts[0].trace_step_id == call.trace_step_id
    assert (call.feature_name, call.prompt_key, call.provider_name, call.model_name, call.model_tier) == ("incident_triage", "incident_triage", "scripted", "scripted-model", "fast")
    assert call.raw_output == {"text": "ok"} and call.failure is None and call.duration_milliseconds >= 0
    assert len(call.prompt_template_sha256) == 64 and len(call.system_prompt_sha256) == 64 and call.prompt_version
    assert call.prompt_sections[0].title == "Incident"


async def test_a_failed_call_is_observed_and_the_error_still_reaches_the_caller() -> None:
    calls: list[InvestigationAiCall] = []
    failure = LlmUnavailableException("model down")
    with pytest.raises(LlmUnavailableException):
        await caller_with(ScriptedGateway(error=failure), calls).ask("incident_triage", SECTIONS, Answer)
    (call,) = calls
    assert call.failure is failure and call.raw_output is None


async def test_each_call_gets_its_own_step_id() -> None:
    calls: list[InvestigationAiCall] = []
    caller = caller_with(ScriptedGateway(Answer(text="ok")), calls)
    await caller.ask("incident_triage", SECTIONS, Answer)
    await caller.ask("incident_triage", SECTIONS, Answer)
    assert calls[0].trace_step_id != calls[1].trace_step_id


async def test_without_an_observer_nothing_changes() -> None:
    assert (await caller_with(ScriptedGateway(Answer(text="ok"))).ask("incident_triage", SECTIONS, Answer)).text == "ok"


async def test_an_observer_that_raises_never_fails_the_call() -> None:
    caller = caller_with(ScriptedGateway(Answer(text="ok")))
    caller.call_observer = lambda call: (_ for _ in ()).throw(RuntimeError("recorder bug"))
    assert (await caller.ask("incident_triage", SECTIONS, Answer)).text == "ok"


async def test_an_offline_run_is_observed_with_its_estimated_tokens() -> None:
    from keigan.ai.investigation_mock_responses import OFFLINE_FACTORIES

    calls: list[InvestigationAiCall] = []
    caller = InvestigationAiCaller("app", "Claims", "tier_1", None, None, None, offline_ai=True, call_observer=calls.append)
    OFFLINE_FACTORIES["incident_triage"] = lambda schema, sections: Answer(text="offline")  # type: ignore[assignment]
    try:
        await caller.ask("incident_triage", SECTIONS, Answer)
    finally:
        import keigan.ai.investigation_mock_responses as responses

        responses.OFFLINE_FACTORIES.pop("incident_triage", None)
    (call,) = calls
    assert (call.provider_name, call.model_name) == ("offline", "offline-factory") and call.estimated_input_tokens and call.estimated_output_tokens

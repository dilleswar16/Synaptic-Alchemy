"""Records an investigation's decision trace as it runs (spec 28): one ordered step per input snapshot, AI call, evidence summary, decision and outcome.

The recorder adds rows to the session the investigation runner already commits after every stage, so the trace and the visible progress never disagree. It is observational:
every public method catches its own errors, logs them with the investigation id and, after the first, stops recording (the trace then reports itself incomplete); the
investigation itself is never affected. Steps hold ids, codes, numbers, hashes and catalogue names. The raw answer of an AI call is masked with the run's masker and cut.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.investigation_ai_caller import InvestigationAiCall
from keigan.ai.llm_gateway import PromptSection
from keigan.ai.prompt_safety import find_citation_codes
from keigan.config.settings import Settings
from keigan.entities.incident_entities import InvestigationTraceStep
from keigan.entities.status_values import (
    InvestigationAiCallFailure, InvestigationDecisionKind, InvestigationStage, InvestigationTraceStepKind, InvestigationTraceStepStatus,
)
from keigan.exceptions.keigan_exceptions import LlmRateLimitedException, LlmUnavailableException, TokenBudgetExceededException
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.time_utils import utc_now

logger = logging.getLogger(__name__)
TRUNCATED_OUTPUT_KEY = "truncated_output_text"  # the format Ask Keigan uses for a stored output that was cut
_STAGE_OF_FEATURE = {
    "incident_triage": InvestigationStage.TRIAGE, "evidence_query_planner": InvestigationStage.EVIDENCE, "rca_synthesis": InvestigationStage.SYNTHESIS,
    "blast_radius_narrative": InvestigationStage.SYNTHESIS, "incident_communications": InvestigationStage.COMMUNICATIONS,
}
_HYPOTHESIS_FEATURE_PREFIX = "hypothesis_"

Parameters, Result = ParamSpec("Parameters"), TypeVar("Result")


def failure_code_of(failure: Exception) -> InvestigationAiCallFailure:
    """The trace records why a call failed as a code; the exception's own text is never stored."""
    if isinstance(failure, TokenBudgetExceededException):
        return InvestigationAiCallFailure.TOKEN_BUDGET_EXCEEDED
    if isinstance(failure, LlmRateLimitedException):
        return InvestigationAiCallFailure.AI_RATE_LIMITED
    if isinstance(failure, LlmUnavailableException):
        return InvestigationAiCallFailure.AI_UNAVAILABLE
    return InvestigationAiCallFailure.AI_OUTPUT_INVALID if type(failure).__name__.endswith("ValidationException") else InvestigationAiCallFailure.FAILED


def section_manifest(sections: Sequence[PromptSection]) -> list[dict[str, Any]]:
    """Per section: what it was, how big, whether the gateway cut it, the SHA-256 of its content and the citation codes inside. Never the text."""
    manifest = []
    for section in sections:
        sent_characters = min(len(section.content), section.maximum_characters) if section.is_untrusted and section.maximum_characters else len(section.content)
        manifest.append({
            "title": section.title, "sourceLabel": section.source_label, "isUntrusted": section.is_untrusted, "isFlagged": section.is_flagged, "characterCount": len(section.content),
            "sentCharacterCount": sent_characters, "isTruncated": sent_characters < len(section.content), "sha256": hashlib.sha256(section.content.encode("utf-8")).hexdigest(),
            "citationCodes": sorted(find_citation_codes(section.content)),
        })
    return manifest


def _never_fail(method: Callable[Parameters, Result]) -> Callable[Parameters, Result | None]:
    """A recorder error is logged once and stops the recording; it never reaches the investigation (D-A3-5)."""
    @wraps(method)
    def guarded(*arguments: Parameters.args, **keyword_arguments: Parameters.kwargs) -> Result | None:
        recorder = arguments[0]
        if not recorder.is_recording:  # type: ignore[attr-defined]
            return None
        try:
            return method(*arguments, **keyword_arguments)
        except Exception:  # noqa: BLE001 - observational code must never fail what it observes
            logger.exception("Decision trace recording stopped for investigation %s", recorder.investigation_id)  # type: ignore[attr-defined]
            recorder.is_recording = False  # type: ignore[attr-defined]
            return None
    return guarded


class InvestigationTraceRecorder:
    def __init__(self, session: AsyncSession, investigation_id: str, masker: PiiMasker, settings: Settings):
        self.session = session
        self.investigation_id = investigation_id
        self.masker = masker
        self.maximum_raw_output_characters = settings.investigation_trace_raw_output_stored_characters
        self.is_recording = True
        self.stage: str = InvestigationStage.TRIAGE
        self._next_sequence_number = 1
        self._steps_by_feature: dict[str, InvestigationTraceStep] = {}
        self.prompt_versions: dict[str, str] = {}  # prompt key -> version of every prompt a call used (for the audit row)

    @property
    def step_count(self) -> int:
        return self._next_sequence_number - 1

    # ── Steps ──────────────────────────────────────────────────────────────────
    def _add(self, kind: InvestigationTraceStepKind, status: InvestigationTraceStepStatus = InvestigationTraceStepStatus.SUCCEEDED, **fields: Any) -> InvestigationTraceStep:
        stage = fields.pop("stage_name", self.stage)
        step = InvestigationTraceStep(
            investigation_id=self.investigation_id, sequence_number=self._next_sequence_number, stage_name=stage, step_kind=kind, step_status=status, **fields,
        )
        self._next_sequence_number += 1
        self.session.add(step)
        return step

    @_never_fail
    def record_inputs(self, details: dict[str, Any]) -> None:
        self._add(InvestigationTraceStepKind.INPUTS, stage_name=InvestigationStage.TRIAGE, completed_at=utc_now(), details_json=details)

    @_never_fail
    def record_decision(self, kind: InvestigationDecisionKind, details: dict[str, Any], status: InvestigationTraceStepStatus = InvestigationTraceStepStatus.SUCCEEDED) -> None:
        self._add(InvestigationTraceStepKind.DECISION, status, decision_kind=kind, completed_at=utc_now(), details_json=details)

    @_never_fail
    def record_evidence(self, details: dict[str, Any]) -> None:
        self._add(InvestigationTraceStepKind.EVIDENCE, stage_name=InvestigationStage.EVIDENCE, completed_at=utc_now(), details_json=details)

    @_never_fail
    def record_ai_call(self, call: InvestigationAiCall) -> None:
        """The observer the investigation's AI caller reports every call to."""
        stage = (InvestigationStage.HYPOTHESES if call.feature_name.startswith(_HYPOTHESIS_FEATURE_PREFIX) else _STAGE_OF_FEATURE.get(call.feature_name, self.stage))
        raw_text = json.dumps(call.raw_output, ensure_ascii=False, default=str) if call.raw_output is not None else None
        masked_text = self.masker.mask_text(raw_text) if raw_text is not None else None
        is_truncated = masked_text is not None and len(masked_text) > self.maximum_raw_output_characters
        stored_output: dict[str, Any] | None = None
        if masked_text is not None:
            stored_output = {TRUNCATED_OUTPUT_KEY: masked_text[: self.maximum_raw_output_characters]} if is_truncated else json.loads(masked_text)
        step = self._add(
            InvestigationTraceStepKind.AI_CALL, InvestigationTraceStepStatus.FAILED if call.failure else InvestigationTraceStepStatus.SUCCEEDED, stage_name=stage,
            trace_step_id=call.trace_step_id, started_at=call.started_at, completed_at=utc_now(), duration_milliseconds=call.duration_milliseconds, feature_name=call.feature_name,
            prompt_key=call.prompt_key, prompt_version=call.prompt_version, prompt_template_sha256=call.prompt_template_sha256, system_prompt_sha256=call.system_prompt_sha256,
            provider_name=call.provider_name, model_name=call.model_name, model_tier=call.model_tier, input_manifest_json=section_manifest(call.prompt_sections),
            estimated_input_token_count=call.estimated_input_tokens, estimated_output_token_count=call.estimated_output_tokens, raw_output_json=stored_output,
            raw_output_character_count=len(masked_text) if masked_text is not None else None, raw_output_is_truncated=is_truncated if masked_text is not None else None,
            raw_output_sha256=hashlib.sha256(masked_text.encode("utf-8")).hexdigest() if masked_text is not None else None,
            failure_code=failure_code_of(call.failure) if call.failure else None,
        )
        self._steps_by_feature[call.feature_name] = step
        self.prompt_versions[call.prompt_key] = call.prompt_version

    @_never_fail
    def add_adjustments(self, feature_name: str, adjustments: Sequence[dict[str, Any]]) -> None:
        """What Keigan's code changed in the model's answer for the call of ``feature_name`` (the latest one): codes and small parameters."""
        step = self._steps_by_feature.get(feature_name)
        if step is not None and adjustments:
            step.adjustments_json = [*(step.adjustments_json or []), *adjustments]

    @_never_fail
    def link_hypothesis(self, feature_name: str, hypothesis_id: str) -> None:
        step = self._steps_by_feature.get(feature_name)
        if step is not None:
            step.hypothesis_id = hypothesis_id

    @_never_fail
    def record_outcome(self, details: dict[str, Any], status: InvestigationTraceStepStatus = InvestigationTraceStepStatus.SUCCEEDED) -> None:
        self._add(InvestigationTraceStepKind.OUTCOME, status, stage_name=InvestigationStage.COMPLETED, completed_at=utc_now(), details_json=details)

    async def record_failure(self, failed_after_stage: str, correlation_id: str | None) -> None:
        """After the failed stage was rolled back: one failed outcome step, numbered after the steps that were committed (the in-memory counter may be ahead of them)."""
        if not self.is_recording:
            return
        try:
            committed_count = int(await self.session.scalar(select(func.count()).select_from(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == self.investigation_id)) or 0)
            self._next_sequence_number = committed_count + 1
            self.record_outcome({"failedAfterStage": failed_after_stage, "correlationId": correlation_id}, InvestigationTraceStepStatus.FAILED)
        except Exception:  # noqa: BLE001
            logger.exception("Could not record the failure of investigation %s in its trace", self.investigation_id)

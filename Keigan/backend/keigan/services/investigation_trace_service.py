"""Reads an investigation's decision trace for the API (spec 28).

Who may read what (D-A3-4): anyone who can read the investigation reads its trace (the people who must trust a conclusion are the whole team, not only whoever asked);
the raw answer of an AI call, which is the model's words before Keigan's checks and can hold commands and paths Keigan would have changed, is for the application's
admins and Keigan admins. Tokens come from the usage rows of each call's attempts; a call that wrote none (the mock or the offline model) shows the recorded estimate, marked.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.dtos.investigation_trace_dtos import (
    InvestigationTraceView, RawOutputView, TraceAdjustmentDto, TraceAiCallDto, TraceAttemptDto, TraceCallWithoutStepDto, TraceInputSectionDto, TraceModelDto, TracePromptDto,
    TraceStepDto, TraceTotalsDto,
)
from keigan.entities.incident_entities import Investigation, InvestigationTraceStep
from keigan.entities.platform_entities import LlmUsageRecord
from keigan.entities.status_values import InvestigationStatus, InvestigationTraceStepKind
from keigan.exceptions.keigan_exceptions import ForbiddenException, NotFoundException
from keigan.security.current_user import CurrentUser
from keigan.services.investigation_service import InvestigationService, outcome_of

RAW_OUTPUT_ADMIN_ONLY_MESSAGE = "Only application admins can see the raw AI answers of an investigation."
_STILL_RUNNING = (InvestigationStatus.QUEUED, InvestigationStatus.RUNNING)
_STATUS_FAILED_ATTEMPT = "failed"


class InvestigationTraceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.investigation_service = InvestigationService(session)

    async def get_trace(self, current_user: CurrentUser, investigation_id: str) -> InvestigationTraceView:
        investigation = await self.investigation_service.load_readable_investigation(current_user, investigation_id)
        steps = list((await self.session.scalars(select(InvestigationTraceStep).where(InvestigationTraceStep.investigation_id == investigation_id).order_by(InvestigationTraceStep.sequence_number))).all())
        usage_rows = list((await self.session.scalars(select(LlmUsageRecord).where(LlmUsageRecord.investigation_id == investigation_id).order_by(LlmUsageRecord.created_at))).all())
        attempts_by_step: dict[str, list[LlmUsageRecord]] = defaultdict(list)
        for row in usage_rows:
            if row.investigation_trace_step_id:
                attempts_by_step[row.investigation_trace_step_id].append(row)
        step_ids = {step.trace_step_id for step in steps}
        step_dtos = [self._step_dto(step, attempts_by_step.get(step.trace_step_id, [])) for step in steps]
        calls_without_step = [
            TraceCallWithoutStepDto(
                feature_name=row.feature_name, model_name=row.model_name, created_at=row.created_at, input_token_count=row.input_token_count, output_token_count=row.output_token_count,
                outcome_status=row.outcome_status,
            )
            for row in usage_rows if row.investigation_trace_step_id not in step_ids
        ]
        return InvestigationTraceView(
            investigation_id=investigation_id, is_recorded=bool(steps), is_complete=self._is_complete(investigation, steps), pipeline_version=self._pipeline_version(steps),
            status=investigation.investigation_status, outcome=outcome_of(investigation), totals=self._totals(step_dtos, calls_without_step, steps, investigation), models=self._models(step_dtos),
            prompts=self._prompts(steps), steps=step_dtos, calls_without_step=calls_without_step,
        )

    async def get_raw_output(self, current_user: CurrentUser, investigation_id: str, trace_step_id: str) -> RawOutputView:
        try:
            await self.investigation_service.load_readable_investigation(current_user, investigation_id, require_admin=True)
        except ForbiddenException as refusal:
            await self.investigation_service.load_readable_investigation(current_user, investigation_id)  # a person with no access at all gets the plain refusal
            raise ForbiddenException(RAW_OUTPUT_ADMIN_ONLY_MESSAGE) from refusal
        step = await self.session.get(InvestigationTraceStep, trace_step_id)
        if step is None or step.investigation_id != investigation_id or step.step_kind != InvestigationTraceStepKind.AI_CALL or step.raw_output_json is None:
            raise NotFoundException("That step has no stored raw answer.")
        return RawOutputView(
            raw_output=step.raw_output_json, character_count=step.raw_output_character_count or 0, is_truncated=bool(step.raw_output_is_truncated), sha256=step.raw_output_sha256 or "",
        )

    # ── Shaping ────────────────────────────────────────────────────────────────
    @staticmethod
    def _step_dto(step: InvestigationTraceStep, attempts: list[LlmUsageRecord]) -> TraceStepDto:
        ai_call = None
        if step.step_kind == InvestigationTraceStepKind.AI_CALL:
            has_usage_rows = bool(attempts)
            ai_call = TraceAiCallDto(
                feature_name=step.feature_name, prompt_key=step.prompt_key, prompt_version=step.prompt_version, prompt_template_sha256=step.prompt_template_sha256,
                system_prompt_sha256=step.system_prompt_sha256, provider_name=step.provider_name, model_name=step.model_name, model_tier=step.model_tier,
                input_token_count=sum(row.input_token_count for row in attempts) if has_usage_rows else step.estimated_input_token_count or 0,
                output_token_count=sum(row.output_token_count for row in attempts) if has_usage_rows else step.estimated_output_token_count or 0, token_counts_estimated=not has_usage_rows,
                attempts=[
                    TraceAttemptDto(outcome_status=row.outcome_status, latency_milliseconds=row.latency_milliseconds, input_token_count=row.input_token_count, output_token_count=row.output_token_count)
                    for row in attempts
                ],
                input_sections=[TraceInputSectionDto.model_validate(section) for section in step.input_manifest_json or []],
                adjustments=[TraceAdjustmentDto.model_validate(adjustment) for adjustment in step.adjustments_json or []],
                has_raw_output=step.raw_output_json is not None, raw_output_character_count=step.raw_output_character_count, raw_output_is_truncated=step.raw_output_is_truncated,
                failure_code=step.failure_code, hypothesis_id=step.hypothesis_id,
            )
        return TraceStepDto(
            trace_step_id=step.trace_step_id, sequence_number=step.sequence_number, stage_name=step.stage_name, step_kind=step.step_kind, step_status=step.step_status,
            decision_kind=step.decision_kind, started_at=step.started_at, completed_at=step.completed_at, duration_milliseconds=step.duration_milliseconds, ai_call=ai_call,
            details=step.details_json if step.step_kind != InvestigationTraceStepKind.AI_CALL else None,
        )

    @staticmethod
    def _is_complete(investigation: Investigation, steps: list[InvestigationTraceStep]) -> bool:
        """A finished investigation whose last step is its outcome; false while it runs and when recording stopped early (spec 28, 5.3)."""
        if investigation.investigation_status in _STILL_RUNNING:
            return False
        return bool(steps) and steps[-1].step_kind == InvestigationTraceStepKind.OUTCOME

    @staticmethod
    def _pipeline_version(steps: list[InvestigationTraceStep]) -> str | None:
        inputs = next((step for step in steps if step.step_kind == InvestigationTraceStepKind.INPUTS), None)
        return (inputs.details_json or {}).get("pipelineVersion") if inputs else None

    @staticmethod
    def _totals(
        step_dtos: list[TraceStepDto], calls_without_step: list[TraceCallWithoutStepDto], steps: list[InvestigationTraceStep], investigation: Investigation,
    ) -> TraceTotalsDto:
        ai_calls = [step.ai_call for step in step_dtos if step.ai_call]
        attempts = [attempt for call in ai_calls for attempt in call.attempts]
        input_tokens = sum(call.input_token_count for call in ai_calls) + sum(call.input_token_count for call in calls_without_step)
        output_tokens = sum(call.output_token_count for call in ai_calls) + sum(call.output_token_count for call in calls_without_step)
        started, ended = investigation.started_at, investigation.completed_at
        return TraceTotalsDto(
            input_token_count=input_tokens, output_token_count=output_tokens, token_counts_estimated=any(call.token_counts_estimated for call in ai_calls), ai_call_count=len(ai_calls),
            attempt_count=len(attempts), failed_attempt_count=sum(1 for attempt in attempts if attempt.outcome_status == _STATUS_FAILED_ATTEMPT),
            duration_milliseconds=int((ended - started).total_seconds() * 1000) if started and ended else None,
        )

    @staticmethod
    def _models(step_dtos: list[TraceStepDto]) -> list[TraceModelDto]:
        counts = Counter((call.provider_name, call.model_name, call.model_tier) for step in step_dtos if (call := step.ai_call))
        return [TraceModelDto(provider_name=provider, model_name=model, model_tier=tier, call_count=count) for (provider, model, tier), count in counts.items()]

    @staticmethod
    def _prompts(steps: list[InvestigationTraceStep]) -> list[TracePromptDto]:
        seen: dict[str, TracePromptDto] = {}
        for step in steps:
            if step.prompt_key and step.prompt_key not in seen:
                seen[step.prompt_key] = TracePromptDto(prompt_key=step.prompt_key, prompt_version=step.prompt_version, prompt_template_sha256=step.prompt_template_sha256)
        return list(seen.values())

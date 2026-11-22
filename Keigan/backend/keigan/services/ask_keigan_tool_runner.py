"""Runs the tool calls a model asked for, one at a time, and records each in the trace (spec 23, 4.5.3 and 4.8).

Every call gets its own database session and a copy of the person's user with no cached roles, so the person's access to the application is read from the
database again on every call: access removed between two calls of one answer is noticed. The registry does the shared work (binding, validation, the
read-only guard, masking, the model view); this class adds what only the engine knows: the citation number, the trace, the stop request and the access check.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import AgentToolRequest, LlmUsageContext
from keigan.ai.output_sanitizer import sanitize_ai_line
from keigan.ai.tool_registry import MAXIMUM_TOOL_NAME_CHARACTERS, ToolContext, ToolDefinition, ToolOutcome, ToolOutcomeCode, ToolPresentation, ToolRegistry, tool_label_in
from keigan.config.database_config import open_session
from keigan.entities.status_values import ChatRunStepStatus
from keigan.exceptions.keigan_exceptions import AccessLostMidRunException
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_cancellation import RunCancellationGuard
from keigan.services.ask_keigan_run_state import ExecutedToolCall
from keigan.services.ask_keigan_scopes import ScopeProfile, bound_argument_names
from keigan.services.ask_keigan_trace import SkipReason, StepHandle, ToolIdentity, ToolTarget, TraceRecorder
from keigan.services.authorization_service import AuthorizationService
from keigan.utils.pii_masker import PiiMasker

UNKNOWN_TOOL_SOURCE = "unknown"
APPLICATION_ARGUMENT = "application_code"
# Said to the model when a request is not run, so it can answer with what it has. The planner and the model read the first words (the status).
_SKIP_EXPLANATIONS = {
    SkipReason.TOOL_LIMIT_REACHED: "the limit of tool calls for this answer is used up; answer with what you have",
    SkipReason.PARALLEL_LIMIT_REACHED: "too many tools were requested at once; ask again in your next step if you still need it",
    SkipReason.TOKEN_BUDGET_REACHED: "the budget for this answer is used up; answer with what you have",
}


@dataclass(frozen=True)
class ToolCallResult:
    """``transcript_text`` is what the model is told about the request. ``executed`` is None for a request that was skipped (no citation code is used)."""

    transcript_text: str
    executed: ExecutedToolCall | None


class ToolCallRunner:
    def __init__(
        self, *, registry: ToolRegistry, recorder: TraceRecorder, profile: ScopeProfile, current_user: CurrentUser, masker: PiiMasker, usage_context: LlmUsageContext,
        guard: RunCancellationGuard, language_code: str | None,
    ):
        self._registry, self._recorder, self._profile, self._current_user = registry, recorder, profile, current_user
        self._masker, self._usage_context, self._guard, self._language_code = masker, usage_context, guard, language_code
        self._offered_tools = {tool.name: tool for tool in profile.offered_tools}

    async def run(self, request: AgentToolRequest, parent: StepHandle, citation_number: int) -> ToolCallResult:
        """Run one requested tool. Raises ``AnswerCancelledError`` when the person stops the answer meanwhile and ``AccessLostMidRunException`` when access was removed."""
        definition = self._offered_tools.get(request.tool_name)
        citation_code = f"T{citation_number}"
        effective_arguments = self._effective_arguments(definition, request)
        step = await self._recorder.start_tool_call(
            parent=parent, request_id=request.request_id, tool=self._identity(definition, request), citation_code=citation_code, requested_arguments=request.arguments or {},
            effective_arguments=effective_arguments, target=self._target(effective_arguments),
            bound_argument_names=self._bound_names(definition),
        )
        masked_value_count_before = self._masker.masked_value_count
        outcome = await self._outcome_of(request, definition, citation_code, step)
        await self._recorder.finish_tool_call(step, outcome, self._masker.masked_value_count - masked_value_count_before)
        if outcome.outcome_code == ToolOutcomeCode.ACCESS_DENIED:
            await self._raise_if_access_was_lost()
        label = tool_label_in(definition, self._language_code) if definition else self._shown_name(request)  # in the person's language: it is what the sources list and the summary show
        summary = getattr(outcome.output, "summary", None) if outcome.status is ChatRunStepStatus.SUCCEEDED else None  # every output model has a code-written summary (registry rule)
        return ToolCallResult(outcome.model_message, ExecutedToolCall(citation_code, step.run_step_id, request.tool_name, label, outcome.status, summary))

    async def skip(self, request: AgentToolRequest, parent: StepHandle, reason: SkipReason, outcome_message: str | None = None) -> ToolCallResult:
        definition = self._offered_tools.get(request.tool_name)
        effective_arguments = self._effective_arguments(definition, request)
        await self._recorder.record_skipped_tool_call(
            parent=parent, request_id=request.request_id, tool=self._identity(definition, request), requested_arguments=request.arguments or {}, target=self._target(effective_arguments),
            bound_argument_names=self._bound_names(definition), reason=reason, outcome_message=outcome_message,
        )
        return ToolCallResult(f"{self._shown_name(request)} {ChatRunStepStatus.SKIPPED.value} ({reason.value}): {_SKIP_EXPLANATIONS[reason]}", None)

    # ── Internals ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _outcome_of(self, request: AgentToolRequest, definition: ToolDefinition | None, citation_code: str, step: StepHandle) -> ToolOutcome:
        if request.arguments is None and definition is not None:
            return self._unreadable_arguments_outcome(definition, request.arguments_problem or "")
        # A fresh copy of the user without cached roles: the registry's reader check reads the person's access from the database again for this call.
        fresh_user = replace(self._current_user, application_roles_by_application_id=None)
        async with open_session() as session:
            authorization = AuthorizationService(session)

            async def report_progress(stage: str, detail: dict[str, Any]) -> None:
                await self._recorder.record_tool_progress(step, stage, detail)

            context = ToolContext(
                current_user=fresh_user, profile=self._profile, session=session, masker=self._masker, usage_context=self._usage_context, report_progress=report_progress,
                ensure_application_reader=lambda application_id: authorization.ensure_application_reader(fresh_user, application_id), citation_code=citation_code,
                language_code=self._language_code,
            )
            return await self._guard.run(self._registry.execute_by_name(request.tool_name, context, request.arguments or {}))

    def _unreadable_arguments_outcome(self, definition: ToolDefinition, problem: str) -> ToolOutcome:
        message = AskKeiganErrorCatalogue.describe("tool_failed_invalid_arguments", {"toolLabel": tool_label_in(definition, self._language_code), "fieldMessage": problem}, self._language_code).detail
        return ToolOutcome(
            status=ChatRunStepStatus.REFUSED, output=None, application_id=None, records=[], outcome_code=ToolOutcomeCode.INVALID_ARGUMENTS, outcome_message=message,
            model_message=f"{definition.name} {ChatRunStepStatus.REFUSED.value} ({ToolOutcomeCode.INVALID_ARGUMENTS}): {message}",
        )

    async def _raise_if_access_was_lost(self) -> None:
        """A refusal on grounds of access is only a refusal when the person never had access. When an application of the scope can no longer be read, the answer stops."""
        fresh_user = replace(self._current_user, application_roles_by_application_id=None)
        async with open_session() as session:
            readable_application_ids = await AuthorizationService(session).readable_application_ids(fresh_user)
        if any(application.id not in readable_application_ids for application in self._profile.readable_applications):
            raise AccessLostMidRunException("Access to an application of this answer was removed while the answer was running.")

    def _effective_arguments(self, definition: ToolDefinition | None, request: AgentToolRequest) -> dict[str, Any]:
        """What the model asked for with the scope's bound arguments applied (the registry applies the same rule before it validates)."""
        return {**(request.arguments or {}), **{name: self._profile.bound_arguments[name] for name in self._bound_names(definition)}}

    def _bound_names(self, definition: ToolDefinition | None) -> tuple[str, ...]:
        return bound_argument_names(definition, self._profile.bound_arguments) if definition else ()

    def _target(self, effective_arguments: Mapping[str, Any]) -> ToolTarget:
        """The application the call is about: the one it names, or the one the scope fixes (an evidence lookup names none, but the investigation belongs to one)."""
        application_code = effective_arguments.get(APPLICATION_ARGUMENT) or self._profile.bound_arguments.get(APPLICATION_ARGUMENT, "")
        application = self._profile.application_named(str(application_code))
        return ToolTarget(application.id, application.name) if application else ToolTarget(None, None)

    def _identity(self, definition: ToolDefinition | None, request: AgentToolRequest) -> ToolIdentity:
        if definition is not None:
            return ToolIdentity.of(definition)
        shown_name = self._shown_name(request)
        return ToolIdentity(name=shown_name, version=None, source=UNKNOWN_TOOL_SOURCE, label=shown_name, label_key=f"chat:tools.{shown_name}.label", presentation=ToolPresentation.RECORD)

    @staticmethod
    def _shown_name(request: AgentToolRequest) -> str:
        """A tool name the model made up is shown as one short plain line."""
        return sanitize_ai_line(request.tool_name, maximum_characters=MAXIMUM_TOOL_NAME_CHARACTERS)

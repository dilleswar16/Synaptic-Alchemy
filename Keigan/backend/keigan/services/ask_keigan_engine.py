"""Ask Keigan's engine: answers one question by letting a model call read-only tools, and leaves a trace a person can check (spec 23, sections 4.8 to 4.10).

``prepare`` is called first (before the run row exists): it refuses a model that cannot use tools and builds the prompt, the tool schemas and the
``RunSetup`` stored with the run. ``run`` then does the whole answer. It never raises for a failure of the answer: every failure is worded by
``AskKeiganErrorCatalogue``, stored on the run, published as ``answer.failed`` and returned in the outcome. While the model and the tools work, a heartbeat keeps
the run's progress fresh. Every end of the run is a conditional write: when someone else ended the run first (another process judged it silent, a shutdown), the
engine changes nothing, publishes nothing and says so in the outcome. The pieces are separate modules: the loop
(``ask_keigan_loop``), the tool calls (``ask_keigan_tool_runner``), the paragraph streamer, the follow-up splitter, the answer assembler, the limit summary
and the trace recorder.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from keigan.ai import ask_keigan_mock_planner  # noqa: F401 — importing it registers the offline planners the mock provider answers tool turns with
from keigan.ai.ask_keigan_answer_format import FixedAnswer, fixed_answer
from keigan.ai.ask_keigan_errors import INTERNAL_ERROR, AnswerFailure, AskKeiganErrorCatalogue
from keigan.ai.llm_gateway import LlmUsageContext
from keigan.ai.tool_registry import exhausted_budget_owner, tool_registry
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.entities.status_values import ChatAnswerRunStatus, ChatAnswerStopReason
from keigan.security.current_user import CurrentUser
from keigan.services.ask_keigan_answer_assembler import AssembledAnswer, assemble_answer, build_citation_targets
from keigan.services.ask_keigan_cancellation import AnswerCancelledError, CancellationFlag, RunCancellationGuard
from keigan.services.ask_keigan_heartbeat import RunHeartbeat
from keigan.services.ask_keigan_loop import AnswerLoop
from keigan.services.ask_keigan_prepared_run import AgentGateway, PreparedRun, prepare_run
from keigan.services.ask_keigan_scopes import ScopeProfile
from keigan.services.ask_keigan_tool_runner import ToolCallRunner
from keigan.services.ask_keigan_trace import RunCompletion, TraceRecorder
from keigan.services.ask_keigan_transcript import ConversationTurn, build_initial_transcript
from keigan.utils.pii_masker import PiiMasker
from keigan.utils.string_table import translate

logger = logging.getLogger(__name__)
_CANCELLED_ERROR_CODE = "cancelled"


class _Stage(StrEnum):
    """What the engine was doing when an unclassified failure happened; the name is a key of ``ask_keigan_answers.steps`` in the string tables."""

    MODEL_TURN = "model_turn"
    SAVING_ANSWER = "saving_answer"


@dataclass(frozen=True)
class AnswerRequest:
    """The question of one run. ``question_text`` and ``history`` are already masked with ``masker``, the one masker of the run (tool outputs are masked with it too)."""

    current_user: CurrentUser
    conversation_id: str
    question_text: str
    history: Sequence[ConversationTurn]
    masker: PiiMasker


@dataclass(frozen=True)
class AnswerOutcome:
    """How the run ended. ``was_ended_elsewhere``: another party had ended the run before this engine finished, so nothing was written (``status`` and ``stop_reason`` are what
    this engine reached, not what is stored)."""

    status: ChatAnswerRunStatus
    stop_reason: ChatAnswerStopReason
    error_code: str | None
    assistant_message_id: str | None
    was_ended_elsewhere: bool = False


@dataclass(frozen=True)
class _ComposedAnswer:
    answer: AssembledAnswer
    stop_reason: ChatAnswerStopReason


class AskKeiganEngine:
    def __init__(self, gateway: AgentGateway | None = None):
        self._gateway: AgentGateway = gateway or application_context.llm_gateway()

    def prepare(self, profile: ScopeProfile, language_code: str | None = None) -> PreparedRun:
        """Raises ``AgentToolsUnsupportedException`` (model cannot use tools) or ``LlmRequestRejectedException`` (prompt cannot fit) before any run exists."""
        return prepare_run(gateway=self._gateway, prompt_library=application_context.prompt_library(), registry=tool_registry, profile=profile, language_code=language_code)

    async def run(self, prepared: PreparedRun, request: AnswerRequest, recorder: TraceRecorder, cancellation_flag: CancellationFlag) -> AnswerOutcome:
        """Answer the question of ``request``. ``recorder`` belongs to the already stored ``running`` run; the engine closes its event channel when the run ends."""
        language_code = request.current_user.preferred_locale
        stage = _Stage.MODEL_TURN
        try:
            profile = prepared.profile
            await recorder.record_start(scope=profile.scope, offered_tools=profile.offered_tools, maximum_tool_calls=profile.maximum_tool_calls)
            heartbeat = RunHeartbeat(recorder.touch_progress, get_settings().ask_keigan_progress_heartbeat_seconds, recorder.answer_run_id)
            async with heartbeat.running():  # it stops before the run is ended below, so no beat can race the end
                composed = await self._compose_answer(prepared, request, recorder, cancellation_flag, language_code)
            stage = _Stage.SAVING_ANSWER
            assistant_message_id = await recorder.complete_run(RunCompletion(
                markdown=composed.answer.markdown, follow_ups=composed.answer.follow_ups, citations=composed.answer.citations, is_unverified=composed.answer.is_unverified,
                is_refusal=composed.answer.is_refusal, stop_reason=composed.stop_reason,
            ))
            return AnswerOutcome(ChatAnswerRunStatus.COMPLETED, composed.stop_reason, None, assistant_message_id, was_ended_elsewhere=assistant_message_id is None)
        except AnswerCancelledError:
            was_ended_here = await recorder.cancel_run(AskKeiganErrorCatalogue.describe(_CANCELLED_ERROR_CODE, language_code=language_code))
            return AnswerOutcome(ChatAnswerRunStatus.CANCELLED, ChatAnswerStopReason.CANCELLED_BY_USER, _CANCELLED_ERROR_CODE, None, was_ended_elsewhere=not was_ended_here)
        except Exception as failure:  # noqa: BLE001 — every failure of the answer is classified, stored and published; nothing is swallowed
            description = self._describe_failure(failure, prepared, stage, recorder.answer_run_id, language_code)
            was_ended_here = await recorder.fail_run(description)
            return AnswerOutcome(ChatAnswerRunStatus.FAILED, ChatAnswerStopReason.FAILED, description.error_code, None, was_ended_elsewhere=not was_ended_here)
        finally:
            recorder.close_events()

    async def _compose_answer(
        self, prepared: PreparedRun, request: AnswerRequest, recorder: TraceRecorder, cancellation_flag: CancellationFlag, language_code: str | None,
    ) -> _ComposedAnswer:
        profile = prepared.profile
        if not profile.readable_applications:  # nothing to read: the fixed answer, and the model is never called
            no_access_answer = assemble_answer(fixed_answer(FixedAnswer.NO_ACCESS, language_code), {}, tool_call_count=0, follow_up_limit=0)
            return _ComposedAnswer(no_access_answer, ChatAnswerStopReason.ANSWERED)
        guard = RunCancellationGuard(cancellation_flag, recorder.is_cancel_requested)
        usage_context = LlmUsageContext(
            application_id=profile.budget_application_id, investigation_id=profile.investigation_id, conversation_id=request.conversation_id,
            requested_by_user_principal_name=request.current_user.user_principal_name,
        )
        tool_runner = ToolCallRunner(
            registry=tool_registry, recorder=recorder, profile=profile, current_user=request.current_user, masker=request.masker, usage_context=usage_context, guard=guard,
            language_code=language_code,
        )
        loop = AnswerLoop(gateway=self._gateway, prepared=prepared, recorder=recorder, tool_runner=tool_runner, guard=guard, usage_context=usage_context, language_code=language_code)
        loop_outcome = await loop.run(build_initial_transcript(profile, request.masker, request.history, request.question_text))
        citation_targets = build_citation_targets(profile.reference_citations, profile.accepted_citation_prefixes, loop_outcome.executed_calls)
        answer = assemble_answer(
            loop_outcome.answer_text, citation_targets, tool_call_count=len(loop_outcome.executed_calls), follow_up_limit=get_settings().ask_keigan_follow_up_question_limit,
        )
        return _ComposedAnswer(answer, loop_outcome.stop_reason)

    @staticmethod
    def _describe_failure(failure: Exception, prepared: PreparedRun, stage: _Stage, answer_run_id: str, language_code: str | None) -> AnswerFailure:
        step_description = translate(language_code, f"ask_keigan_answers.steps.{stage}")
        description = AskKeiganErrorCatalogue.describe_exception(
            failure, {
                "modelTier": prepared.model_tier.value, "seconds": get_settings().llm_request_timeout_seconds, "stepDescription": step_description,
                "budgetOwner": exhausted_budget_owner(failure, prepared.profile.readable_applications),
            }, language_code,
        )
        if description.error_code == INTERNAL_ERROR:
            logger.error("Ask Keigan run %s failed unexpectedly while %s (%s)", answer_run_id, step_description, type(failure).__name__, exc_info=failure)
        return description

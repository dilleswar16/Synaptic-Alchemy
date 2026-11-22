"""Ask Keigan answers as a service: start one, follow it, read its trace, stop it (spec 23, 4.4.1 and 7.5).

``start`` does everything that must be right before the answer begins, in the request session: who may ask (the conversation's owner, who must still be able to read
the investigation), the rate limit, a repeated request, one answer at a time per conversation, the scope profile (the scope of the answer is the scope of its conversation: an
investigation chat gets the investigation profile, the Keigan AI chat the global one) and the model's ability to use tools. It then begins the
trace (the masked question and the run row are one transaction) and hands the answer to a detached task (it outlives the request); the request only reads the task's
event channel. Everything the task does afterwards uses its own short sessions. A run is ended by the engine, by a stop request, or (when its process is gone) by
``RunInterruption``.

The checks of ``start`` are the fast path: with several processes only the database can decide a race, so a unique ``clientRequestId`` and a unique running run per
conversation are enforced by it, and a refused run is explained afterwards as ``duplicate_request`` or ``answer_in_progress``.

Who may read what: the snapshot and the output of a step show an answer, so they need the same access as reading the conversation (``ChatService.open_conversation``:
the owner who can still read the investigation's application) and, besides, that the person can still read every application the answer used (``AnswerAccess``).
Stopping and deleting need ownership only: they reveal nothing and end work the person started.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from keigan.ai.ask_keigan_errors import AskKeiganErrorCatalogue
from keigan.config import application_context
from keigan.config.settings import get_settings
from keigan.dtos.ask_keigan_dtos import AnswerRequest, AnswerRunView, CancelAnswerResponse, StepOutputView
from keigan.entities.base_entity import new_identifier
from keigan.entities.incident_entities import ChatAnswerRun, ChatRunStep, Conversation
from keigan.entities.status_values import ChatAnswerRunStatus, ChatRunStepKind, ConversationScope, MessageAuthorRole
from keigan.exceptions.keigan_exceptions import (
    AnswerInProgressException, AnswerNotRunningException, BusinessValidationException, DuplicateRequestException, ForbiddenException, NotFoundException, RateLimitedException,
)
from keigan.security.current_user import CurrentUser
from keigan.security.security_middleware import rate_limiter
from keigan.services.ask_keigan_answer_access import AnswerAccess
from keigan.services.ask_keigan_cancellation import CancellationFlag
from keigan.services.ask_keigan_engine import AnswerOutcome, AnswerRequest as EngineAnswerRequest, AskKeiganEngine
from keigan.services.ask_keigan_events import RunEventChannel
from keigan.services.ask_keigan_interruption import RunInterruption
from keigan.services.ask_keigan_prepared_run import PreparedRun
from keigan.services.ask_keigan_run_registry import AnswerRunRegistry, ConversationBusyError, LiveAnswerRun
from keigan.services.ask_keigan_run_snapshot import AnswerRunSnapshotBuilder
from keigan.services.ask_keigan_scopes import ScopeProfile, build_global_profile, build_investigation_profile
from keigan.services.ask_keigan_stream import event_frames
from keigan.services.ask_keigan_trace import QuestionToStore, RunRegistration, TraceRecorder
from keigan.services.ask_keigan_transcript import ConversationTurn
from keigan.services.authorization_service import AuthorizationService
from keigan.services.chat_service import ChatService
from keigan.utils.pii_masker import PiiMasker

logger = logging.getLogger(__name__)
CONVERSATION_NOT_ANSWERABLE_MESSAGE = "This conversation is neither a Keigan AI chat nor an investigation chat with an investigation, so Keigan cannot answer in it."
STEP_REDACTED_MESSAGE = "You no longer have access to the application this step read."
_ASSISTANT_HISTORY_ROLE = "assistant"
_USER_HISTORY_ROLE = "user"


@dataclass(frozen=True)
class StartedAnswer:
    """What ``start`` hands the request: the run, and the channel its events arrive on (read it with ``AskKeiganService.stream``)."""

    answer_run_id: str
    channel: RunEventChannel


class AskKeiganService:
    def __init__(self, session: AsyncSession, registry: AnswerRunRegistry | None = None, engine: AskKeiganEngine | None = None):
        self.session = session
        self.settings = get_settings()
        self.registry = registry or application_context.answer_run_registry()
        self._engine = engine
        self.chat_service = ChatService(session)
        self.answer_access = AnswerAccess(session)
        self.interruption = RunInterruption(self.registry)

    # ── Starting an answer ────────────────────────────────────────────────────────────────────────────────────────────────────
    async def start(self, current_user: CurrentUser, conversation_id: str, request: AnswerRequest) -> StartedAnswer:
        """Raises ``NotFoundException``/``ForbiddenException`` (not the owner, or access lost), ``DuplicateRequestException`` (same ``clientRequestId``),
        ``AnswerInProgressException``, ``RateLimitedException``, and the model errors of ``AskKeiganEngine.prepare``: all before anything is stored or any model is called."""
        language_code = current_user.preferred_locale
        conversation = await self.chat_service.open_conversation(current_user, conversation_id)
        await self._ensure_not_a_repeat(conversation_id, str(request.client_request_id), language_code)
        answer_run_id = new_identifier()
        live_run = LiveAnswerRun(answer_run_id, conversation_id, RunEventChannel(answer_run_id), CancellationFlag())
        engine = self._engine or AskKeiganEngine()
        self._register(live_run, language_code)
        try:
            await self._ensure_no_other_pod_is_answering(conversation_id, language_code)
            self._check_rate_limit(current_user, language_code)
            engine_user = replace(current_user, application_roles_by_application_id=None)  # the answer outlives this request: it must not share the request's cached roles
            profile = await self._build_profile(engine_user, conversation)
            prepared = engine.prepare(profile, language_code)
            masker = PiiMasker()
            history = await self._masked_history(current_user, conversation_id, masker)
            masked_question = masker.mask_text(request.message_text)
            recorder = await self._begin_run(
                RunRegistration(
                    answer_run_id=live_run.answer_run_id, conversation_id=conversation_id, question=QuestionToStore(masked_question, current_user.display_name, current_user.user_principal_name),
                    client_request_id=str(request.client_request_id), conversation_scope=profile.conversation_scope, investigation_id=profile.investigation_id,
                    requested_by_user_principal_name=current_user.user_principal_name, scope_snapshot=profile.snapshot(), setup=prepared.setup,
                ),
                live_run.channel, masker, language_code,
            )
            engine_request = EngineAnswerRequest(engine_user, conversation_id, masked_question, tuple(history), masker)
            live_run.task = asyncio.create_task(_answer_in_background(engine, prepared, engine_request, recorder, live_run, self.registry))
            live_run.task.add_done_callback(_log_unexpected_failure)
        except BaseException:
            self.registry.release(live_run.answer_run_id)
            raise
        return StartedAnswer(live_run.answer_run_id, live_run.channel)

    @staticmethod
    def stream(channel: RunEventChannel) -> AsyncIterator[str]:
        """The server-sent frames of a started answer. Reading them does not keep the answer alive: it runs to its end whatever the reader does."""
        return event_frames(channel, get_settings().ask_keigan_heartbeat_seconds)

    # ── Reading and stopping ──────────────────────────────────────────────────────────────────────────────────────────────────
    async def snapshot(self, current_user: CurrentUser, answer_run_id: str) -> AnswerRunView:
        """The stored trace of a run, for its owner while they may still read the conversation (``ForbiddenException`` otherwise: the answer, the notes and the citations are
        withheld with everything else). Works for a running run too; a run nothing is working on any more is ended as interrupted first."""
        run = await self._readable_run(current_user, answer_run_id)
        return await AnswerRunSnapshotBuilder(self.session, self.registry).build(run, current_user)

    async def step_output(self, current_user: CurrentUser, answer_run_id: str, run_step_id: str) -> StepOutputView:
        run = await self._readable_run(current_user, answer_run_id)
        step = await self.session.get(ChatRunStep, run_step_id)
        if step is None or step.answer_run_id != run.answer_run_id or step.step_kind != ChatRunStepKind.TOOL_CALL:
            raise NotFoundException("That step has no stored output.")
        if step.application_id and step.application_id not in await AuthorizationService(self.session).readable_application_ids(current_user):
            raise ForbiddenException(STEP_REDACTED_MESSAGE)
        return StepOutputView(
            run_step_id=step.run_step_id, output=step.output_json, output_character_count=step.output_character_count or 0, output_is_truncated=bool(step.output_is_truncated),
            model_view_text=step.model_view_text or "", model_view_sha256=step.model_view_sha256 or "",
        )

    async def cancel(self, current_user: CurrentUser, answer_run_id: str) -> CancelAnswerResponse:
        """Ask a running answer to stop: the request is stored (committed) for a run in another pod, then the flag is set for a run in this process. Asking again changes
        nothing. The owner may stop their own answer even after losing access to its application (the answer reads data they may no longer see; the reply shows nothing)."""
        run = await self._owned_run(current_user, answer_run_id)
        if run.run_status != ChatAnswerRunStatus.RUNNING or not await self._request_stop(answer_run_id):
            raise self._not_running(answer_run_id, current_user.preferred_locale)
        return CancelAnswerResponse(answer_run_id=answer_run_id, cancel_requested=True)

    async def delete_conversation(self, current_user: CurrentUser, conversation_id: str) -> None:
        """Delete a conversation of the caller. Its running answer is stopped first and has ended before any row is removed, so no answer writes into a conversation that is gone.
        An answer of another process is asked to stop (its next step sees the request) and the deletion is refused with ``AnswerInProgressException``: delete again a moment later."""
        language_code = current_user.preferred_locale
        await self.chat_service.owned_conversation(current_user, conversation_id)
        await self._stop_running_answers_of(conversation_id, language_code)
        await self.session.commit()  # ends the read transaction: the answers that just ended committed after it began
        await self.chat_service.delete_conversation(current_user, conversation_id)

    # ── Internals ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
    async def _owned_run(self, current_user: CurrentUser, answer_run_id: str) -> ChatAnswerRun:
        run = await self.session.get(ChatAnswerRun, answer_run_id)
        if run is None:
            raise NotFoundException("That answer does not exist.")
        await self.chat_service.owned_conversation(current_user, run.conversation_id)  # only the owner of the conversation reviews its trace
        if await self.interruption.interrupt_if_stale(run):
            await self.session.refresh(run)
        return run

    async def _readable_run(self, current_user: CurrentUser, answer_run_id: str) -> ChatAnswerRun:
        """The run of the owner who may still read its conversation (the rule of ``ChatService.open_conversation``, not a copy of it) and every application the answer used."""
        run = await self._owned_run(current_user, answer_run_id)
        await self.chat_service.open_conversation(current_user, run.conversation_id)
        await self.answer_access.ensure_run_readable(current_user, run)
        return run

    async def _request_stop(self, answer_run_id: str) -> bool:
        """Store the stop request (its own committed write), then set the in-process flag, so the engine never ends the run while the request is still an open transaction
        of the request. False when the run was no longer running."""
        if not await TraceRecorder.store_cancel_request(answer_run_id):
            return False
        self.registry.request_cancellation(answer_run_id)
        return True

    @staticmethod
    def _not_running(answer_run_id: str, language_code: str | None) -> AnswerNotRunningException:
        return AnswerNotRunningException(AskKeiganErrorCatalogue.describe("answer_not_running", language_code=language_code).detail, answer_run_id=answer_run_id)

    async def _stop_running_answers_of(self, conversation_id: str, language_code: str | None) -> None:
        running_runs = (await self.session.scalars(select(ChatAnswerRun).where(ChatAnswerRun.conversation_id == conversation_id, ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING))).all()
        for running_run in running_runs:
            live_run = self.registry.get(running_run.answer_run_id)
            if live_run is None:
                if not await self.interruption.interrupt_if_stale(running_run):  # another pod works on it (or it just ended)
                    await TraceRecorder.store_cancel_request(running_run.answer_run_id)
                    raise self._in_progress(running_run.answer_run_id, language_code)
            elif not await self._stopped_within_grace(live_run):
                raise self._in_progress(running_run.answer_run_id, language_code)

    async def _stopped_within_grace(self, live_run: LiveAnswerRun) -> bool:
        """Stop the answer of this process and wait for it to end (the engine ends a stopped run at once, even in the middle of a model call or a tool call)."""
        await self._request_stop(live_run.answer_run_id)
        if live_run.task is None:
            return False
        finished_tasks, _ = await asyncio.wait({live_run.task}, timeout=self.settings.ask_keigan_shutdown_grace_seconds)
        return bool(finished_tasks)

    @staticmethod
    def _in_progress(answer_run_id: str, language_code: str | None) -> AnswerInProgressException:
        return AnswerInProgressException(AskKeiganErrorCatalogue.describe("answer_in_progress", language_code=language_code).detail, answer_run_id=answer_run_id)

    async def _ensure_not_a_repeat(self, conversation_id: str, client_request_id: str, language_code: str | None) -> None:
        existing_run_id = await self.session.scalar(select(ChatAnswerRun.answer_run_id).where(ChatAnswerRun.conversation_id == conversation_id, ChatAnswerRun.client_request_id == client_request_id))
        if existing_run_id:
            raise DuplicateRequestException(AskKeiganErrorCatalogue.describe("duplicate_request", language_code=language_code).detail, answer_run_id=existing_run_id)

    def _register(self, live_run: LiveAnswerRun, language_code: str | None) -> None:
        try:
            self.registry.register(live_run)
        except ConversationBusyError as busy:
            raise self._in_progress(busy.running_answer_run_id, language_code) from busy

    async def _begin_run(self, registration: RunRegistration, channel: RunEventChannel, masker: PiiMasker, language_code: str | None) -> TraceRecorder:
        """Begin the trace. The database has the last word on a race that the checks above could not see (another pod wrote between this pod's check and its write): it refuses
        the run, and the refusal is explained by reading again, as ``duplicate_request`` (the same ``clientRequestId``) or ``answer_in_progress`` (a running run in the conversation)."""
        try:
            return await TraceRecorder.begin(registration, channel, masker)
        except IntegrityError:
            await self.session.rollback()  # this session's snapshot is older than the winner's commit
            await self._ensure_not_a_repeat(registration.conversation_id, registration.client_request_id, language_code)
            await self._ensure_no_other_pod_is_answering(registration.conversation_id, language_code)
            raise

    async def _ensure_no_other_pod_is_answering(self, conversation_id: str, language_code: str | None) -> None:
        """This process knows its own runs (the registry); a ``running`` row that is not one of them belongs to another pod, unless it went silent (then it is ended)."""
        running_runs = (await self.session.scalars(select(ChatAnswerRun).where(ChatAnswerRun.conversation_id == conversation_id, ChatAnswerRun.run_status == ChatAnswerRunStatus.RUNNING))).all()
        for running_run in running_runs:
            if not await self.interruption.interrupt_if_stale(running_run):
                raise self._in_progress(running_run.answer_run_id, language_code)

    def _check_rate_limit(self, current_user: CurrentUser, language_code: str | None) -> None:
        try:
            rate_limiter.check(f"chat:{current_user.user_principal_name}", self.settings.chat_rate_limit_per_minute)  # the same budget as the other chat endpoints
        except RateLimitedException as limited:
            raise RateLimitedException(AskKeiganErrorCatalogue.describe("rate_limited", language_code=language_code).detail) from limited

    async def _build_profile(self, current_user: CurrentUser, conversation: Conversation) -> ScopeProfile:
        """The scope of the answer is the scope of its conversation, and nothing else decides it."""
        if conversation.conversation_scope == ConversationScope.KEIGAN_AI_CHAT:
            return await build_global_profile(self.session, current_user, conversation.application_ids)
        if conversation.conversation_scope == ConversationScope.INVESTIGATION and conversation.investigation_id is not None:
            return await build_investigation_profile(self.session, current_user, conversation.investigation_id)
        raise BusinessValidationException(CONVERSATION_NOT_ANSWERABLE_MESSAGE)

    async def _masked_history(self, current_user: CurrentUser, conversation_id: str, masker: PiiMasker) -> list[ConversationTurn]:
        """The earlier exchange for the model, without the answers the person may no longer see: what they may not read must not come back through the next answer."""
        messages = await self.chat_service.conversation_messages(conversation_id)
        withheld = await self.answer_access.withheld_answers(current_user, conversation_id, messages)
        return [
            ConversationTurn(_USER_HISTORY_ROLE if message.author_role == MessageAuthorRole.USER else _ASSISTANT_HISTORY_ROLE, masker.mask_text(message.message_text))
            for message in messages if message.message_id not in withheld
        ]


async def _answer_in_background(engine: AskKeiganEngine, prepared: PreparedRun, request: EngineAnswerRequest, recorder: TraceRecorder, live_run: LiveAnswerRun, registry: AnswerRunRegistry) -> AnswerOutcome:
    """The detached task of one answer: it ends when the engine does, whatever happened to the request that started it, and then frees the conversation."""
    try:
        return await engine.run(prepared, request, recorder, live_run.cancellation_flag)
    finally:
        registry.release(live_run.answer_run_id)


def _log_unexpected_failure(task: asyncio.Task[AnswerOutcome]) -> None:
    """The engine reports every failure of an answer itself; an exception that still escapes (the database was unreachable while ending the run) is logged here. A run that
    is still marked running afterwards is ended as interrupted when it is next read."""
    if not task.cancelled() and task.exception() is not None:
        logger.error("An Ask Keigan answer task ended with an unexpected error; if its run is still marked running, it is ended as interrupted when next read.", exc_info=task.exception())

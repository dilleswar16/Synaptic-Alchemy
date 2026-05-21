"""
CorvinBot — Fully agentic Teams ChatOps bot.

Every @mention is routed to the Corvin Command Center agentic engine.
Fast-path commands (investigate, approve, reject, execute, help) are still
handled explicitly so they get an immediate structured ack.  All other text
— questions, conversational requests, status asks — goes straight to the
agentic engine which decides what tools to call.

Per-conversation session tracking
----------------------------------
Each Teams conversation (conversation.id) maps to a Corvin session stored in
the DB.  The mapping is cached in _sessions on this instance.  On restart the
map is empty but history is preserved in DB — the bot creates a new session
for the conversation on the next message.

Teams 15-second timeout
-----------------------
All slow operations (investigation, agentic engine) are fire-and-forget:
1. An immediate ack is sent ("Thinking…" / "Investigating…")
2. The engine runs as a background asyncio.Task
3. The result is posted back via adapter.continue_conversation or the
   outbound Teams webhook when no adapter is available.

Testing
-------
CorvinBot accepts injectable *engine*, *teams_adapter*, *adapter*, and *app_id*
constructor args.  Unit tests pass fakes; no real Azure / Teams endpoints
are contacted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from botbuilder.core import ActivityHandler, BotFrameworkAdapter, TurnContext

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, TriggerSource
from corvin.delivery.rca_notification import send_rca_email_if_enabled
from corvin.delivery.teams_adapter import TeamsAdapter
from corvin.execution.execution_service import ExecutionService
from corvin.investigation.engine import InvestigationEngine
from corvin.storage.repository import InvestigationRepository

_log = logging.getLogger(__name__)


# ── Mention-tag stripping helpers ─────────────────────────────────────────────

_AT_TAG_RE = re.compile(r"<at[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_mention_tags(text: str) -> str:
    """Remove Teams @mention HTML tags from *text* and normalise whitespace.

    Teams wraps @mentions in ``<at>DisplayName</at>`` elements.  This function
    strips those elements (and any residual HTML tags), then collapses
    whitespace so the result is a clean plain-text command string.

    Examples
    --------
    >>> _strip_mention_tags("<at>Corvin</at> investigate order-service production")
    'investigate order-service production'
    >>> _strip_mention_tags("investigate order-service")
    'investigate order-service'
    """
    text = _AT_TAG_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return " ".join(text.split())  # collapse extra whitespace


# ── Parsed command ─────────────────────────────────────────────────────────────


class _ParsedCommand:
    """Lightweight struct for a parsed Teams message command."""

    __slots__ = ("command", "args", "raw")

    def __init__(self, command: str, args: list[str], raw: str) -> None:
        self.command = command
        self.args = args
        self.raw = raw


def _parse_command(text: str) -> _ParsedCommand | None:
    """Parse *text* into a ``_ParsedCommand``.

    Strips mention tags, lowercases, and splits on whitespace.
    Returns ``None`` when *text* is blank after stripping.
    """
    clean = _strip_mention_tags(text).strip()
    if not clean:
        return None
    parts = clean.lower().split()
    return _ParsedCommand(command=parts[0], args=parts[1:], raw=clean)


# ── Bot ───────────────────────────────────────────────────────────────────────


class CorvinBot(ActivityHandler):
    """
    Teams bot handler for Corvin.

    Parameters
    ----------
    engine:
        Investigation engine to run.  Defaults to ``InvestigationEngine()``.
    teams_adapter:
        Outbound Teams adapter for posting result cards.  Defaults to
        ``TeamsAdapter()``.

    Notes
    -----
    *engine* and *teams_adapter* are injected in tests so that no real Azure
    endpoints are contacted.

    The ``_last_investigation_task`` attribute is set by ``_handle_investigate``
    each time an investigation is started.  Tests can ``await`` it to verify
    the full background flow without polling or sleeping.
    """

    def __init__(
        self,
        engine: InvestigationEngine | None = None,
        teams_adapter: TeamsAdapter | None = None,
        repository: InvestigationRepository | None = None,
        execution_service: ExecutionService | None = None,
        adapter: BotFrameworkAdapter | None = None,
        app_id: str = "",
    ) -> None:
        super().__init__()
        self._engine: InvestigationEngine = (
            engine if engine is not None else InvestigationEngine()
        )
        self._teams: TeamsAdapter = (
            teams_adapter if teams_adapter is not None else TeamsAdapter()
        )
        self._repository: InvestigationRepository = (
            repository if repository is not None else InvestigationRepository()
        )
        self._execution: ExecutionService = (
            execution_service if execution_service is not None else ExecutionService()
        )
        # Bot Framework adapter + app ID — used for proactive continue_conversation replies.
        self._adapter: BotFrameworkAdapter | None = adapter
        self._app_id: str = app_id
        # Maps Teams conversation.id → Corvin session_id (in-memory cache).
        self._sessions: dict[str, str] = {}
        # Set by _handle_investigate; exposed for test introspection only.
        self._last_investigation_task: asyncio.Task[None] | None = None
        # Set by _handle_agentic_chat; exposed for test introspection only.
        self._last_agentic_task: asyncio.Task[None] | None = None

    # ── ActivityHandler override ──────────────────────────────────────────────

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Dispatch an inbound Teams message to the appropriate handler."""
        text = (turn_context.activity.text or "").strip()
        parsed = _parse_command(text)

        if parsed is None:
            await turn_context.send_activity(
                "Hi! I'm Corvin. Try: `investigate <service> <environment>` or `help`."
            )
            return

        if parsed.command == "investigate":
            await self._handle_investigate(turn_context, parsed.args)
        elif parsed.command == "approve":
            await self._handle_approval(turn_context, parsed.args, ApprovalStatus.APPROVED)
        elif parsed.command == "reject":
            await self._handle_approval(turn_context, parsed.args, ApprovalStatus.REJECTED)
        elif parsed.command == "execute":
            await self._handle_execute(turn_context, parsed.args)
        elif parsed.command == "help":
            await self._handle_help(turn_context)
        else:
            # Route everything else to the agentic engine — the LLM decides intent.
            await self._handle_agentic_chat(turn_context, parsed.raw)

    # ── Command handlers ──────────────────────────────────────────────────────

    async def _handle_investigate(
        self, turn_context: TurnContext, args: list[str]
    ) -> None:
        """Send an acknowledgement then fire the investigation as a background task.

        Teams imposes a ~15-second connection timeout on inbound bot messages.
        Sending the ack immediately and running the investigation asynchronously
        prevents the connection from being dropped before the engine completes.
        """
        if not args:
            await turn_context.send_activity(
                "Usage: `investigate <service_name> [environment]`\n"
                "Example: `investigate order-service production`"
            )
            return

        service_name = args[0]
        environment = args[1] if len(args) > 1 else "production"

        await turn_context.send_activity(
            f"🔍 Investigating **{service_name}** in **{environment}**... "
            "I'll post the results to this channel shortly."
        )

        # Fire-and-forget: create a background task so the HTTP response to Teams
        # is returned before the (potentially slow) engine run completes.
        self._last_investigation_task = asyncio.create_task(
            self._run_investigation_async(service_name, environment)
        )

    async def _handle_help(self, turn_context: TurnContext) -> None:
        """Reply with the command reference."""
        await turn_context.send_activity(
            "**Corvin — Your AI SRE Co-Pilot** 🤖\n\n"
            "Just talk to me naturally — I understand anything you type!\n\n"
            "**Quick commands:**\n"
            "• `investigate <service> <environment>` — start a structured investigation\n"
            "• `approve <request_id>` — approve a pending fix strategy\n"
            "• `reject <request_id>` — reject a pending fix strategy\n"
            "• `execute <request_id>` — execute an approved fix strategy\n"
            "• `help` — show this message\n\n"
            "**Or just ask me anything:**\n"
            "• _\"What's the blast radius of order-service going down?\"_\n"
            "• _\"Why are APIM errors spiking?\"_\n"
            "• _\"Show me the last 3 incidents\"_\n\n"
            "Results are posted as Adaptive Cards to this channel."
        )

    # ── Agentic chat (free-form) ──────────────────────────────────────────────

    async def _handle_agentic_chat(
        self, turn_context: TurnContext, user_text: str
    ) -> None:
        """Route a free-form message to the Corvin agentic engine.

        Sends an immediate "Thinking…" ack, then runs the agentic engine in a
        background task.  The final response is posted back via
        ``adapter.continue_conversation`` when an adapter is available,
        or logged when running in test mode (no adapter).
        """
        from botbuilder.schema import Activity, ActivityTypes
        await turn_context.send_activity("⚡ On it — thinking…")

        # Safely extract Teams conversation ID for session tracking.
        conversation = getattr(turn_context.activity, "conversation", None)
        conversation_id: str = getattr(conversation, "id", None) or "default"

        # Snapshot the conversation reference before the background task runs.
        try:
            conv_ref = TurnContext.get_conversation_reference(turn_context.activity)
        except Exception:
            conv_ref = None

        session_id = self._get_or_create_session(conversation_id, user_text)

        self._last_agentic_task = asyncio.create_task(
            self._run_agentic_async(session_id, user_text, conv_ref)
        )

    async def _send_typing_loop(self, conv_ref: Any, interval: float = 5.0) -> None:
        """Send typing indicators every *interval* seconds until cancelled.

        Teams shows the animated '...' bubble while this runs, so the user
        knows Corvin is actively working rather than sitting idle.
        """
        try:
            while True:
                await asyncio.sleep(interval)
                if self._adapter and conv_ref:
                    try:
                        async def _type(tc: TurnContext) -> None:
                            from botbuilder.schema import Activity, ActivityTypes
                            typing = Activity(type=ActivityTypes.typing)
                            await tc.send_activity(typing)
                        await self._adapter.continue_conversation(conv_ref, _type, self._app_id)
                    except Exception:
                        pass  # typing indicator failure is non-critical
        except asyncio.CancelledError:
            pass

    def _get_or_create_session(self, conversation_id: str, first_message: str = "") -> str:
        """Return an existing Corvin session ID for *conversation_id*, or create one."""
        if conversation_id in self._sessions:
            return self._sessions[conversation_id]

        # Lazy imports to avoid heavy load at module level.
        from corvin.storage.db import get_session as get_db_session
        from corvin.storage.models import CorvinSessionRow

        session_id = str(uuid.uuid4())
        title = (first_message[:60] + "…") if len(first_message) > 60 else first_message
        title = title or f"Teams conversation"
        now = datetime.now(timezone.utc)
        try:
            with get_db_session() as db:
                db.add(CorvinSessionRow(id=session_id, title=title, created_at=now, updated_at=now))
                db.commit()
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._get_or_create_session DB error: %s", exc)

        self._sessions[conversation_id] = session_id
        return session_id

    async def _run_agentic_async(
        self,
        session_id: str,
        user_text: str,
        conv_ref: Any | None,
    ) -> None:
        """Background task: run the agentic engine and post the result back to Teams."""
        from corvin.storage.db import get_session as get_db_session
        from corvin.storage.models import CorvinMessageRow, CorvinSessionRow
        from corvin.strategy.agent_service import CorvinAgentService
        from sqlalchemy import select

        try:
            # Load existing history for this session.
            with get_db_session() as db:
                msg_rows = (
                    db.execute(
                        select(CorvinMessageRow)
                        .where(CorvinMessageRow.session_id == session_id)
                        .order_by(CorvinMessageRow.created_at)
                    )
                    .scalars()
                    .all()
                )
                history = [{"role": m.role, "content": m.content} for m in msg_rows]

            # Persist the user message.
            now = datetime.now(timezone.utc)
            with get_db_session() as db:
                db.add(CorvinMessageRow(session_id=session_id, role="user", content=user_text, created_at=now))
                session_row = db.get(CorvinSessionRow, session_id)
                if session_row:
                    session_row.updated_at = now
                db.commit()

            history.append({"role": "user", "content": user_text})

            # Start typing indicator loop — shows '...' bubble in Teams while engine runs.
            typing_task = asyncio.create_task(self._send_typing_loop(conv_ref, interval=5.0))

            # Run the agentic engine in a thread (stream_chat_simple is synchronous).
            text_chunks: list[str] = []

            def _run_sync() -> None:
                svc = CorvinAgentService()
                for chunk in svc.stream_chat_simple(history):
                    if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                        try:
                            data = json.loads(chunk[6:])
                            if data.get("type") == "text" and data.get("text"):
                                text_chunks.append(data["text"])
                        except Exception:
                            pass

            try:
                await asyncio.to_thread(_run_sync)
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

            final_text = "".join(text_chunks).strip() or "Sorry, I couldn't generate a response."

            # Persist the assistant reply.
            now2 = datetime.now(timezone.utc)
            with get_db_session() as db:
                db.add(CorvinMessageRow(session_id=session_id, role="assistant", content=final_text, created_at=now2))
                session_row = db.get(CorvinSessionRow, session_id)
                if session_row:
                    session_row.updated_at = now2
                db.commit()

            # Post back to the Teams conversation.
            if self._adapter and conv_ref:
                async def _reply(tc: TurnContext) -> None:
                    await tc.send_activity(final_text)

                await self._adapter.continue_conversation(conv_ref, _reply, self._app_id)
            else:
                # No adapter in test/local mode — log only.
                _log.info(
                    "CorvinBot._run_agentic_async: no adapter; response for session %s: %.120s",
                    session_id,
                    final_text,
                )

        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._run_agentic_async failed for session %s: %s", session_id, exc)

    async def _handle_approval(
        self,
        turn_context: TurnContext,
        args: list[str],
        new_status: ApprovalStatus,
    ) -> None:
        """Handle ``approve <id>`` and ``reject <id>`` commands.

        Mirrors the API state machine: only investigations currently in
        ``pending`` can transition to ``approved`` or ``rejected``.
        """
        verb = new_status.value
        if not args:
            await turn_context.send_activity(f"Usage: `{verb} <request_id>`")
            return
        request_id = args[0]
        try:
            current = await asyncio.to_thread(self._repository.get_approval_status, request_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._handle_approval lookup failed for %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"⚠️ Could not look up `{request_id}`. Please try again."
            )
            return

        if current is None:
            await turn_context.send_activity(f"❌ Investigation `{request_id}` not found.")
            return
        if current != ApprovalStatus.PENDING.value:
            await turn_context.send_activity(
                f"⚠️ Cannot {verb} `{request_id}` — current status is **{current}**."
            )
            return

        try:
            await asyncio.to_thread(self._repository.update_approval_status, request_id, new_status)
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._handle_approval update failed for %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"⚠️ Failed to {verb} `{request_id}` — see server logs."
            )
            return

        icon = "✅" if new_status == ApprovalStatus.APPROVED else "❌"
        msg = (
            "Use `execute <request_id>` to run the fix strategy."
            if new_status == ApprovalStatus.APPROVED
            else "No fix will be executed for this investigation."
        )
        await turn_context.send_activity(
            f"{icon} {verb.capitalize()}d **{request_id}**. {msg}"
        )

    async def _handle_execute(
        self, turn_context: TurnContext, args: list[str]
    ) -> None:
        """Handle ``execute <id>`` — run the approved fix strategy."""
        if not args:
            await turn_context.send_activity("Usage: `execute <request_id>`")
            return
        request_id = args[0]

        try:
            current = await asyncio.to_thread(self._repository.get_approval_status, request_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._handle_execute lookup failed for %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"⚠️ Could not look up `{request_id}`. Please try again."
            )
            return

        if current is None:
            await turn_context.send_activity(f"❌ Investigation `{request_id}` not found.")
            return
        if current != ApprovalStatus.APPROVED.value:
            await turn_context.send_activity(
                f"⚠️ Cannot execute `{request_id}` — current status is **{current}** "
                "(must be `approved`)."
            )
            return

        # Load the persisted InvestigationResult — required by ExecutionService.
        try:
            result = await asyncio.to_thread(
                self._repository.get_investigation_result, request_id
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._handle_execute load failed for %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"⚠️ Could not load investigation `{request_id}`. Please try again."
            )
            return
        if result is None:
            await turn_context.send_activity(
                f"❌ Investigation `{request_id}` result not found in persistence store."
            )
            return

        await turn_context.send_activity(
            f"🚀 Executing approved fix strategy for **{request_id}**…"
        )

        try:
            outcome = await asyncio.to_thread(
                self._execution.execute, result, current
            )
        except PermissionError as exc:
            _log.warning("CorvinBot._handle_execute gate refused %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"⚠️ Execution refused by the approval gate for `{request_id}`."
            )
            return
        except Exception as exc:  # noqa: BLE001
            _log.warning("CorvinBot._handle_execute failed for %s: %s", request_id, exc)
            await turn_context.send_activity(
                f"❌ Execution failed for `{request_id}` — see server logs."
            )
            return

        # Transition approval_status → executed so subsequent execute calls are blocked.
        try:
            await asyncio.to_thread(
                self._repository.update_approval_status,
                request_id,
                ApprovalStatus.EXECUTED,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "CorvinBot._handle_execute: state transition to EXECUTED failed for %s: %s",
                request_id,
                exc,
            )

        all_ok = bool(getattr(outcome, "all_succeeded", False))
        head = "✅ Execution complete." if all_ok else "⚠️ Execution finished with errors."
        lines = [head]
        for o in getattr(outcome, "outcomes", []) or []:
            mark = "✅" if getattr(o, "success", False) else "❌"
            title = getattr(o, "title", "?")
            detail = getattr(o, "detail", "")
            lines.append(f"{mark} **{title}** — {detail}")
        await turn_context.send_activity("\n".join(lines))

    # ── Background investigation ──────────────────────────────────────────────

    async def _run_investigation_async(
        self, service_name: str, environment: str
    ) -> None:
        """Run the investigation engine and post the result card.

        Runs ``InvestigationEngine.run()`` in a thread executor (it is
        synchronous) so the event loop remains responsive.

        Never raises — all exceptions are logged and swallowed so that a single
        failing investigation does not crash the bot process.
        """
        try:
            request = InvestigationRequest(
                trigger_source=TriggerSource.TEAMS,
                service_name=service_name,
                environment=environment,
                description=f"Teams investigation: {service_name} in {environment}",
            )
            # Run the sync engine in a thread to avoid blocking the event loop.
            result = await asyncio.to_thread(self._engine.run, request)
            # Post the result card via the outbound Teams webhook.
            self._teams.send_result(result)
            # Optional and non-fatal: email RCA PDF when configured.
            send_rca_email_if_enabled(result)
            _log.info(
                "CorvinBot: investigation complete for service=%s env=%s request_id=%s",
                service_name,
                environment,
                result.request_id,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "CorvinBot._run_investigation_async failed for service=%s env=%s: %s",
                service_name,
                environment,
                exc,
            )

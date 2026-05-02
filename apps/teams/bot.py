"""
CorvinBot — V2 Teams ChatOps bot.

Handles inbound @mention messages from Microsoft Teams via the Bot Framework.

Supported commands
------------------
investigate <service_name> [environment]
    Trigger a new investigation.  Environment defaults to ``production`` when
    omitted.  An acknowledgement is sent immediately; the investigation runs
    in a background task and the result card is posted via the outbound webhook.

help
    Show a brief command reference.

Any unrecognised input returns a friendly error with a usage hint.

Testing
-------
``CorvinBot`` accepts injectable *engine* and *teams_adapter* constructor args
so unit tests can drive behaviour without real Azure / Teams endpoints.
The ``_last_investigation_task`` attribute is set whenever an investigation
background task is created — tests can ``await`` it to wait for completion.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from botbuilder.core import ActivityHandler, TurnContext

from corvin.core.contracts import ApprovalStatus, InvestigationRequest, TriggerSource
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
        # Set by _handle_investigate; exposed for test introspection only.
        self._last_investigation_task: asyncio.Task[None] | None = None

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
            await turn_context.send_activity(
                f"Unknown command: `{parsed.command}`. "
                "Try `investigate <service> <environment>`, `approve <id>`, "
                "`reject <id>`, `execute <id>`, or `help`."
            )

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
            "**Corvin — Available Commands**\n\n"
            "• `investigate <service> <environment>` — start an investigation\n"
            "• `approve <request_id>` — approve a pending fix strategy\n"
            "• `reject <request_id>` — reject a pending fix strategy\n"
            "• `execute <request_id>` — execute an approved fix strategy\n"
            "• `help` — show this message\n\n"
            "Results are posted as Adaptive Cards to this channel."
        )

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

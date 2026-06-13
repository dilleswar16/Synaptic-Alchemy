"""
V2 Slice 5 — Teams ChatOps Bot (CorvinBot).

Tests cover:
  - _strip_mention_tags helper (AT tags, no tags, residual HTML, multi-mention)
  - _parse_command helper (investigate with/without env, unknown, empty, help)
  - CorvinBot.on_message_activity dispatch:
      investigate command sends ack
      investigate with no args sends usage hint
      empty message sends help hint
      help command sends help text
      unknown command sends error with command name
  - CorvinBot._run_investigation_async:
      calls engine.run with correct InvestigationRequest
      trigger_source is TriggerSource.TEAMS
      environment defaults to "production" when not specified
      calls teams_adapter.send_result with the engine result
      gracefully handles engine exception without raising
  - POST /teams/messages route:
      returns 501 when bot_enabled is false (default)
      /teams/messages is registered in the app router

All bot logic tests use:
  - _FakeTurnContext (duck-typed — no real TurnContext required)
  - _FakeEngine (sync fake returning a canned InvestigationResult)
  - _FakeTeamsAdapter (captures sent results)

No real Teams connection, no real Azure endpoints contacted.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.teams.bot import (
    CorvinBot,
    _ParsedCommand,
    _parse_command,
    _strip_mention_tags,
)
from corvin.core.contracts import (
    ActionType,
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.execution.execution_service import ActionOutcome, ExecutionResult


# ═══════════════════════════════════════════════════════════════════════════════
# Test doubles
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeActivity:
    """Minimal Activity-like object: only exposes .text."""

    def __init__(self, text: str = "") -> None:
        self.text = text


class _FakeTurnContext:
    """Duck-typed TurnContext for unit testing CorvinBot handlers.

    Captures all send_activity calls in ``self.sent`` for assertions.
    """

    def __init__(self, text: str = "") -> None:
        self.activity = _FakeActivity(text=text)
        self.sent: list[str] = []

    async def send_activity(self, text_or_activity: Any) -> None:
        self.sent.append(str(text_or_activity))


def _make_canned_result(request_id: str = "bot-test-1") -> InvestigationResult:
    """Return a minimal valid InvestigationResult for test assertions."""
    req = InvestigationRequest(
        id=request_id,
        trigger_source=TriggerSource.TEAMS,
        service_name="order-service",
        environment="production",
        description="Teams investigation: order-service in production",
    )
    return InvestigationResult(
        request_id=request_id,
        request=req,
        evidence=EvidenceBundle(request_id=request_id),
        rca=RCAOutput(
            request_id=request_id,
            summary="Heap exhaustion.",
            root_cause="JVM heap too low.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=request_id,
            summary="Restart pods.",
            justification="Heap exhaustion requires restart.",
            actions=[
                FixAction(
                    title="Restart order-service",
                    description="Rolling restart.",
                    action_type=ActionType.RESTART_POD,
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Service recovers in 60s.",
                )
            ],
        ),
    )


class _FakeEngine:
    """Synchronous fake InvestigationEngine.  Captures calls, returns canned result."""

    def __init__(self) -> None:
        self.calls: list[InvestigationRequest] = []
        self._result = _make_canned_result()

    def run(self, request: InvestigationRequest) -> InvestigationResult:
        self.calls.append(request)
        return self._result


class _FailingEngine:
    """Fake engine that raises on every run() call."""

    def run(self, request: InvestigationRequest) -> InvestigationResult:
        raise RuntimeError("Simulated engine failure")


class _FakeTeamsAdapter:
    """Fake outbound TeamsAdapter.  Captures sent results."""

    def __init__(self) -> None:
        self.sent_results: list[InvestigationResult] = []

    def send_result(self, result: InvestigationResult) -> None:
        self.sent_results.append(result)


# ═══════════════════════════════════════════════════════════════════════════════
# _strip_mention_tags
# ═══════════════════════════════════════════════════════════════════════════════


def test_strip_mention_tags_removes_at_tag():
    text = "<at>Corvin</at> investigate order-service production"
    assert _strip_mention_tags(text) == "investigate order-service production"


def test_strip_mention_tags_no_tags_unchanged():
    assert _strip_mention_tags("investigate order-service") == "investigate order-service"


def test_strip_mention_tags_removes_multiple_at_tags():
    text = "<at>Corvin</at> <at>Bot</at> help"
    assert _strip_mention_tags(text) == "help"


def test_strip_mention_tags_collapses_extra_whitespace():
    assert _strip_mention_tags("   investigate   order-service   ") == "investigate order-service"


def test_strip_mention_tags_removes_residual_html():
    text = "<b>investigate</b> order-service"
    assert _strip_mention_tags(text) == "investigate order-service"


def test_strip_mention_tags_empty_string():
    assert _strip_mention_tags("") == ""


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_command
# ═══════════════════════════════════════════════════════════════════════════════


def test_parse_command_investigate_with_env():
    p = _parse_command("investigate order-service production")
    assert p is not None
    assert p.command == "investigate"
    assert p.args == ["order-service", "production"]


def test_parse_command_investigate_without_env():
    p = _parse_command("investigate order-service")
    assert p is not None
    assert p.command == "investigate"
    assert p.args == ["order-service"]


def test_parse_command_help():
    p = _parse_command("help")
    assert p is not None
    assert p.command == "help"
    assert p.args == []


def test_parse_command_unknown():
    p = _parse_command("deploy order-service")
    assert p is not None
    assert p.command == "deploy"


def test_parse_command_empty_returns_none():
    assert _parse_command("") is None


def test_parse_command_whitespace_only_returns_none():
    assert _parse_command("   ") is None


def test_parse_command_strips_mention_tags():
    p = _parse_command("<at>Corvin</at> investigate order-service staging")
    assert p is not None
    assert p.command == "investigate"
    assert p.args == ["order-service", "staging"]


def test_parse_command_lowercases():
    p = _parse_command("INVESTIGATE Order-Service PRODUCTION")
    assert p is not None
    assert p.command == "investigate"
    assert p.args == ["order-service", "production"]


# ═══════════════════════════════════════════════════════════════════════════════
# CorvinBot.on_message_activity — dispatch
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bot_investigate_sends_ack_message():
    """investigate command should reply with an acknowledgement before running."""
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("<at>Corvin</at> investigate order-service production")

    await bot.on_message_activity(ctx)
    # Cancel the background task (it's not what we're testing here)
    if bot._last_investigation_task:
        bot._last_investigation_task.cancel()
        try:
            await bot._last_investigation_task
        except (asyncio.CancelledError, Exception):
            pass

    assert len(ctx.sent) == 1
    assert "Investigating" in ctx.sent[0]
    assert "order-service" in ctx.sent[0]
    assert "production" in ctx.sent[0]


@pytest.mark.asyncio
async def test_bot_investigate_ack_mentions_channel():
    """The ack should tell the user where results will be posted."""
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate order-service production")

    await bot.on_message_activity(ctx)
    if bot._last_investigation_task:
        bot._last_investigation_task.cancel()
        try:
            await bot._last_investigation_task
        except (asyncio.CancelledError, Exception):
            pass

    assert "channel" in ctx.sent[0].lower() or "shortly" in ctx.sent[0].lower()


@pytest.mark.asyncio
async def test_bot_investigate_no_args_sends_usage():
    """investigate with no service name should send a usage hint."""
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate")

    await bot.on_message_activity(ctx)

    assert len(ctx.sent) == 1
    assert "usage" in ctx.sent[0].lower() or "example" in ctx.sent[0].lower()


@pytest.mark.asyncio
async def test_bot_help_command_sends_help_text():
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("help")

    await bot.on_message_activity(ctx)

    assert len(ctx.sent) == 1
    assert "investigate" in ctx.sent[0].lower()


@pytest.mark.asyncio
async def test_bot_help_command_lists_investigate_and_help():
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("help")

    await bot.on_message_activity(ctx)

    msg = ctx.sent[0].lower()
    assert "investigate" in msg
    assert "help" in msg


@pytest.mark.asyncio
async def test_bot_unknown_command_routes_to_agentic_engine():
    """Unrecognised input (e.g. 'deploy order-service') is routed to the agentic engine.

    The bot must send an immediate ack ('On it / Thinking').  The background
    agentic task is cancelled immediately — we are only testing the dispatch
    path here, not the LLM response.
    """
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("deploy order-service")

    await bot.on_message_activity(ctx)

    # Cancel background agentic task to avoid side-effects in tests.
    if bot._last_agentic_task:
        bot._last_agentic_task.cancel()
        try:
            await bot._last_agentic_task
        except (asyncio.CancelledError, Exception):
            pass

    assert len(ctx.sent) == 1
    ack = ctx.sent[0].lower()
    assert "thinking" in ack or "on it" in ack


@pytest.mark.asyncio
async def test_bot_empty_text_sends_help_hint():
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("")

    await bot.on_message_activity(ctx)

    assert len(ctx.sent) == 1
    assert "investigate" in ctx.sent[0].lower() or "corvin" in ctx.sent[0].lower()


@pytest.mark.asyncio
async def test_bot_mention_only_sends_help_hint():
    """A bare @mention with no command text should send the help hint."""
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("<at>Corvin</at>")

    await bot.on_message_activity(ctx)

    assert len(ctx.sent) == 1
    assert "investigate" in ctx.sent[0].lower() or "corvin" in ctx.sent[0].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# CorvinBot._run_investigation_async
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_investigation_calls_engine_run():
    """Background task should call engine.run exactly once."""
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())

    await bot._run_investigation_async("order-service", "production")

    assert len(engine.calls) == 1


@pytest.mark.asyncio
async def test_run_investigation_passes_correct_service_name():
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())

    await bot._run_investigation_async("payment-service", "staging")

    assert engine.calls[0].service_name == "payment-service"


@pytest.mark.asyncio
async def test_run_investigation_passes_correct_environment():
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())

    await bot._run_investigation_async("order-service", "staging")

    assert engine.calls[0].environment == "staging"


@pytest.mark.asyncio
async def test_run_investigation_trigger_source_is_teams():
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())

    await bot._run_investigation_async("order-service", "production")

    assert engine.calls[0].trigger_source == TriggerSource.TEAMS


@pytest.mark.asyncio
async def test_run_investigation_calls_teams_send_result():
    """After the engine runs, send_result must be called with the result."""
    engine = _FakeEngine()
    adapter = _FakeTeamsAdapter()
    bot = CorvinBot(engine=engine, teams_adapter=adapter)

    await bot._run_investigation_async("order-service", "production")

    assert len(adapter.sent_results) == 1
    assert adapter.sent_results[0] is engine._result


@pytest.mark.asyncio
async def test_run_investigation_engine_exception_does_not_raise():
    """A failing engine must NOT propagate the exception out of the background task."""
    bot = CorvinBot(engine=_FailingEngine(), teams_adapter=_FakeTeamsAdapter())

    # Must not raise
    await bot._run_investigation_async("order-service", "production")


@pytest.mark.asyncio
async def test_run_investigation_engine_exception_skips_send_result():
    """When the engine fails, send_result must NOT be called."""
    adapter = _FakeTeamsAdapter()
    bot = CorvinBot(engine=_FailingEngine(), teams_adapter=adapter)

    await bot._run_investigation_async("order-service", "production")

    assert len(adapter.sent_results) == 0


@pytest.mark.asyncio
async def test_run_investigation_default_environment_is_production():
    """The bot should pass the environment exactly as given — 'production' is default at call site."""
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())

    await bot._run_investigation_async("order-service", "production")

    assert engine.calls[0].environment == "production"


# ═══════════════════════════════════════════════════════════════════════════════
# on_message_activity → background task end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bot_investigate_background_task_runs_engine():
    """After on_message_activity, awaiting the background task should have called engine."""
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate order-service production")

    await bot.on_message_activity(ctx)
    assert bot._last_investigation_task is not None
    await bot._last_investigation_task  # wait for background work to finish

    assert len(engine.calls) == 1
    assert engine.calls[0].service_name == "order-service"
    assert engine.calls[0].environment == "production"


@pytest.mark.asyncio
async def test_bot_investigate_background_task_sends_result():
    """After on_message_activity, the result card must be sent via teams adapter."""
    engine = _FakeEngine()
    adapter = _FakeTeamsAdapter()
    bot = CorvinBot(engine=engine, teams_adapter=adapter)
    ctx = _FakeTurnContext("investigate order-service production")

    await bot.on_message_activity(ctx)
    await bot._last_investigation_task

    assert len(adapter.sent_results) == 1


@pytest.mark.asyncio
async def test_bot_investigate_without_environment_prompts_for_one():
    """When the environment arg is omitted, the bot asks for it instead of
    assuming production — no investigation task is started."""
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate order-service")

    await bot.on_message_activity(ctx)

    assert bot._last_investigation_task is None
    assert engine.calls == []
    assert any("environment" in msg.lower() for msg in ctx.sent)


@pytest.mark.asyncio
async def test_bot_investigate_uses_explicit_environment():
    engine = _FakeEngine()
    bot = CorvinBot(engine=engine, teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate payment-service staging")

    await bot.on_message_activity(ctx)
    await bot._last_investigation_task

    assert engine.calls[0].environment == "staging"
    assert engine.calls[0].service_name == "payment-service"


@pytest.mark.asyncio
async def test_bot_investigate_creates_last_investigation_task():
    """_last_investigation_task must be set after a valid investigate command."""
    bot = CorvinBot(engine=_FakeEngine(), teams_adapter=_FakeTeamsAdapter())
    ctx = _FakeTurnContext("investigate order-service production")

    assert bot._last_investigation_task is None

    await bot.on_message_activity(ctx)
    assert bot._last_investigation_task is not None

    await bot._last_investigation_task  # cleanup


# ═══════════════════════════════════════════════════════════════════════════════
# POST /teams/messages route
# ═══════════════════════════════════════════════════════════════════════════════


def test_teams_messages_route_returns_501_when_bot_disabled():
    """With bot_enabled: false, the route returns 501."""
    from unittest.mock import patch

    from apps.api.main import app

    with patch("apps.teams.router._load_teams_config", return_value={"bot_enabled": False}):
        client = TestClient(app)
        resp = client.post(
            "/teams/messages",
            json={"type": "message", "text": "investigate order-service production"},
        )
        assert resp.status_code == 501


def test_teams_messages_route_is_registered():
    """The /teams/messages route must be present in the application router."""
    from apps.api.main import app

    paths = [route.path for route in app.routes]
    assert "/teams/messages" in paths


def test_teams_messages_route_501_body_explains_how_to_enable():
    """The 501 body should explain how to enable the bot (TEAMS_BOT_ENABLED)."""
    from unittest.mock import patch

    from apps.api.main import app

    with patch("apps.teams.router._load_teams_config", return_value={"bot_enabled": False}):
        client = TestClient(app)
        resp = client.post("/teams/messages", json={"type": "message", "text": "help"})
        assert "TEAMS_BOT_ENABLED" in resp.text


# -------------------------------------------------------------------------------
# CorvinBot.approve / reject / execute commands  (V2 slice 5b)
# -------------------------------------------------------------------------------


class _FakeRepository:
    """Test double for InvestigationRepository — supports approve/reject/execute paths.

    Implements the subset of methods CorvinBot calls:
      - get_approval_status(request_id) -> str | None
      - update_approval_status(request_id, ApprovalStatus) -> None
      - get_investigation_result(request_id) -> InvestigationResult | None
    """

    def __init__(
        self,
        status: str | None = "pending",
        result: InvestigationResult | None = None,
    ) -> None:
        self._status = status
        self._result = result
        self.update_calls: list[tuple[str, Any]] = []

    def get_approval_status(self, request_id: str) -> str | None:
        return self._status

    def update_approval_status(self, request_id: str, new_status: Any) -> None:
        self.update_calls.append((request_id, new_status))
        self._status = new_status.value if hasattr(new_status, "value") else new_status

    def get_investigation_result(self, request_id: str) -> InvestigationResult | None:
        return self._result


class _FakeExecutionService:
    """Subclass of the real ExecutionService that records calls and returns a canned result.

    The real ExecutionService.execute signature is:
        execute(self, result: InvestigationResult, approval_status: str, namespace: str | None = None)

    We honor that signature exactly so a contract drift between the bot and the
    real service surfaces as a TypeError in these tests rather than as a silent
    runtime failure in production.
    """

    def __init__(self, result: "ExecutionResult") -> None:
        self._result = result
        self.calls: list[tuple[InvestigationResult, str]] = []

    def execute(
        self,
        result: InvestigationResult,
        approval_status: str,
        namespace: str | None = None,
    ) -> "ExecutionResult":
        self.calls.append((result, approval_status))
        return self._result


def _outcome(title: str, success: bool, detail: str) -> ActionOutcome:
    return ActionOutcome(
        action_type=ActionType.RESTART_POD,
        title=title,
        success=success,
        detail=detail,
    )


def _exec_result(request_id: str, outcomes: list[ActionOutcome]) -> "ExecutionResult":
    return ExecutionResult(request_id=request_id, outcomes=outcomes)


@pytest.mark.asyncio
async def test_bot_approve_pending_marks_approved() -> None:
    repo = _FakeRepository(status="pending")
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=_FakeExecutionService(_exec_result("req-123", [])),
    )
    ctx = _FakeTurnContext(text="approve req-123")
    await bot.on_message_activity(ctx)
    assert len(repo.update_calls) == 1
    assert repo.update_calls[0][0] == "req-123"
    assert any("Approved" in m and "req-123" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_reject_pending_marks_rejected() -> None:
    repo = _FakeRepository(status="pending")
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=_FakeExecutionService(_exec_result("req-456", [])),
    )
    ctx = _FakeTurnContext(text="reject req-456")
    await bot.on_message_activity(ctx)
    assert len(repo.update_calls) == 1
    assert any("Rejected" in m and "req-456" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_approve_non_pending_refuses() -> None:
    repo = _FakeRepository(status="approved")
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=_FakeExecutionService(_exec_result("req-789", [])),
    )
    ctx = _FakeTurnContext(text="approve req-789")
    await bot.on_message_activity(ctx)
    assert repo.update_calls == []
    assert any("Cannot approve" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_approve_unknown_request_says_not_found() -> None:
    repo = _FakeRepository(status=None)
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=_FakeExecutionService(_exec_result("req-missing", [])),
    )
    ctx = _FakeTurnContext(text="approve req-missing")
    await bot.on_message_activity(ctx)
    assert any("not found" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_approve_no_args_sends_usage() -> None:
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=_FakeRepository(),
        execution_service=_FakeExecutionService(_exec_result("x", [])),
    )
    ctx = _FakeTurnContext(text="approve")
    await bot.on_message_activity(ctx)
    assert any("Usage" in m and "approve" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_execute_approved_runs_service_and_reports_outcomes() -> None:
    canned = _make_canned_result("req-exec-1")
    repo = _FakeRepository(status="approved", result=canned)
    exec_service = _FakeExecutionService(
        _exec_result(
            "req-exec-1",
            [_outcome("Restart pod", True, "Pod restarted successfully.")],
        )
    )
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=exec_service,
    )
    ctx = _FakeTurnContext(text="execute req-exec-1")
    await bot.on_message_activity(ctx)

    # Verify the bot called execute with the real (result, approval_status) signature.
    assert len(exec_service.calls) == 1
    called_result, called_status = exec_service.calls[0]
    assert called_result.request_id == "req-exec-1"
    assert called_status == "approved"

    # Verify the bot transitioned approval_status -> executed after success.
    assert any(
        rid == "req-exec-1" and getattr(s, "value", s) == "executed"
        for rid, s in repo.update_calls
    )

    body = "\n".join(ctx.sent)
    assert "Executing" in body
    assert "Execution complete" in body
    # Bot must use real ActionOutcome attributes (title / detail), not action_title / message.
    assert "Restart pod" in body
    assert "Pod restarted successfully." in body


@pytest.mark.asyncio
async def test_bot_execute_non_approved_refuses() -> None:
    repo = _FakeRepository(status="pending")
    exec_service = _FakeExecutionService(_exec_result("req-exec-2", []))
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=exec_service,
    )
    ctx = _FakeTurnContext(text="execute req-exec-2")
    await bot.on_message_activity(ctx)
    assert exec_service.calls == []
    assert any("Cannot execute" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_execute_missing_result_returns_friendly_error() -> None:
    """If the row is approved but the InvestigationResult is missing, the bot
    must NOT call ExecutionService.execute (which would crash on a None result)."""
    repo = _FakeRepository(status="approved", result=None)
    exec_service = _FakeExecutionService(_exec_result("req-exec-missing", []))
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=exec_service,
    )
    ctx = _FakeTurnContext(text="execute req-exec-missing")
    await bot.on_message_activity(ctx)
    assert exec_service.calls == []
    assert any("not found" in m for m in ctx.sent)


@pytest.mark.asyncio
async def test_bot_execute_failures_reported_per_action() -> None:
    canned = _make_canned_result("req-exec-3")
    repo = _FakeRepository(status="approved", result=canned)
    exec_service = _FakeExecutionService(
        _exec_result(
            "req-exec-3",
            [
                _outcome("Restart pod", True, "OK"),
                _outcome("Scale up", False, "Quota exceeded"),
            ],
        )
    )
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=repo,
        execution_service=exec_service,
    )
    ctx = _FakeTurnContext(text="execute req-exec-3")
    await bot.on_message_activity(ctx)
    body = "\n".join(ctx.sent)
    assert "errors" in body
    assert "Quota exceeded" in body


@pytest.mark.asyncio
async def test_bot_help_lists_approve_reject_execute() -> None:
    bot = CorvinBot(
        engine=_FakeEngine(),
        teams_adapter=_FakeTeamsAdapter(),
        repository=_FakeRepository(),
        execution_service=_FakeExecutionService(_exec_result("x", [])),
    )
    ctx = _FakeTurnContext(text="help")
    await bot.on_message_activity(ctx)
    body = "\n".join(ctx.sent)
    assert "approve" in body
    assert "reject" in body
    assert "execute" in body

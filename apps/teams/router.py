"""
Teams bot FastAPI router — V2 Slice 5.

Mounts at ``/teams`` in the main Corvin application.

Endpoint
--------
POST /teams/messages
    Bot Framework inbound message endpoint.  All @mentions from Teams arrive
    here.  The endpoint validates the Bot Framework JWT token, deserialises the
    Activity, and dispatches to ``CorvinBot.on_turn``.

    Returns 501 when ``bot_enabled: false`` in config/integrations/teams.yaml
    so that V1/V2 development environments work without a registered Azure Bot.
    Returns 201 on successful dispatch.
    Returns 400 on malformed JSON body.

Configuration
-------------
Set in ``config/integrations/teams.yaml``:

    bot_enabled: true
    app_id: "${TEAMS_APP_ID}"
    app_password: "${TEAMS_APP_PASSWORD}"

``bot_enabled: false`` (the default) causes the endpoint to return 501 — safe
for local and CI environments that have no Bot Framework registration.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from apps.teams.bot import CorvinBot
from corvin.core.config_loader import get_env, load_config

router = APIRouter()
_log = logging.getLogger(__name__)


# ── Config helpers ────────────────────────────────────────────────────────────


def _load_teams_config() -> dict[str, Any]:
    """Load the teams integration config for the current environment."""
    return load_config("integrations/teams", get_env())


def _resolve_env(value: str) -> str:
    """Expand ``${ENV_VAR}`` placeholders; return empty string when unset."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value if isinstance(value, str) else ""


# ── Dependency providers (overridable in tests) ───────────────────────────────


def get_corvin_bot() -> CorvinBot:
    """Return a configured CorvinBot instance.  Override in tests."""
    return CorvinBot()


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/messages", status_code=201)
async def messages(
    request: Request,
    bot: CorvinBot = Depends(get_corvin_bot),
) -> Response:
    """Bot Framework inbound message handler.

    Security
    --------
    The ``BotFrameworkAdapter`` validates the ``Authorization`` JWT header
    using the Bot Framework public keys.  Requests with a missing or invalid
    token will be rejected with a 401 response by the adapter before the bot
    handler is called.

    Local development
    -----------------
    Set ``bot_enabled: false`` (the default) to skip Bot Framework
    registration entirely.  This returns 501 so the rest of the API works
    without any Azure Bot registration.
    """
    cfg = _load_teams_config()

    # ── Guard: disabled bot returns 501 immediately ───────────────────────────
    if not cfg.get("bot_enabled", False):
        _log.debug("Teams bot is disabled — returning 501.")
        return Response(
            content=(
                "Teams bot is not enabled. "
                "Set bot_enabled: true in config/integrations/teams.yaml "
                "and supply TEAMS_APP_ID / TEAMS_APP_PASSWORD."
            ),
            status_code=501,
            media_type="text/plain",
        )

    # ── Build adapter from config ─────────────────────────────────────────────
    app_id = _resolve_env(str(cfg.get("app_id", "")))
    app_password = _resolve_env(str(cfg.get("app_password", "")))
    settings = BotFrameworkAdapterSettings(app_id=app_id, app_password=app_password)
    adapter = BotFrameworkAdapter(settings)

    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception:
        return Response(
            content="Invalid JSON body.", status_code=400, media_type="text/plain"
        )

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    # ── Dispatch to bot ───────────────────────────────────────────────────────
    invoke_response = await adapter.process_activity(activity, auth_header, bot.on_turn)

    if invoke_response:
        return JSONResponse(
            content=invoke_response.body, status_code=invoke_response.status
        )

    return Response(status_code=201)

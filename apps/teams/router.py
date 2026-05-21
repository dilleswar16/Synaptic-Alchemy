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
from datetime import datetime, timezone
from typing import Any

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from fastapi import APIRouter, Request, Response
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
    # app_password is empty for User-Assigned Managed Identity — Azure handles auth via IMDS.
    app_password = _resolve_env(str(cfg.get("app_password", "")))
    tenant_id = _resolve_env(str(cfg.get("tenant_id", "")))
    settings = BotFrameworkAdapterSettings(
        app_id=app_id,
        app_password=app_password,  # empty string when using managed identity
        channel_auth_tenant=tenant_id if tenant_id else None,
    )
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
    # Pass adapter + app_id so the bot can use continue_conversation for agentic replies.
    bot_instance = CorvinBot(adapter=adapter, app_id=app_id)
    invoke_response = await adapter.process_activity(activity, auth_header, bot_instance.on_turn)

    if invoke_response:
        return JSONResponse(
            content=invoke_response.body, status_code=invoke_response.status
        )

    return Response(status_code=201)


# ── War Room Channel ──────────────────────────────────────────────────────────


@router.post("/war-room", status_code=201)
async def create_war_room(request: Request) -> JSONResponse:
    """Auto-create a Teams incident channel for a P1 alert via Microsoft Graph API.

    Body: { investigation_id, service_name, environment, severity }

    Requires:
      - war_room_enabled: true in config/policies/investigation.yaml
      - MICROSOFT_GRAPH_CLIENT_ID, MICROSOFT_GRAPH_CLIENT_SECRET, TEAMS_TEAM_ID env vars

    Returns the new Teams channel URL and name when successful.
    Returns 503 when the war room feature is disabled or dependencies missing.
    Returns 502 when Graph API call fails.
    """
    # Guard: httpx must be installed for Graph API calls
    try:
        import httpx
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"detail": "httpx is required for war room creation. Run: pip install httpx"},
        )

    policy = load_config("policies/investigation", get_env())
    if not policy.get("war_room_enabled", False):
        return JSONResponse(
            status_code=503,
            content={"detail": "War room channel creation is disabled. Set war_room_enabled: true in config/policies/investigation.yaml."},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body."})

    service_name     = body.get("service_name", "unknown")
    investigation_id = body.get("investigation_id", "")
    severity         = body.get("severity", "high").lower()

    min_severity   = policy.get("war_room_min_severity", "critical")
    severity_rank  = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    if severity_rank.get(severity, 99) > severity_rank.get(min_severity, 0):
        return JSONResponse(
            status_code=400,
            content={"detail": f"Severity '{severity}' is below war_room_min_severity '{min_severity}'."},
        )

    client_id     = os.environ.get("MICROSOFT_GRAPH_CLIENT_ID", "")
    client_secret = os.environ.get("MICROSOFT_GRAPH_CLIENT_SECRET", "")
    team_id       = os.environ.get("TEAMS_TEAM_ID", "")
    tenant_id     = os.environ.get("AZURE_TENANT_ID", "common")

    if not all([client_id, client_secret, team_id]):
        return JSONResponse(
            status_code=503,
            content={"detail": "MICROSOFT_GRAPH_CLIENT_ID / MICROSOFT_GRAPH_CLIENT_SECRET / TEAMS_TEAM_ID not configured."},
        )

    date_str     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    channel_name = f"INC-{date_str}-{service_name}"

    try:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(token_url, data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            })
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            channel_resp = await client.post(
                f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
                json={
                    "displayName":    channel_name,
                    "description":    f"War room for incident {investigation_id} — {service_name} / {severity}",
                    "membershipType": "standard",
                },
            )
            channel_resp.raise_for_status()
            channel_data = channel_resp.json()

    except Exception as exc:
        _log.error("War room creation failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"detail": f"Microsoft Graph API call failed: {exc}"},
        )

    return JSONResponse(status_code=201, content={
        "channel_name":     channel_name,
        "channel_id":       channel_data.get("id", ""),
        "web_url":          channel_data.get("webUrl", ""),
        "investigation_id": investigation_id,
        "message":          f"War room '{channel_name}' created in Teams.",
    })

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

Supported auth modes
--------------------
- User-Assigned Managed Identity: set ``TEAMS_APP_ID`` to the managed identity
    client ID, leave ``TEAMS_APP_PASSWORD`` empty, and provide ``TEAMS_TENANT_ID``.
- Secret-based bot registration: provide both ``TEAMS_APP_ID`` and
    ``TEAMS_APP_PASSWORD``.

``bot_enabled: false`` (the default) causes the endpoint to return 501 — safe
for local and CI environments that have no Bot Framework registration.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
    ConfigurationServiceClientCredentialFactory,
)
from botbuilder.schema import Activity
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from apps.teams.bot import CorvinBot
from corvin.core.config_loader import get_env, load_config

router = APIRouter()
_log = logging.getLogger(__name__)

_BOT_RUNTIME_CACHE_KEY: tuple[str, str, str] | None = None
_BOT_ADAPTER: CloudAdapter | None = None
_BOT_INSTANCE: CorvinBot | None = None


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
    global _BOT_INSTANCE
    if _BOT_INSTANCE is None:
        _BOT_INSTANCE = CorvinBot()
    return _BOT_INSTANCE


def _get_bot_runtime(cfg: dict[str, Any]) -> tuple[CloudAdapter, CorvinBot]:
    """Build or reuse the Bot Framework adapter and bot instance.

    The deployed branch was recreating the adapter on every request and also
    forcing a managed-identity config even though the integration settings are
    secret-based. Reusing the runtime trims latency and avoids auth mismatches.
    """
    global _BOT_RUNTIME_CACHE_KEY, _BOT_ADAPTER, _BOT_INSTANCE

    app_id = _resolve_env(str(cfg.get("app_id", "")))
    app_password = _resolve_env(str(cfg.get("app_password", "")))
    tenant_id = _resolve_env(str(cfg.get("tenant_id", "")))
    cache_key = (app_id, app_password, tenant_id)

    if _BOT_RUNTIME_CACHE_KEY == cache_key and _BOT_ADAPTER is not None and _BOT_INSTANCE is not None:
        return _BOT_ADAPTER, _BOT_INSTANCE

    class _BotConfig:  # simple config bag read by ConfigurationServiceClientCredentialFactory
        if app_password:
            # Secret-based Azure Bot registration (current deployed config).
            APP_TYPE = "SingleTenant" if tenant_id else "MultiTenant"
            APP_PASSWORD = app_password
            APP_TENANTID = tenant_id
        else:
            # Managed identity fallback for future deployments.
            APP_TYPE = "UserAssignedMsi"
            APP_PASSWORD = ""
            APP_TENANTID = tenant_id

        APP_ID = app_id

    credentials_factory = ConfigurationServiceClientCredentialFactory(_BotConfig())
    bot_auth = ConfigurationBotFrameworkAuthentication(
        _BotConfig(), credentials_factory=credentials_factory
    )
    _BOT_ADAPTER = CloudAdapter(bot_auth)
    _BOT_INSTANCE = CorvinBot(adapter=_BOT_ADAPTER, app_id=app_id)
    _BOT_RUNTIME_CACHE_KEY = cache_key
    return _BOT_ADAPTER, _BOT_INSTANCE


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/messages", status_code=200)
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

    # Build or reuse the adapter + bot instance.
    adapter, bot_instance = _get_bot_runtime(cfg)

    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception:
        return Response(
            content="Invalid JSON body.", status_code=400, media_type="text/plain"
        )

    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        return JSONResponse(
            status_code=401,
            content={"detail": "Authorization header required for Teams bot messages."},
        )

    # ── Dispatch to bot ───────────────────────────────────────────────────────
    # Pass adapter + app_id so the bot can use continue_conversation for agentic replies.
    # CloudAdapter.process_activity has auth_header first, activity second (opposite of BotFrameworkAdapter)
    try:
        invoke_response = await adapter.process_activity(auth_header, activity, bot_instance.on_turn)
    except Exception as exc:
        # Invalid/expired auth tokens should fail clearly instead of surfacing as
        # a generic gateway timeout or unhandled server error.
        message = str(exc).lower()
        if "auth" in message or "token" in message or "unauthor" in message:
            _log.warning("Teams auth failed: %s", exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Teams bot authorization failed."},
            )
        _log.exception("Teams bot dispatch failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Teams bot dispatch failed."},
        )

    if invoke_response:
        return JSONResponse(
            content=invoke_response.body, status_code=invoke_response.status
        )

    return Response(status_code=200)


@router.get("/messages")
async def messages_get() -> JSONResponse:
    """Health/readiness endpoint for Teams probes hitting the message route.

    Some channel checks and manual probes use GET against the same path. A 200
    here avoids noisy 405s and clarifies that POST is the actual Bot Framework
    ingress method.
    """
    cfg = _load_teams_config()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "bot_enabled": bool(cfg.get("bot_enabled", False)),
            "message": "POST /teams/messages is the Bot Framework ingress; GET is health/readiness only.",
        },
    )


@router.get("/health")
async def teams_health() -> JSONResponse:
    """Dedicated health endpoint for the Teams integration."""
    cfg = _load_teams_config()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "bot_enabled": bool(cfg.get("bot_enabled", False)),
            "message": "Teams integration is reachable.",
        },
    )


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

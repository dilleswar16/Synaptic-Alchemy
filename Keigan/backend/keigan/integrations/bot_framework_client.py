"""Azure Bot Service connector: outbound proactive messages and inbound request validation for ``POST /api/teams/messages``."""

from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Any

import httpx
import jwt

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import AuthenticationException, IntegrationException
from keigan.integrations.secret_store import SecretStore

BOT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
BOT_TOKEN_SCOPE = "https://api.botframework.com/.default"
OPENID_CONFIGURATION_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
BOT_ISSUER = "https://api.botframework.com"


@lru_cache(maxsize=1)
def _bot_signing_key_client() -> jwt.PyJWKClient:
    openid_configuration = httpx.get(OPENID_CONFIGURATION_URL, timeout=15).json()
    return jwt.PyJWKClient(openid_configuration["jwks_uri"], cache_keys=True)


class BotFrameworkClient:
    def __init__(self, settings: Settings, secret_store: SecretStore):
        self.settings = settings
        self.secret_store = secret_store
        self._cached_token: tuple[str, float] | None = None

    async def _bot_access_token(self) -> str:
        if self._cached_token and self._cached_token[1] - time.time() > 300:
            return self._cached_token[0]
        client_secret = await self.secret_store.get_secret_or_none(self.settings.teams_bot_app_secret_name)
        if not self.settings.teams_bot_app_id or not client_secret:
            raise IntegrationException("The Teams bot is not configured (TEAMS_BOT_APP_ID and the bot secret are required).", error_code="teams_bot_not_configured")
        token_url = BOT_TOKEN_URL_TEMPLATE.format(tenant_id=self.settings.azure_tenant_id)
        async with httpx.AsyncClient(timeout=20) as http_client:
            response = await http_client.post(
                token_url, data={"grant_type": "client_credentials", "client_id": self.settings.teams_bot_app_id, "client_secret": client_secret, "scope": BOT_TOKEN_SCOPE},
            )
        if response.status_code >= 400:
            raise IntegrationException(f"Could not obtain a Bot Framework token ({response.status_code}).", error_code="teams_bot_token_failed")
        body = response.json()
        self._cached_token = (body["access_token"], time.time() + float(body.get("expires_in", 3600)))
        return self._cached_token[0]

    async def send_activity(self, service_url: str, conversation_id: str, activity: dict[str, Any]) -> str | None:
        """Proactive message into a conversation the bot is part of. Returns the activity id."""
        access_token = await self._bot_access_token()
        request_url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        async with httpx.AsyncClient(timeout=20) as http_client:
            response = await http_client.post(request_url, json=activity, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code >= 400:
            raise IntegrationException(f"The Bot Framework refused the message ({response.status_code}): {response.text[:200]}", error_code="teams_bot_send_failed")
        return response.json().get("id") if response.content else None

    async def validate_inbound_request(self, authorization_header: str | None) -> dict[str, Any]:
        """Validate the Bearer JWT Teams sends to the messaging endpoint (issuer, audience = bot app id, signature)."""
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise AuthenticationException("Missing bot authorization header.")
        if not self.settings.teams_bot_app_id:
            raise AuthenticationException("The Teams bot is not configured.")
        bearer_token = authorization_header[7:].strip()
        try:
            signing_key = await asyncio.to_thread(lambda: _bot_signing_key_client().get_signing_key_from_jwt(bearer_token))
            return jwt.decode(bearer_token, signing_key.key, algorithms=["RS256"], audience=self.settings.teams_bot_app_id, issuer=BOT_ISSUER, options={"require": ["exp", "iss", "aud"]})
        except Exception as token_error:  # noqa: BLE001 - any validation failure is a 401
            raise AuthenticationException("The bot request could not be authenticated.") from token_error

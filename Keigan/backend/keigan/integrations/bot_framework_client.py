"""Azure Bot Service connector: outbound proactive messages and inbound request validation for ``POST /api/teams/messages``."""

from __future__ import annotations

import asyncio
import logging
import time
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import AuthenticationException, IntegrationException
from keigan.integrations.secret_store import SecretStore

BOT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
BOT_TOKEN_SCOPE = "https://api.botframework.com/.default"
OPENID_CONFIGURATION_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
BOT_ISSUER = "https://api.botframework.com"
SERVICE_URL_CLAIM_NAMES = ("serviceurl", "serviceUrl")

logger = logging.getLogger(__name__)


def normalize_service_url(service_url: str) -> str:
    return service_url.strip().rstrip("/").lower()


def is_allowed_service_url(service_url: str | None, allowed_host_patterns: list[str]) -> bool:
    """True when the URL is plain https on a configured Bot Framework host (no credentials, default port).

    Keigan sends its Bot Framework bearer token to the serviceUrl, so a serviceUrl on any other host would hand the token away.
    """
    if not service_url:
        return False
    try:
        parts = urlsplit(service_url.strip())
        host_name, port = parts.hostname, parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or not host_name or parts.username is not None or parts.password is not None or port not in (None, 443):
        return False
    return any(fnmatchcase(host_name.lower(), pattern) for pattern in allowed_host_patterns)


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
        if not is_allowed_service_url(service_url, self.settings.bot_framework_service_url_host_pattern_list):
            logger.warning("Refused to send a Teams message to a service URL that is not allow-listed: %s", service_url)
            raise IntegrationException(
                "The Teams message was not sent because the conversation address is not an approved Bot Framework address.",
                error_code="teams_bot_service_url_not_allowed",
            )
        access_token = await self._bot_access_token()
        request_url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        async with httpx.AsyncClient(timeout=20) as http_client:
            response = await http_client.post(request_url, json=activity, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code >= 400:
            raise IntegrationException(f"The Bot Framework refused the message ({response.status_code}): {response.text[:200]}", error_code="teams_bot_send_failed")
        return response.json().get("id") if response.content else None

    async def validate_inbound_request(self, authorization_header: str | None, activity_service_url: str | None) -> dict[str, Any]:
        """Validate the Bearer JWT Teams sends to the messaging endpoint and bind it to the activity.

        Checks issuer, audience (the bot app id) and signature, then that the token's ``serviceurl`` claim equals the activity's
        ``serviceUrl`` and that this URL is on an allow-listed Bot Framework host. Call it with ``activity.get("serviceUrl")``
        before the activity is stored or answered.
        """
        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise AuthenticationException("Missing bot authorization header.")
        if not self.settings.teams_bot_app_id:
            raise AuthenticationException("The Teams bot is not configured.")
        bearer_token = authorization_header[7:].strip()
        try:
            signing_key = await asyncio.to_thread(lambda: _bot_signing_key_client().get_signing_key_from_jwt(bearer_token))
            token_claims: dict[str, Any] = jwt.decode(bearer_token, signing_key.key, algorithms=["RS256"], audience=self.settings.teams_bot_app_id, issuer=BOT_ISSUER, options={"require": ["exp", "iss", "aud"]})
        except Exception as token_error:  # noqa: BLE001 - any validation failure is a 401
            raise AuthenticationException("The bot request could not be authenticated.") from token_error
        self._require_service_url_bound_to_token(token_claims, activity_service_url)
        return token_claims

    def _require_service_url_bound_to_token(self, token_claims: dict[str, Any], activity_service_url: str | None) -> None:
        token_service_url = next((token_claims[name] for name in SERVICE_URL_CLAIM_NAMES if token_claims.get(name)), None)
        if not token_service_url or not activity_service_url or normalize_service_url(str(token_service_url)) != normalize_service_url(activity_service_url):
            logger.warning("Rejected a bot request: the activity serviceUrl %s does not match the token serviceUrl %s.", activity_service_url, token_service_url)
            raise AuthenticationException("The bot request could not be authenticated.")
        if not is_allowed_service_url(activity_service_url, self.settings.bot_framework_service_url_host_pattern_list):
            logger.warning("Rejected a bot request: serviceUrl %s is not on an allow-listed Bot Framework host.", activity_service_url)
            raise AuthenticationException("The bot request could not be authenticated.")

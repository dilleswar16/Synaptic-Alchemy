"""keigan/integrations/bot_framework_client.py: the Bot Framework token is bound to the activity's serviceUrl (S1).

Tokens are real RS256 JWTs signed with a throw-away key; only the download of Microsoft's public keys is replaced.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import AuthenticationException, IntegrationException
from keigan.integrations import bot_framework_client
from keigan.integrations.bot_framework_client import BotFrameworkClient, is_allowed_service_url

BOT_APP_ID = "44444444-4444-4444-4444-444444444444"
SERVICE_URL = "https://smba.trafficmanager.net/emea/"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
HOST_PATTERNS = ["*.botframework.com", "smba.trafficmanager.net"]


@pytest.fixture
def bot_client(monkeypatch: pytest.MonkeyPatch) -> BotFrameworkClient:
    monkeypatch.setattr(
        bot_framework_client,
        "_bot_signing_key_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SIGNING_KEY.public_key())),
    )
    return BotFrameworkClient(Settings(_env_file=None, teams_bot_app_id=BOT_APP_ID), secret_store=None)  # type: ignore[arg-type]


def authorization_header(**claim_overrides: Any) -> str:
    """A Bot Framework channel token; pass ``serviceurl=None`` to drop a claim."""
    claims: dict[str, Any] = {
        "iss": "https://api.botframework.com",
        "aud": BOT_APP_ID,
        "serviceurl": SERVICE_URL,
        "exp": int(time.time()) + 600,
    }
    claims.update(claim_overrides)
    token = jwt.encode({name: value for name, value in claims.items() if value is not None}, SIGNING_KEY, algorithm="RS256")
    return f"Bearer {token}"


async def test_token_whose_service_url_matches_the_activity_is_accepted(bot_client: BotFrameworkClient) -> None:
    claims = await bot_client.validate_inbound_request(authorization_header(), SERVICE_URL)
    assert claims["serviceurl"] == SERVICE_URL


async def test_service_url_comparison_ignores_case_and_a_trailing_slash(bot_client: BotFrameworkClient) -> None:
    claims = await bot_client.validate_inbound_request(authorization_header(), "HTTPS://SMBA.trafficmanager.net/emea")
    assert claims["aud"] == BOT_APP_ID


async def test_activity_with_a_different_service_url_than_the_token_is_rejected(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(AuthenticationException, match="could not be authenticated"):
        await bot_client.validate_inbound_request(authorization_header(), "https://smba.trafficmanager.net/amer/")


async def test_token_without_a_service_url_claim_is_rejected(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(AuthenticationException, match="could not be authenticated"):
        await bot_client.validate_inbound_request(authorization_header(serviceurl=None), SERVICE_URL)


async def test_activity_without_a_service_url_is_rejected(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(AuthenticationException, match="could not be authenticated"):
        await bot_client.validate_inbound_request(authorization_header(), None)


async def test_service_url_on_a_host_that_is_not_allow_listed_is_rejected_even_when_the_token_agrees(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(AuthenticationException, match="could not be authenticated"):
        await bot_client.validate_inbound_request(authorization_header(serviceurl="https://attacker.example/"), "https://attacker.example/")


async def test_token_for_another_bot_is_still_rejected(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(AuthenticationException, match="could not be authenticated"):
        await bot_client.validate_inbound_request(authorization_header(aud="55555555-5555-5555-5555-555555555555"), SERVICE_URL)


async def test_proactive_message_to_a_host_that_is_not_allow_listed_is_refused_before_any_token_is_requested(bot_client: BotFrameworkClient) -> None:
    with pytest.raises(IntegrationException, match="not an approved Bot Framework address"):
        await bot_client.send_activity("https://attacker.example/", "19:conversation", {"type": "message"})


@pytest.mark.parametrize(
    "service_url",
    [
        "https://smba.trafficmanager.net/teams/",
        "https://smba.botframework.com/",
        "https://SMBA.trafficmanager.net",
        "https://eu.smba.botframework.com/emea/",
    ],
)
def test_bot_framework_service_hosts_are_allowed(service_url: str) -> None:
    assert is_allowed_service_url(service_url, HOST_PATTERNS) is True


@pytest.mark.parametrize(
    "service_url",
    [
        "http://smba.trafficmanager.net/teams/",
        "https://evilbotframework.com/",
        "https://smba.trafficmanager.net.attacker.example/",
        "https://attacker.example/smba.trafficmanager.net",
        "https://user@attacker.example@smba.trafficmanager.net/",
        "https://169.254.169.254/",
        "smba.trafficmanager.net",
        "",
    ],
)
def test_other_service_urls_are_refused(service_url: str) -> None:
    assert is_allowed_service_url(service_url, HOST_PATTERNS) is False

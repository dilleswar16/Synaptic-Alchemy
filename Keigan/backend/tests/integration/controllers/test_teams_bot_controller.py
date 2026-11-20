"""keigan/controllers/teams_bot_controller.py: the inbound bot token is checked against the activity's serviceUrl (S1)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from keigan.config.settings import get_settings
from keigan.integrations import bot_framework_client

BOT_APP_ID = "44444444-4444-4444-4444-444444444444"
SERVICE_URL = "https://smba.trafficmanager.net/emea/"
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def bot_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "teams_bot_app_id", BOT_APP_ID)
    monkeypatch.setattr(
        bot_framework_client,
        "_bot_signing_key_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SIGNING_KEY.public_key())),
    )


def bot_headers() -> dict[str, str]:
    token = jwt.encode(
        {"iss": "https://api.botframework.com", "aud": BOT_APP_ID, "serviceurl": SERVICE_URL, "exp": int(time.time()) + 600},
        SIGNING_KEY,
        algorithm="RS256",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_activity_with_a_service_url_that_differs_from_the_token_is_rejected(client: httpx.AsyncClient, bot_configured: None) -> None:
    response = await client.post(
        "/api/teams/messages", headers=bot_headers(), json={"type": "message", "serviceUrl": "https://attacker.example/"}
    )
    assert response.status_code == 401


async def test_activity_without_a_service_url_is_rejected(client: httpx.AsyncClient, bot_configured: None) -> None:
    response = await client.post("/api/teams/messages", headers=bot_headers(), json={"type": "message"})
    assert response.status_code == 401

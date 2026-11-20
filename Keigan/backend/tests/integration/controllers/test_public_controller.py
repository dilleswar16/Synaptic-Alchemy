"""keigan/controllers/public_controller.py: client configuration the sign-in screen reads."""

from __future__ import annotations

import httpx
import pytest

from keigan.config.settings import Settings
from keigan.controllers import public_controller


async def test_client_configuration_asks_the_browser_for_the_scope_the_api_requires(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    entra_settings = Settings(
        _env_file=None,
        environment="dev",
        auth_mode="entra",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_api_client_id="22222222-2222-2222-2222-222222222222",
        entra_required_delegated_scope="keigan.use",
        local_token_signing_secret="a-long-random-value-that-is-not-the-default-0123456789",
        local_secret_encryption_key="a-long-random-value-that-is-not-the-default-0123456789",
    )
    monkeypatch.setattr(public_controller, "get_settings", lambda: entra_settings)
    response = await client.get("/api/public/client-configuration")
    assert response.json()["entra"]["apiScope"] == "api://22222222-2222-2222-2222-222222222222/keigan.use"

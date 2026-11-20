"""Fixtures shared by integration tests."""

from __future__ import annotations

import httpx
import pytest

from support import users
from support.alerts import AlertSourceFixture
from support.http import AuthHeaders


@pytest.fixture(scope="session")
async def alert_source(client: httpx.AsyncClient, auth_headers: AuthHeaders, seed_context) -> AlertSourceFixture:
    """A generic alert source on CLMJP, created through the API by its application admin."""
    clmjp = seed_context.application_ids_by_code["CLMJP"]
    response = await client.post(
        f"/api/applications/{clmjp}/alert-sources",
        headers=await auth_headers(users.CLMJP_ADMIN_CHAD_READER),
        json={"sourceTool": "generic", "sourceName": "Pytest generic source"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return AlertSourceFixture(alert_source_id=body["alertSource"]["alertSourceId"], webhook_secret=body["webhookSecret"], application_id=clmjp)

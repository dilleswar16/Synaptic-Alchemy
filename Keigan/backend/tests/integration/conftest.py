"""Fixtures shared by integration tests."""

from __future__ import annotations

import httpx
import pytest

from keigan.config import application_context
from keigan.services.ask_keigan_interruption import RunInterruption
from support import users
from support.alerts import AlertSourceFixture
from support.http import AuthHeaders


@pytest.fixture(autouse=True)
async def no_answer_outlives_its_test() -> None:
    """Answers run as detached tasks that outlive their request, and ``ASGITransport`` never runs the app lifespan that ends them at shutdown, so an answer a test left running
    (a stopped stream, a blocked model turn) would still hold the database and the shared event loop in a later test. After every test the live answers of this process are ended
    the way a shutdown ends them: the tasks are cancelled and awaited, and their runs are marked interrupted."""
    yield
    await RunInterruption(application_context.answer_run_registry()).interrupt_live_runs()


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

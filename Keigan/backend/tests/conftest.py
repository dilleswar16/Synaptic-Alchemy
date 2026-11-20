"""Shared fixtures for the whole suite.

Every test session gets its own SQLite database and data directory in a temporary folder, seeded once with the
foundation demo applications (CLMJP, CHAD, PAYAU, PADMF, BENSA). The environment is set before any ``keigan`` import
because settings and the database engine are cached on first use; these values override ``backend/.env``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="keigan-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "AUTH_MODE": "local",
        "LLM_PROVIDER": "mock",
        "TELEMETRY_MODE": "simulated",
        "SERVICENOW_MODE": "simulated",
        "TEAMS_MODE": "simulated",
        "EMAIL_MODE": "simulated",
        "RUN_WORKERS_IN_PROCESS": "false",
        "AUTO_CREATE_SCHEMA": "false",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_TEST_ROOT / 'keigan-test.db').as_posix()}",
        "DATA_DIRECTORY": str(_TEST_ROOT / "data"),
        "LOCAL_TOKEN_SIGNING_SECRET": "test-only-signing-secret-0123456789abcdef0123456789",
        "LOCAL_SECRET_ENCRYPTION_KEY": "test-only-local-secret-encryption-key",
        "LOG_LEVEL": "WARNING",
    }
)

from collections.abc import AsyncIterator  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from keigan.config.database_config import create_database_schema, open_session  # noqa: E402
from keigan.seed.foundation_seed import SeedContext, seed_demo_applications  # noqa: E402
from support.http import AuthHeaders  # noqa: E402


@pytest.fixture(scope="session")
async def seed_context() -> SeedContext:
    """Schema plus the five demo applications. ``seed_context.application_ids_by_code["CLMJP"]`` etc."""
    await create_database_schema()
    context = SeedContext()
    async with open_session() as session:
        await seed_demo_applications(session, context)
    return context


@pytest.fixture(scope="session")
async def client(seed_context: SeedContext) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client calling the real FastAPI app in-process (no server, no workers)."""
    from keigan.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture(scope="session")
def auth_headers(client: httpx.AsyncClient) -> AuthHeaders:
    """``await auth_headers(users.NO_ACCESS)`` → ``{"Authorization": "Bearer ..."}`` (one sign-in per user per session)."""
    tokens: dict[str, str] = {}

    async def build(user_principal_name: str) -> dict[str, str]:
        if user_principal_name not in tokens:
            response = await client.post("/api/auth/local-sign-in", json={"userPrincipalName": user_principal_name})
            assert response.status_code == 200, response.text
            tokens[user_principal_name] = response.json()["accessToken"]
        return {"Authorization": f"Bearer {tokens[user_principal_name]}"}

    return build

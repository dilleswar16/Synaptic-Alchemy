"""keigan/services/topology_service.py: when the AI build fails, the deterministic graph is still built and the failure is logged."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from keigan.config import application_context
from keigan.config.database_config import open_session
from keigan.services.topology_service import TopologyService


async def test_a_failed_ai_build_falls_back_to_the_deterministic_graph_and_logs_a_warning_that_names_the_application(seed_context, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    application_id = seed_context.application_ids_by_code["CLMJP"]

    class LiveGateway:
        is_mock = False

        def model_name_for(self, model_tier: object) -> str:
            return "test-model"

    async def unavailable(self: TopologyService, *arguments: object) -> None:
        raise RuntimeError("model timed out")

    monkeypatch.setattr(application_context, "llm_gateway", lambda: LiveGateway())
    monkeypatch.setattr(TopologyService, "_build_with_ai", unavailable)
    async with open_session() as session:
        result = await TopologyService(session).build_topology(application_id, "aiko.appadmin@keigan.local")
    assert result is not None
    assert any(record.levelno == logging.WARNING and application_id in record.getMessage() for record in caplog.records)

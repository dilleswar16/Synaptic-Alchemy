"""keigan/controllers/administration_controller.py: the settings page also shows the AI models' resolved capabilities and the last conformance report (spec 23, phase 4 row 4.5)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from keigan.config.settings import get_settings
from support import users
from support.http import AuthHeaders


async def read_settings(client: httpx.AsyncClient, auth_headers: AuthHeaders, user: str = users.KEIGAN_ADMIN) -> httpx.Response:
    return await client.get("/api/administration/settings", headers=await auth_headers(user))


async def test_an_administrator_sees_the_capabilities_of_every_model_tier(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    response = await read_settings(client, auth_headers)
    assert response.status_code == 200, response.text
    capabilities = response.json()["modelCapabilities"]
    assert [item["modelTier"] for item in capabilities] == ["fast", "deep", "vision"]
    assert all(item["toolCalling"] in {"native", "prompted_json", "none"} and item["maxContextTokens"] > 0 for item in capabilities)


async def test_a_person_who_is_not_an_administrator_is_refused(client: httpx.AsyncClient, auth_headers: AuthHeaders) -> None:
    assert (await read_settings(client, auth_headers, users.NO_ACCESS)).status_code == 403


async def test_without_a_conformance_report_the_page_has_none(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(get_settings(), "ask_keigan_conformance_report_path", tmp_path / "none.json")
    assert (await read_settings(client, auth_headers)).json()["lastConformanceReport"] is None


async def test_the_last_conformance_report_is_summarised(client: httpx.AsyncClient, auth_headers: AuthHeaders, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "generatedAt": "2026-11-23T05:00:00+00:00", "passed": True, "providerName": "gemini", "modelName": "gemini-2.5-pro", "toolCallingMode": "native",
        "summary": {"scenarioCount": 11, "passedCount": 11},
    }), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "ask_keigan_conformance_report_path", report_path)
    report = (await read_settings(client, auth_headers)).json()["lastConformanceReport"]
    assert (report["providerName"], report["modelName"], report["toolCallingMode"], report["scenarioCount"], report["passedCount"], report["passed"]) == ("gemini", "gemini-2.5-pro", "native", 11, 11, True)

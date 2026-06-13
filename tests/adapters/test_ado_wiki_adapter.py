"""
Unit tests for ADOWikiAdapter.

All HTTP calls are intercepted with fake httpx.Client subclasses —
no real Azure DevOps calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from corvin.core.contracts import (
    EvidenceBundle,
    FixAction,
    FixStrategyOutput,
    InvestigationRequest,
    InvestigationResult,
    RCAConfidence,
    RCAOutput,
    RiskLevel,
    TriggerSource,
)
from corvin.delivery.ado_wiki_adapter import ADOWikiAdapter, _build_wiki_content


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_result(service: str = "fundsso", env: str = "production") -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name=service,
        environment=env,
        description="test",
    )
    return InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=EvidenceBundle(request_id=req.id),
        rca=RCAOutput(
            request_id=req.id,
            summary="Connection pool exhausted.",
            root_cause="Database max_connections too low after scaling.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=req.id,
            summary="Increase DB connection pool.",
            justification="Root cause is pool limit.",
            actions=[
                FixAction(
                    title="Increase max_connections to 200",
                    description="Update postgres.conf and restart.",
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Eliminates pool exhaustion.",
                    requires_approval=True,
                )
            ],
        ),
    )


def _make_config(wiki_enabled: bool = True, wiki_id: str = "test-wiki-id") -> dict:
    return {
        "wiki_enabled": wiki_enabled,
        "org_name": "TestOrg",
        "project_name": "TestProject",
        "pat": "fake-pat",
        "wiki_id": wiki_id,
    }


# ── Content builder tests ─────────────────────────────────────────────────────


def test_build_wiki_content_contains_service_name() -> None:
    result = _make_result(service="fundsso")
    content = _build_wiki_content(result)
    assert "fundsso" in content


def test_build_wiki_content_contains_root_cause() -> None:
    result = _make_result()
    content = _build_wiki_content(result)
    assert "Database max_connections too low" in content


def test_build_wiki_content_contains_fix_action() -> None:
    result = _make_result()
    content = _build_wiki_content(result)
    assert "Increase max_connections to 200" in content


def test_build_wiki_content_contains_confidence() -> None:
    result = _make_result()
    content = _build_wiki_content(result)
    assert "HIGH" in content


def test_build_wiki_content_contains_corvin_footer() -> None:
    result = _make_result()
    content = _build_wiki_content(result)
    assert "Corvin AI SRE Co-Pilot" in content


def test_build_wiki_content_contains_environment() -> None:
    result = _make_result(env="staging")
    content = _build_wiki_content(result)
    assert "staging" in content


# ── Disabled / misconfigured guard tests ─────────────────────────────────────


def test_publish_returns_none_when_wiki_disabled() -> None:
    cfg = _make_config(wiki_enabled=False)
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()
    assert adapter.publish_investigation(result) is None


def test_publish_returns_none_when_pat_missing() -> None:
    cfg = _make_config()
    cfg["pat"] = ""
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()
    assert adapter.publish_investigation(result) is None


def test_publish_returns_none_when_org_missing() -> None:
    cfg = _make_config()
    cfg["org_name"] = ""
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()
    assert adapter.publish_investigation(result) is None


def test_publish_returns_none_when_wiki_id_missing() -> None:
    cfg = _make_config()
    cfg["wiki_id"] = ""
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()
    assert adapter.publish_investigation(result) is None


# ── HTTP interaction tests ────────────────────────────────────────────────────


def test_publish_returns_url_on_success() -> None:
    cfg = _make_config(wiki_id="my-wiki")
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result(service="fundsso", env="production")

    fake_get = MagicMock()
    fake_get.status_code = 200  # parent page exists

    fake_put = MagicMock()
    fake_put.status_code = 201

    fake_client = MagicMock()
    fake_client.__enter__ = lambda s: s
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get.return_value = fake_get
    fake_client.put.return_value = fake_put

    with patch("corvin.delivery.ado_wiki_adapter.httpx.Client", return_value=fake_client):
        url = adapter.publish_investigation(result)

    assert url is not None
    assert "TestOrg" in url
    assert "TestProject" in url
    assert "my-wiki" in url
    assert result.request_id in url


def test_publish_calls_put_with_markdown_content() -> None:
    cfg = _make_config(wiki_id="my-wiki")
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()

    fake_get = MagicMock()
    fake_get.status_code = 200

    fake_put = MagicMock()
    fake_put.status_code = 201

    fake_client = MagicMock()
    fake_client.__enter__ = lambda s: s
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get.return_value = fake_get
    fake_client.put.return_value = fake_put

    with patch("corvin.delivery.ado_wiki_adapter.httpx.Client", return_value=fake_client):
        adapter.publish_investigation(result)

    # put should have been called with a payload containing 'content'
    call_kwargs = fake_client.put.call_args
    assert call_kwargs is not None
    body = call_kwargs.kwargs.get("json") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
    assert body is not None
    assert "content" in body
    assert "fundsso" in body["content"]


def test_publish_returns_none_on_http_error() -> None:
    cfg = _make_config(wiki_id="my-wiki")
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()

    fake_get = MagicMock()
    fake_get.status_code = 200

    fake_put = MagicMock()
    fake_put.status_code = 500
    fake_put.text = "Internal Server Error"

    fake_client = MagicMock()
    fake_client.__enter__ = lambda s: s
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get.return_value = fake_get
    fake_client.put.return_value = fake_put

    with patch("corvin.delivery.ado_wiki_adapter.httpx.Client", return_value=fake_client):
        url = adapter.publish_investigation(result)

    assert url is None


def test_publish_returns_none_on_exception() -> None:
    cfg = _make_config(wiki_id="my-wiki")
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()

    with patch(
        "corvin.delivery.ado_wiki_adapter.httpx.Client",
        side_effect=RuntimeError("network error"),
    ):
        url = adapter.publish_investigation(result)

    assert url is None


# ── Auto wiki_id resolution tests ─────────────────────────────────────────────


def test_publish_auto_resolves_wiki_id() -> None:
    cfg = _make_config(wiki_id="auto")
    adapter = ADOWikiAdapter(config=cfg)
    result = _make_result()

    fake_list_resp = MagicMock()
    fake_list_resp.status_code = 200
    fake_list_resp.json.return_value = {"value": [{"id": "resolved-wiki-id"}]}

    fake_get = MagicMock()
    fake_get.status_code = 200

    fake_put = MagicMock()
    fake_put.status_code = 201

    fake_client = MagicMock()
    fake_client.__enter__ = lambda s: s
    fake_client.__exit__ = MagicMock(return_value=False)
    # First GET is the wiki list, subsequent GETs are parent-page checks
    fake_client.get.side_effect = [fake_list_resp, fake_get]
    fake_client.put.return_value = fake_put

    with patch("corvin.delivery.ado_wiki_adapter.httpx.Client", return_value=fake_client):
        url = adapter.publish_investigation(result)

    assert url is not None
    assert "resolved-wiki-id" in url


# ── rca_notification integration ─────────────────────────────────────────────


def test_publish_wiki_page_if_enabled_returns_none_when_disabled() -> None:
    from corvin.delivery.rca_notification import publish_wiki_page_if_enabled

    result = _make_result()
    with patch(
        "corvin.delivery.rca_notification.resolve_ado_wiki_config_for_service",
        return_value=None,
    ):
        url = publish_wiki_page_if_enabled(result)

    assert url is None


def test_publish_wiki_page_if_enabled_calls_adapter() -> None:
    from corvin.delivery.rca_notification import publish_wiki_page_if_enabled

    result = _make_result()
    fake_cfg = {
        "org_name": "Org",
        "project_name": "Proj",
        "pat": "pat",
        "wiki_id": "wid",
    }
    with (
        patch(
            "corvin.delivery.rca_notification.resolve_ado_wiki_config_for_service",
            return_value=fake_cfg,
        ),
        patch(
            "corvin.delivery.ado_wiki_adapter.ADOWikiAdapter.publish_investigation",
            return_value="https://fake-wiki-url",
        ),
    ):
        url = publish_wiki_page_if_enabled(result)

    assert url == "https://fake-wiki-url"

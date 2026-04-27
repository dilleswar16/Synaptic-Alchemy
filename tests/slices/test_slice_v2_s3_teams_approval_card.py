"""
V2 Slice 3 – Teams Adaptive Card with Approve / Reject buttons.

Validates that TeamsAdapter._build_card injects two Action.OpenUrl buttons
into the Adaptive Card ``actions`` array, pointing to the correct investigation
detail URLs built from the configured ``web_base_url``.

No real Teams webhook is called — all tests work on the card dict directly
or via mocked httpx.  All existing Slice 10 TeamsAdapter tests remain valid.
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
from corvin.delivery.teams_adapter import TeamsAdapter

# ── Constants ─────────────────────────────────────────────────────────────────

_WEB_BASE = "https://corvin.example.com"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_adapter(web_base_url: str = _WEB_BASE) -> TeamsAdapter:
    return TeamsAdapter(
        config={
            "enabled": True,
            "webhook_url": "https://placeholder.webhook.office.com/wh",
            "web_base_url": web_base_url,
        }
    )


def _make_result() -> InvestigationResult:
    req = InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_API,
        service_name="order-service",
        environment="production",
        description="Spike in 5xx errors",
    )
    return InvestigationResult(
        request_id=req.id,
        request=req,
        evidence=EvidenceBundle(request_id=req.id),
        rca=RCAOutput(
            request_id=req.id,
            summary="Heap exhaustion in order-service.",
            root_cause="JVM heap set too low.",
            confidence=RCAConfidence.HIGH,
        ),
        fix_strategy=FixStrategyOutput(
            request_id=req.id,
            summary="Increase JVM heap and redeploy.",
            justification="Root cause maps to JVM config.",
            actions=[
                FixAction(
                    title="Increase -Xmx to 2g",
                    description="Update JVM_OPTS env var.",
                    risk_level=RiskLevel.LOW,
                    estimated_impact="Eliminates OOM errors.",
                    requires_approval=True,
                )
            ],
        ),
    )


def _card_content(result: InvestigationResult | None = None, adapter: TeamsAdapter | None = None) -> dict:
    """Return the Adaptive Card content dict from _build_card."""
    r = result or _make_result()
    a = adapter or _make_adapter()
    payload = a._build_card(r)
    return payload["attachments"][0]["content"]


# ── actions array presence ────────────────────────────────────────────────────


def test_card_content_has_actions_key():
    """Adaptive Card content must have a top-level 'actions' key."""
    assert "actions" in _card_content()


def test_card_has_exactly_two_actions():
    """There must be exactly two actions: Approve and Reject."""
    assert len(_card_content()["actions"]) == 2


# ── action types ──────────────────────────────────────────────────────────────


def test_approve_action_type_is_action_open_url():
    assert _card_content()["actions"][0]["type"] == "Action.OpenUrl"


def test_reject_action_type_is_action_open_url():
    assert _card_content()["actions"][1]["type"] == "Action.OpenUrl"


# ── button styles ─────────────────────────────────────────────────────────────


def test_approve_action_has_positive_style():
    assert _card_content()["actions"][0]["style"] == "positive"


def test_reject_action_has_destructive_style():
    assert _card_content()["actions"][1]["style"] == "destructive"


# ── button titles ─────────────────────────────────────────────────────────────


def test_approve_action_title_contains_approve():
    assert "approve" in _card_content()["actions"][0]["title"].lower()


def test_reject_action_title_contains_reject():
    assert "reject" in _card_content()["actions"][1]["title"].lower()


# ── URL correctness ───────────────────────────────────────────────────────────


def test_approve_url_contains_request_id():
    result = _make_result()
    content = _card_content(result=result)
    assert result.request_id in content["actions"][0]["url"]


def test_reject_url_contains_request_id():
    result = _make_result()
    content = _card_content(result=result)
    assert result.request_id in content["actions"][1]["url"]


def test_approve_url_contains_action_approve_param():
    assert "action=approve" in _card_content()["actions"][0]["url"]


def test_reject_url_contains_action_reject_param():
    assert "action=reject" in _card_content()["actions"][1]["url"]


def test_custom_web_base_url_reflected_in_both_button_urls():
    adapter = _make_adapter("https://corvin.mycompany.com")
    content = _card_content(adapter=adapter)
    assert content["actions"][0]["url"].startswith("https://corvin.mycompany.com")
    assert content["actions"][1]["url"].startswith("https://corvin.mycompany.com")


def test_trailing_slash_on_web_base_url_produces_clean_url():
    """A trailing slash in web_base_url must not create a double slash in the URL."""
    adapter = _make_adapter("https://corvin.mycompany.com/")
    content = _card_content(adapter=adapter)
    # Strip the scheme so we only check the path part
    for action in content["actions"]:
        path_part = action["url"].replace("https://", "")
        assert "//" not in path_part, f"Double slash found in URL: {action['url']}"


def test_default_web_base_url_fallback_is_localhost_5173():
    """When web_base_url is absent from config the fallback is localhost:5173."""
    adapter = TeamsAdapter(config={"enabled": True, "webhook_url": "https://wh.example.com"})
    content = _card_content(adapter=adapter)
    assert "localhost:5173" in content["actions"][0]["url"]
    assert "localhost:5173" in content["actions"][1]["url"]


# ── card body still intact ────────────────────────────────────────────────────


def test_card_body_still_contains_service_name():
    """Adding actions must not remove the existing body content."""
    result = _make_result()
    content = _card_content(result=result)
    body_text = str(content["body"])
    assert result.request.service_name in body_text


def test_card_body_still_contains_rca_summary():
    result = _make_result()
    content = _card_content(result=result)
    body_text = str(content["body"])
    assert "Heap exhaustion in order-service." in body_text


# ── warning text block ────────────────────────────────────────────────────────


def test_card_body_contains_review_warning():
    """The card must include a warning TextBlock above the action buttons."""
    content = _card_content()
    warning_texts = [
        b.get("text", "")
        for b in content["body"]
        if b.get("type") == "TextBlock" and b.get("color") == "Warning"
    ]
    assert len(warning_texts) >= 1, "Expected at least one Warning-coloured TextBlock"
    assert any("review" in t.lower() for t in warning_texts)


# ── send_result integration (button URLs flow through to httpx) ───────────────


def test_send_result_posts_card_with_actions():
    """send_result must POST a payload that includes the actions array."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    adapter = _make_adapter()
    result = _make_result()

    with patch("corvin.delivery.teams_adapter.httpx.post", return_value=mock_response) as mock_post:
        adapter.send_result(result)

    payload = mock_post.call_args.kwargs["json"]
    card_content = payload["attachments"][0]["content"]
    assert "actions" in card_content
    assert len(card_content["actions"]) == 2
    assert card_content["actions"][0]["type"] == "Action.OpenUrl"

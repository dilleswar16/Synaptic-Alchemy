"""
Teams delivery adapter.

Posts investigation results to a Microsoft Teams channel via incoming webhook.
Config is loaded from config/integrations/teams.yaml.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult

_log = logging.getLogger(__name__)


class TeamsAdapter:
    """Delivers InvestigationResult cards to a Microsoft Teams channel."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = (
            config if config is not None else load_config("integrations/teams", get_env())
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_card(self, result: InvestigationResult) -> dict[str, Any]:
        """Construct a Teams Adaptive Card payload for *result*.

        The card includes two ``Action.OpenUrl`` buttons — Approve and Reject —
        that link to the Corvin web app's investigation detail page with an
        ``?action=approve`` / ``?action=reject`` query param.  The web app then
        presents a confirmation dialog before POSTing to the approval API.

        ``web_base_url`` is read from config (env: ``CORVIN_WEB_BASE_URL``).
        Trailing slashes are stripped to avoid double-slash URLs.
        """
        web_base_url = self._config.get("web_base_url", "http://localhost:5173").rstrip("/")
        approve_url = f"{web_base_url}/investigations/{result.request_id}?action=approve"
        reject_url = f"{web_base_url}/investigations/{result.request_id}?action=reject"

        confidence = result.rca.confidence.value if result.rca else "unknown"
        actions_text = (
            "\n".join(
                f"• [{a.risk_level.value.upper()}] {a.title}"
                for a in result.fix_strategy.actions
            )
            if result.fix_strategy and result.fix_strategy.actions
            else "No specific actions proposed."
        )
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "Corvin — Investigation Complete",
                                "weight": "Bolder",
                                "size": "Large",
                                "color": "Accent",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Service", "value": result.request.service_name},
                                    {"title": "Environment", "value": result.request.environment},
                                    {"title": "Trigger", "value": result.request.trigger_source.value},
                                    {"title": "Confidence", "value": confidence.upper()},
                                    {"title": "Request ID", "value": result.request_id},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": "Root Cause Analysis",
                                "weight": "Bolder",
                                "separator": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": result.rca.summary if result.rca else "(not available)",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Fix Strategy",
                                "weight": "Bolder",
                                "separator": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": result.fix_strategy.summary if result.fix_strategy else "(not available)",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Recommended Actions",
                                "weight": "Bolder",
                                "separator": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": actions_text,
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "⚠️ Review the full investigation detail before approving.",
                                "wrap": True,
                                "color": "Warning",
                                "size": "Small",
                                "separator": True,
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "✅ Approve",
                                "url": approve_url,
                                "style": "positive",
                            },
                            {
                                "type": "Action.OpenUrl",
                                "title": "❌ Reject",
                                "url": reject_url,
                                "style": "destructive",
                            },
                        ],
                    },
                }
            ],
        }

    # ── Public interface ──────────────────────────────────────────────────────

    def send_result(self, result: InvestigationResult) -> None:
        """
        Post an Adaptive Card for *result* to the configured Teams webhook.

        Skips silently when ``enabled: false`` in config.
        Raises ``ValueError`` when ``webhook_url`` is missing or unresolved.
        Raises ``httpx.HTTPError`` on network or HTTP-level failures.
        """
        if not self._config.get("enabled", True):
            return

        webhook_url: str = self._config.get("webhook_url", "")
        if not webhook_url or webhook_url.startswith("${"):
            raise ValueError(
                "TeamsAdapter: webhook_url is not configured. "
                "Set TEAMS_WEBHOOK_URL in your environment or config/integrations/teams.yaml."
            )

        card = self._build_card(result)
        response = httpx.post(webhook_url, json=card, timeout=10)
        response.raise_for_status()
        _log.info(
            "Teams card delivered for request_id=%s (status=%s)",
            result.request_id,
            response.status_code,
        )

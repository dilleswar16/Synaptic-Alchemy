"""Teams delivery adapter.

Posts investigation results to Microsoft Teams using an app-scoped outbound
connector (connector_type=teams_webhook) resolved from DB at runtime.
Falls back to environment variables for legacy/bootstrap scenarios.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from corvin.connectors.config_resolver import resolve_outbound_connector_config
from corvin.core.contracts import InvestigationResult
from corvin.strategy.blast_radius import BlastRadiusEstimate, estimate_blast_radius
from corvin.core.config_loader import get_env, load_config

_log = logging.getLogger(__name__)


def _env_default_config() -> dict[str, Any]:
    webhook = str(os.environ.get("TEAMS_WEBHOOK_URL", "")).strip()
    enabled_raw = str(os.environ.get("TEAMS_ENABLED", "")).strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"} if enabled_raw else bool(webhook)
    return {
        "enabled": enabled,
        "endpoint": webhook,
        "web_base_url": str(os.environ.get("CORVIN_WEB_BASE_URL", "http://localhost:5173")).strip() or "http://localhost:5173",
        "auth": {"type": "none"},
    }


class TeamsAdapter:
    """Delivers InvestigationResult cards to a Microsoft Teams channel."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else _env_default_config()

    def _resolved_config(self, service_name: str) -> dict[str, Any]:
        cfg = resolve_outbound_connector_config(
            service_name,
            connector_type="teams_webhook",
            fallback=self._config,
        )
        return cfg or dict(self._config)

    def _build_card(
        self,
        result: InvestigationResult,
        blast: BlastRadiusEstimate | None = None,
        *,
        web_base_url: str,
    ) -> dict[str, Any]:
        """Construct a Teams Adaptive Card payload for *result*."""
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

        blast_blocks: list[dict[str, Any]] = []
        if blast is not None:
            severity_colour = {
                "critical": "Attention",
                "high": "Warning",
                "medium": "Warning",
                "low": "Good",
            }.get(getattr(blast, "severity", "medium"), "Warning")

            blast_blocks = [
                {
                    "type": "TextBlock",
                    "text": "Blast Radius Estimate",
                    "weight": "Bolder",
                    "separator": True,
                    "color": severity_colour,
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Affected Services", "value": str(len(blast.affected_services))},
                        {"title": "Estimated Users", "value": f"~{blast.estimated_users:,}"},
                        {
                            "title": "Revenue Risk/min",
                            "value": f"{blast.currency} {blast.revenue_risk_per_min:,.2f}",
                        },
                        {"title": "Replicas (AKS)", "value": str(blast.replica_count)},
                        {"title": "How Estimated", "value": blast.rationale},
                    ],
                },
            ]

        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "Corvin - Investigation Complete",
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
            *blast_blocks,
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
                "text": "Review the full investigation detail before approving.",
                "wrap": True,
                "color": "Warning",
                "size": "Small",
                "separator": True,
            },
        ]

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
                        "body": body,
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "Approve",
                                "url": approve_url,
                                "style": "positive",
                            },
                            {
                                "type": "Action.OpenUrl",
                                "title": "Reject",
                                "url": reject_url,
                                "style": "destructive",
                            },
                        ],
                    },
                }
            ],
        }

    def send_result(self, result: InvestigationResult) -> None:
        """Post an Adaptive Card for *result* to a Teams outbound connector."""
        cfg = self._resolved_config(result.request.service_name)
        enabled = bool(cfg.get("enabled", True))
        if not enabled:
            return

        endpoint = str(cfg.get("endpoint") or cfg.get("webhook_url") or "").strip()
        if not endpoint or endpoint.startswith("${"):
            raise ValueError(
                "TeamsAdapter: webhook_url is not configured. Configure a teams_webhook outbound connector."
            )

        web_base_url = str(cfg.get("web_base_url", self._config.get("web_base_url", "http://localhost:5173"))).rstrip("/")

        blast: BlastRadiusEstimate | None = None
        try:
            policy = load_config("policies/investigation", get_env())
            blast = estimate_blast_radius(
                service_name=result.request.service_name,
                environment=result.request.environment,
                evidence=result.evidence,
                policy=policy,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("Blast radius computation failed (non-fatal): %s", exc)

        card = self._build_card(result, blast=blast, web_base_url=web_base_url)
        response = httpx.post(endpoint, json=card, timeout=10)
        response.raise_for_status()
        _log.info(
            "Teams card delivered for request_id=%s (status=%s)",
            result.request_id,
            response.status_code,
        )

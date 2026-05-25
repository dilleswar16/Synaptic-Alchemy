"""
SharePoint Adapter — uploads RCA PDF + markdown to a SharePoint document library.

Uses Microsoft Graph API with client-credentials (app-only) auth.
The same Azure AD app registration used for War Room (MICROSOFT_GRAPH_CLIENT_ID)
can be reused if Sites.ReadWrite.All permission is granted.

Config lives in config/integrations/sharepoint.yaml.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from corvin.core.contracts import InvestigationResult

logger = logging.getLogger(__name__)


def _safe_filename(value: str) -> str:
    """Sanitise a string for use as a SharePoint filename."""
    import re
    value = re.sub(r'[<>:"/\\|?*]', "", value)
    return value.strip().replace(" ", "_")[:80]


class SharePointAdapter:
    """Uploads investigation reports to a SharePoint document library via Graph API."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._enabled: bool = config.get("enabled", False)
        self._tenant_id: str = os.environ.get(
            "MICROSOFT_GRAPH_TENANT_ID",
            os.environ.get("AZURE_TENANT_ID", ""),
        )
        self._client_id: str = os.environ.get("MICROSOFT_GRAPH_CLIENT_ID", "")
        self._client_secret: str = os.environ.get("MICROSOFT_GRAPH_CLIENT_SECRET", "")
        self._site_id: str = config.get("site_id", "")
        self._drive_id: str = config.get("drive_id", "")
        self._folder_path: str = config.get("folder_path", "Corvin/Investigations")

    def _is_configured(self) -> bool:
        if not self._enabled:
            return False
        missing = [k for k, v in {
            "tenant_id": self._tenant_id,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "site_id": self._site_id,
        }.items() if not v or v.startswith("${") or v == "placeholder"]
        if missing:
            logger.warning("SharePointAdapter: missing config: %s", missing)
            return False
        return True

    def _get_access_token(self, client: httpx.Client) -> Optional[str]:
        """Acquire an app-only access token via client credentials flow."""
        url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        resp = client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "https://graph.microsoft.com/.default",
        })
        if resp.status_code != 200:
            logger.warning("SharePointAdapter: token request failed: %s %s", resp.status_code, resp.text[:200])
            return None
        return resp.json().get("access_token")

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _resolve_drive_id(self, client: httpx.Client, token: str) -> Optional[str]:
        """If drive_id is not configured, use the site's default document library."""
        if self._drive_id and self._drive_id.lower() != "auto":
            return self._drive_id
        url = f"https://graph.microsoft.com/v1.0/sites/{self._site_id}/drive"
        resp = client.get(url, headers=self._headers(token))
        if resp.status_code == 200:
            drive_id = resp.json().get("id")
            logger.info("SharePointAdapter: auto-resolved drive_id = %s", drive_id)
            return drive_id
        logger.warning("SharePointAdapter: could not resolve drive: %s", resp.text[:200])
        return None

    def upload_investigation(
        self,
        result: InvestigationResult,
        pdf_bytes: bytes | None = None,
    ) -> Optional[str]:
        """Upload RCA report (PDF + markdown summary) to SharePoint.

        Returns the web URL of the uploaded PDF on success, None on failure.
        """
        if not self._is_configured():
            return None

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        svc = _safe_filename(result.request.service_name)
        env = _safe_filename(result.request.environment)
        folder = f"{self._folder_path}/{date_str}_{svc}_{env}"

        try:
            with httpx.Client(timeout=30) as client:
                token = self._get_access_token(client)
                if not token:
                    return None

                drive_id = self._resolve_drive_id(client, token)
                if not drive_id:
                    return None

                web_url: str | None = None

                # Upload PDF if provided
                if pdf_bytes:
                    pdf_name = f"corvin-rca-{result.request_id[:8]}.pdf"
                    pdf_path = f"{folder}/{pdf_name}"
                    url = (
                        f"https://graph.microsoft.com/v1.0/sites/{self._site_id}"
                        f"/drives/{drive_id}/root:/{pdf_path}:/content"
                    )
                    resp = client.put(
                        url,
                        content=pdf_bytes,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/pdf",
                        },
                    )
                    if resp.status_code in (200, 201):
                        web_url = resp.json().get("webUrl")
                        logger.info("SharePointAdapter: uploaded PDF → %s", web_url)
                    else:
                        logger.warning("SharePointAdapter: PDF upload failed: %s %s", resp.status_code, resp.text[:200])

                # Upload markdown summary
                md_content = self._build_markdown(result)
                md_name = f"corvin-rca-{result.request_id[:8]}.md"
                md_path = f"{folder}/{md_name}"
                md_url = (
                    f"https://graph.microsoft.com/v1.0/sites/{self._site_id}"
                    f"/drives/{drive_id}/root:/{md_path}:/content"
                )
                resp = client.put(
                    md_url,
                    content=md_content.encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "text/markdown",
                    },
                )
                if resp.status_code in (200, 201):
                    if not web_url:
                        web_url = resp.json().get("webUrl")
                    logger.info("SharePointAdapter: uploaded MD → %s", resp.json().get("webUrl"))
                else:
                    logger.warning("SharePointAdapter: MD upload failed: %s %s", resp.status_code, resp.text[:200])

                return web_url

        except Exception as exc:
            logger.warning("SharePointAdapter: upload failed: %s", exc)
            return None

    def _build_markdown(self, result: InvestigationResult) -> str:
        """Build a markdown summary for the SharePoint upload."""
        rca = result.rca
        fix = result.fix_strategy
        confidence = (rca.confidence.value if hasattr(rca.confidence, "value") else str(rca.confidence or "medium")).upper()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"# Corvin RCA — {result.request.service_name} ({result.request.environment})",
            "",
            f"**Generated:** {ts}",
            f"**Investigation ID:** `{result.request_id}`",
            f"**Triggered by:** {result.request.trigger_source.value}",
            f"**Confidence:** {confidence}",
            "",
            "---",
            "",
            "## Root Cause Summary",
            "",
            rca.summary or "_No summary available._",
            "",
            "## Root Cause Detail",
            "",
            rca.root_cause or "_No root cause identified._",
            "",
        ]

        if fix and fix.actions:
            lines += ["## Proposed Fix Actions", ""]
            for i, action in enumerate(fix.actions, 1):
                lines.append(f"### {i}. {action.title}")
                lines.append("")
                lines.append(action.description or "")
                lines.append("")
                if getattr(action, "risk_level", None):
                    lines.append(f"**Risk:** {action.risk_level}")
                    lines.append("")

        lines += ["---", "", "_Generated by Corvin AI SRE Co-Pilot_"]
        return "\n".join(lines)

from __future__ import annotations

import logging
import re
import time
from typing import Iterable, Optional

from corvin.core.contracts import InvestigationResult
from corvin.connectors.secret_ref import resolve_secret_reference
from corvin.connectors.config_resolver import resolve_outbound_connector_config
from corvin.delivery.email_adapter import EmailAdapter, default_email_config
from corvin.delivery.rca_pdf import build_rca_pdf

_log = logging.getLogger(__name__)


_ORG_FROM_URL = re.compile(r"https?://dev\.azure\.com/([^/]+)/?", re.IGNORECASE)


def send_rca_email_if_enabled(
    result: InvestigationResult,
    *,
    recipients: Iterable[str] | None = None,
    force: bool = False,
    ado_work_item_url: str | None = None,
    max_retries: int = 2,
    on_retry: object | None = None,
) -> bool:
    """Best-effort RCA email delivery with PDF attachment.

    Returns True when an email is actually sent, False otherwise.
    Retries up to *max_retries* times with exponential backoff on
    TooManyRequests (HTTP 429) errors.  If *on_retry* is a callable
    it is invoked with ``(attempt: int, wait_secs: float)`` before
    each sleep so the caller can emit progress events.
    Never raises.
    """
    try:
        cfg = default_email_config()
        if not force and not cfg.get("auto_send_on_rca", True):
            return False

        pdf_bytes = build_rca_pdf(result)
        adapter = EmailAdapter(config=cfg)

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 2):  # attempts 1 … max_retries+1
            try:
                return adapter.send_rca_pdf(
                    result,
                    pdf_bytes,
                    recipients=recipients,
                    ado_work_item_url=ado_work_item_url,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                is_throttle = "TooManyRequests" in str(exc) or "429" in str(exc)
                if not is_throttle or attempt > max_retries:
                    break
                wait = min(2 ** attempt, 8)  # 2s, 4s
                _log.info(
                    "Email throttled (attempt %d/%d), retrying in %ds: %s",
                    attempt, max_retries + 1, wait, exc,
                )
                if callable(on_retry):
                    on_retry(attempt, wait)
                time.sleep(wait)

        _log.warning("RCA email delivery failed (non-fatal) for %s: %s", result.request_id, last_exc)
        return False
    except Exception as exc:  # noqa: BLE001
        _log.warning("RCA email delivery failed (non-fatal) for %s: %s", result.request_id, exc)
        return False


def publish_wiki_page_if_enabled(result: InvestigationResult) -> Optional[str]:
    """Best-effort ADO Wiki page creation after an investigation completes.

    Returns the wiki page URL on success, None otherwise.
    Never raises.
    """
    try:
        from corvin.delivery.ado_wiki_adapter import ADOWikiAdapter
        cfg = resolve_ado_wiki_config_for_service(result.request.service_name)
        if not cfg:
            return None
        adapter = ADOWikiAdapter(config=cfg)
        url = adapter.publish_investigation(result)
        if url:
            _log.info("Wiki page published for %s: %s", result.request_id, url)
        return url
    except Exception as exc:  # noqa: BLE001
        _log.warning("Wiki publish failed (non-fatal) for %s: %s", result.request_id, exc)
        return None


def publish_sharepoint_if_enabled(
    result: InvestigationResult,
    pdf_bytes: bytes | None = None,
) -> Optional[str]:
    """Best-effort SharePoint upload after an investigation completes.

    Returns the web URL of the uploaded file on success, None otherwise.
    Never raises.
    """
    try:
        from corvin.delivery.sharepoint_adapter import SharePointAdapter
        cfg = resolve_sharepoint_config_for_service(result.request.service_name)
        if not cfg:
            return None
        adapter = SharePointAdapter(config=cfg)
        url = adapter.upload_investigation(result, pdf_bytes=pdf_bytes)
        if url:
            _log.info("SharePoint upload for %s: %s", result.request_id, url)
        return url
    except Exception as exc:  # noqa: BLE001
        _log.warning("SharePoint upload failed (non-fatal) for %s: %s", result.request_id, exc)
        return None


def resolve_ado_boards_config_for_service(service_name: str) -> dict | None:
    cfg = resolve_outbound_connector_config(service_name, connector_type="azure_devops_boards")
    if not cfg:
        return None
    endpoint = str(cfg.get("endpoint", "")).strip()
    endpoint_fields = cfg.get("endpoint_fields") if isinstance(cfg.get("endpoint_fields"), dict) else {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    org_name = _extract_ado_org_name(endpoint)
    project_name = str(endpoint_fields.get("project_name", "")).strip()
    pat = _extract_secret(auth)
    if not (org_name and project_name and pat):
        return None
    return {
        "enabled": True,
        "org_name": org_name,
        "project_name": project_name,
        "pat": pat,
        "work_item_type": str(endpoint_fields.get("work_item_type", "Issue") or "Issue"),
        "fixed_tags": str(cfg.get("fixed_tags", "corvin") or "corvin"),
        "assignment_routing": cfg.get("assignment_routing", {}),
    }


def resolve_ado_wiki_config_for_service(service_name: str) -> dict | None:
    cfg = resolve_outbound_connector_config(service_name, connector_type="azure_devops_wiki")
    if not cfg:
        return None
    endpoint = str(cfg.get("endpoint", "")).strip()
    endpoint_fields = cfg.get("endpoint_fields") if isinstance(cfg.get("endpoint_fields"), dict) else {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    org_name = _extract_ado_org_name(endpoint)
    project_name = str(endpoint_fields.get("project_name", "")).strip()
    wiki_id = str(endpoint_fields.get("wiki_id", "")).strip()
    pat = _extract_secret(auth)
    if not (org_name and project_name and wiki_id and pat):
        return None
    return {
        "wiki_enabled": True,
        "org_name": org_name,
        "project_name": project_name,
        "wiki_id": wiki_id,
        "pat": pat,
    }


def resolve_sharepoint_config_for_service(service_name: str) -> dict | None:
    cfg = resolve_outbound_connector_config(service_name, connector_type="sharepoint")
    if not cfg:
        return None
    endpoint_fields = cfg.get("endpoint_fields") if isinstance(cfg.get("endpoint_fields"), dict) else {}
    auth = cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {}
    site_id = str(endpoint_fields.get("site_id", "")).strip()
    if not site_id:
        return None
    out = {
        "enabled": True,
        "site_id": site_id,
        "drive_id": str(endpoint_fields.get("drive_id", "auto") or "auto"),
        "folder_path": str(endpoint_fields.get("folder_path", "Corvin/Investigations") or "Corvin/Investigations"),
    }
    if auth:
        out["auth"] = auth
    return out


def _extract_ado_org_name(endpoint: str) -> str:
    m = _ORG_FROM_URL.match(endpoint)
    return m.group(1).strip() if m else ""


def _extract_secret(auth: dict) -> str:
    value = str(
        auth.get("bearer_token")
        or auth.get("api_key")
        or auth.get("password")
        or ""
    ).strip()
    if value:
        return value

    ref = str(
        auth.get("bearer_token_ref")
        or auth.get("api_key_ref")
        or auth.get("password_ref")
        or ""
    ).strip()
    return str(resolve_secret_reference(ref) or "").strip()

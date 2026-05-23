from __future__ import annotations

import logging
import time
from typing import Iterable, Optional

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult
from corvin.delivery.email_adapter import EmailAdapter
from corvin.delivery.rca_pdf import build_rca_pdf

_log = logging.getLogger(__name__)


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
        cfg = load_config("integrations/email", get_env())
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
        cfg = load_config("integrations/azure_devops", get_env())
        if not cfg.get("wiki_enabled", False):
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
        cfg = load_config("integrations/sharepoint", get_env())
        if not cfg.get("enabled", False):
            return None
        adapter = SharePointAdapter(config=cfg)
        url = adapter.upload_investigation(result, pdf_bytes=pdf_bytes)
        if url:
            _log.info("SharePoint upload for %s: %s", result.request_id, url)
        return url
    except Exception as exc:  # noqa: BLE001
        _log.warning("SharePoint upload failed (non-fatal) for %s: %s", result.request_id, exc)
        return None

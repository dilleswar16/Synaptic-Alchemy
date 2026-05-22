from __future__ import annotations

import logging
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
) -> bool:
    """Best-effort RCA email delivery with PDF attachment.

    Returns True when an email is actually sent, False otherwise.
    Never raises.
    """
    try:
        cfg = load_config("integrations/email", get_env())
        if not force and not cfg.get("auto_send_on_rca", True):
            return False

        pdf_bytes = build_rca_pdf(result)
        adapter = EmailAdapter(config=cfg)
        return adapter.send_rca_pdf(
            result,
            pdf_bytes,
            recipients=recipients,
            ado_work_item_url=ado_work_item_url,
        )
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

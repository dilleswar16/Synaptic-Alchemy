from __future__ import annotations

import logging
from typing import Iterable

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
        return adapter.send_rca_pdf(result, pdf_bytes, recipients=recipients)
    except Exception as exc:  # noqa: BLE001
        _log.warning("RCA email delivery failed (non-fatal) for %s: %s", result.request_id, exc)
        return False

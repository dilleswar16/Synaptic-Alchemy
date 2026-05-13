from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Iterable

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult

_log = logging.getLogger(__name__)


class EmailAdapter:
    """Delivers RCA reports by SMTP email when enabled in config."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config if config is not None else load_config("integrations/email", get_env())

    def _resolved_recipients(self, recipients: Iterable[str] | None = None) -> list[str]:
        if recipients:
            return [r.strip() for r in recipients if r and r.strip()]

        configured = self._config.get("to_addresses", [])
        if isinstance(configured, str):
            configured = [x.strip() for x in configured.split(",") if x.strip()]
        if not isinstance(configured, list):
            return []
        return [str(x).strip() for x in configured if str(x).strip()]

    def send_rca_pdf(
        self,
        result: InvestigationResult,
        pdf_bytes: bytes,
        *,
        recipients: Iterable[str] | None = None,
    ) -> bool:
        if not self._config.get("enabled", False):
            return False

        recipient_list = self._resolved_recipients(recipients)
        if not recipient_list:
            _log.warning("EmailAdapter: enabled but no recipients configured")
            return False

        host = str(self._config.get("smtp_host", "")).strip()
        port = int(self._config.get("smtp_port", 587))
        username = str(self._config.get("smtp_username", "")).strip()
        password = str(self._config.get("smtp_password", "")).strip()
        from_address = str(self._config.get("from_address", "")).strip()
        use_starttls = bool(self._config.get("use_starttls", True))

        if not host or host.startswith("${"):
            _log.warning("EmailAdapter: smtp_host not configured")
            return False
        if not from_address or from_address.startswith("${"):
            _log.warning("EmailAdapter: from_address not configured")
            return False

        subject_prefix = str(self._config.get("subject_prefix", "[Corvin RCA]")).strip()
        subject = (
            f"{subject_prefix} {result.request.service_name} ({result.request.environment}) "
            f"- {result.rca.confidence.value.upper()}"
        )

        body = (
            "Corvin generated a new RCA report.\n\n"
            f"Request ID: {result.request_id}\n"
            f"Service: {result.request.service_name}\n"
            f"Environment: {result.request.environment}\n"
            f"Confidence: {result.rca.confidence.value.upper()}\n\n"
            "The structured RCA PDF is attached.\n"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_address
        msg["To"] = ", ".join(recipient_list)
        msg.set_content(body)
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"corvin-rca-{result.request_id}.pdf",
        )

        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            if use_starttls:
                smtp.starttls()
                smtp.ehlo()
            if username and password and not username.startswith("${") and not password.startswith("${"):
                smtp.login(username, password)
            smtp.send_message(msg)

        _log.info(
            "RCA email sent for request_id=%s to=%s",
            result.request_id,
            ",".join(recipient_list),
        )
        return True

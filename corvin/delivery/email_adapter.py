from __future__ import annotations

import base64
import logging
import os
from typing import Any, Iterable

from corvin.core.config_loader import get_env, load_config
from corvin.core.contracts import InvestigationResult

_log = logging.getLogger(__name__)


class EmailAdapter:
    """Delivers RCA reports via Azure Communication Services Email SDK."""

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
        ado_work_item_url: str | None = None,
    ) -> bool:
        if not self._config.get("enabled", False):
            return False

        recipient_list = self._resolved_recipients(recipients)
        if not recipient_list:
            _log.warning("EmailAdapter: enabled but no recipients configured")
            return False

        connection_string = os.environ.get("AZURE_COMMUNICATION_CONNECTION_STRING", "").strip()
        from_address = str(self._config.get("from_address", "")).strip()

        if not connection_string or connection_string.startswith("${") or "<your" in connection_string:
            _log.warning("EmailAdapter: AZURE_COMMUNICATION_CONNECTION_STRING not configured")
            return False
        if not from_address or from_address.startswith("${") or "<your" in from_address:
            _log.warning("EmailAdapter: from_address not configured (set CORVIN_EMAIL_FROM)")
            return False

        service = result.request.service_name
        env = result.request.environment
        description = result.request.description or "No description provided."
        root_cause = result.rca.root_cause or "See attached PDF for details."
        confidence = result.rca.confidence.value.upper()

        subject_prefix = str(self._config.get("subject_prefix", "[Corvin RCA]")).strip()
        subject = f"{subject_prefix} {service} ({env}) - {confidence} confidence"

        body_lines = [
            f"A Corvin RCA investigation has completed for {service} in {env}.",
            "",
            f"Description:  {description}",
            f"What Broke:   {root_cause}",
            f"Confidence:   {confidence}",
            "",
        ]
        if ado_work_item_url:
            body_lines += [
                "Azure DevOps Work Item:",
                f"  {ado_work_item_url}",
                "",
            ]
        body_lines += [
            "The full RCA report (root cause, evidence summary, fix strategy) is attached as a PDF.",
            "",
            "--",
            "Corvin AI SRE Co-Pilot",
        ]
        body = "\n".join(body_lines)

        try:
            from azure.communication.email import EmailClient  # type: ignore
        except ImportError:
            _log.warning(
                "EmailAdapter: azure-communication-email not installed. "
                "Run: pip install azure-communication-email"
            )
            return False

        client = EmailClient.from_connection_string(connection_string)
        filename = f"corvin-rca-{result.request_id}.pdf"
        message = {
            "senderAddress": from_address,
            "recipients": {
                "to": [{"address": addr} for addr in recipient_list],
            },
            "content": {
                "subject": subject,
                "plainText": body,
            },
            "attachments": [
                {
                    "name": filename,
                    "contentType": "application/pdf",
                    "contentInBase64": base64.b64encode(pdf_bytes).decode("utf-8"),
                }
            ],
        }

        poller = client.begin_send(message)
        result_acs = poller.result()
        _log.info(
            "RCA email sent for request_id=%s to=%s messageId=%s",
            result.request_id,
            ",".join(recipient_list),
            result_acs.get("id", "unknown"),
        )
        return True
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

        service = result.request.service_name
        env = result.request.environment
        description = result.request.description or "No description provided."
        root_cause = result.rca.root_cause or "See attached PDF for details."
        confidence = result.rca.confidence.value.upper()

        subject_prefix = str(self._config.get("subject_prefix", "[Corvin RCA]")).strip()
        subject = f"{subject_prefix} {service} ({env}) - {confidence} confidence"

        body_lines = [
            f"A Corvin RCA investigation has completed for {service} in {env}.",
            "",
            f"Description:  {description}",
            f"What Broke:   {root_cause}",
            f"Confidence:   {confidence}",
            "",
        ]
        if ado_work_item_url:
            body_lines += [
                "Azure DevOps Work Item:",
                f"  {ado_work_item_url}",
                "",
            ]
        body_lines += [
            "The full RCA report (root cause, evidence summary, fix strategy) is attached as a PDF.",
            "",
            "--",
            "Corvin AI SRE Co-Pilot",
        ]
        body = "\n".join(body_lines)

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

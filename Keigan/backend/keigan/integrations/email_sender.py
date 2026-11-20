"""Plain SMTP delivery (STARTTLS) for ``EMAIL_MODE=smtp``. ``smtplib`` is blocking, so it runs in a worker thread."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from keigan.config.settings import Settings
from keigan.exceptions.keigan_exceptions import IntegrationException
from keigan.integrations.secret_store import SecretStore


class SmtpEmailSender:
    def __init__(self, settings: Settings, secret_store: SecretStore):
        self.settings = settings
        self.secret_store = secret_store

    async def send(self, recipient_address: str, subject_line: str, body_html: str, body_text: str) -> str:
        if not self.settings.smtp_host:
            raise IntegrationException("SMTP_HOST is not configured.", error_code="smtp_not_configured")
        password = await self.secret_store.get_secret_or_none(self.settings.smtp_password_secret_name) if self.settings.smtp_username else None
        message = EmailMessage()
        message["From"], message["To"], message["Subject"], message["Message-ID"] = self.settings.email_from_address, recipient_address, subject_line, make_msgid()
        message.set_content(body_text or subject_line)
        message.add_alternative(body_html, subtype="html")
        await asyncio.to_thread(self._deliver, message, password)
        return str(message["Message-ID"])

    def _deliver(self, message: EmailMessage, password: str | None) -> None:
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp_connection:
                smtp_connection.starttls(context=ssl.create_default_context())
                if self.settings.smtp_username and password:
                    smtp_connection.login(self.settings.smtp_username, password)
                smtp_connection.send_message(message)
        except (smtplib.SMTPException, OSError) as smtp_error:
            raise IntegrationException(f"SMTP delivery failed: {smtp_error}", error_code="smtp_delivery_failed") from smtp_error

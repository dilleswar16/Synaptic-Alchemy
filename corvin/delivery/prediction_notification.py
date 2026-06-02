"""Send email notifications when Predictive Analysis detects potential failures.

Looks up notification contacts for the application owning the service,
filters by priority, and dispatches warning emails via EmailAdapter.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import select

from corvin.delivery.email_adapter import default_email_config
from corvin.storage.db import get_session
from corvin.storage.models import (
    ApplicationRow,
    ApplicationServiceRow,
    NotificationContactRow,
)

_log = logging.getLogger(__name__)

_SEVERITY_TO_PRIORITY = {"critical": "p1", "high": "p1", "medium": "p2", "low": "p3"}


def _matches_priority_filter(severity: str, priority_filter: str) -> bool:
    """Return True if the alert severity passes the contact's priority filter."""
    if priority_filter == "all":
        return True
    mapped = _SEVERITY_TO_PRIORITY.get(severity.lower(), "p3")
    if priority_filter == "p1_only":
        return mapped == "p1"
    if priority_filter == "p1_p2":
        return mapped in ("p1", "p2")
    return True


def _lookup_email_recipients(service_name: str, severity: str) -> list[str]:
    """Find active email notification contacts for the application owning this service."""
    with get_session() as session:
        # Find ApplicationServiceRow matching service_name
        svc_row = session.execute(
            select(ApplicationServiceRow).where(
                ApplicationServiceRow.service_name == service_name
            )
        ).scalars().first()

        if svc_row is None:
            return []

        app_id = svc_row.application_id

        # Get active email contacts for this application
        contacts = session.execute(
            select(NotificationContactRow).where(
                NotificationContactRow.application_id == app_id,
                NotificationContactRow.method == "email",
                NotificationContactRow.is_active == True,  # noqa: E712
            )
        ).scalars().all()

    return [
        c.value
        for c in contacts
        if _matches_priority_filter(severity, c.priority_filter)
    ]


def _build_prediction_email_html(alert: dict[str, Any]) -> str:
    """Build a concise HTML email body for a predictive alert."""
    severity = alert.get("severity", "unknown").upper()
    confidence_pct = alert.get("confidence_pct", 0)
    breach_at = alert.get("estimated_breach_at")
    breach_label = str(breach_at)[:19] if breach_at else "Not projected"

    return f"""<html><body style="font-family: Segoe UI, sans-serif; color: #333;">
<h2 style="color: #d13438;">⚠️ Corvin Predictive Alert — {severity}</h2>
<table style="border-collapse: collapse; width: 100%; max-width: 600px;">
  <tr><td style="padding: 6px 12px; font-weight: bold;">Service</td><td style="padding: 6px 12px;">{alert.get('service_name', 'unknown')}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Environment</td><td style="padding: 6px 12px;">{alert.get('environment', 'unknown')}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Alert Type</td><td style="padding: 6px 12px;">{alert.get('alert_type', '').replace('_', ' ').title()}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Title</td><td style="padding: 6px 12px;">{alert.get('title', '')}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Summary</td><td style="padding: 6px 12px;">{alert.get('summary', '')}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Confidence</td><td style="padding: 6px 12px;">{confidence_pct:.0f}%</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Signal / Threshold</td><td style="padding: 6px 12px;">{alert.get('signal_value', 0):.1f} / {alert.get('threshold_value', 0):.1f}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Estimated Breach</td><td style="padding: 6px 12px;">{breach_label}</td></tr>
  <tr><td style="padding: 6px 12px; font-weight: bold;">Rationale</td><td style="padding: 6px 12px;">{alert.get('rationale', '')}</td></tr>
</table>
<p style="margin-top: 16px; font-size: 13px; color: #666;">
  This is an automated warning from Corvin's Predictive Analysis engine.
  An incident has NOT occurred yet — this is a proactive alert based on trend analysis.
</p>
</body></html>"""


def send_prediction_emails(alerts: list[dict[str, Any]]) -> int:
    """Send prediction warning emails for new alerts.

    Returns the number of emails successfully sent.
    """
    try:
        cfg = default_email_config()
    except Exception:
        cfg = {}

    if not cfg.get("enabled", False):
        return 0

    connection_string = os.environ.get("AZURE_COMMUNICATION_CONNECTION_STRING", "").strip()
    from_address = str(cfg.get("from_address", "")).strip()

    if not connection_string or connection_string.startswith("${"):
        _log.debug("Prediction notification skipped: AZURE_COMMUNICATION_CONNECTION_STRING not set")
        return 0
    if not from_address or from_address.startswith("${"):
        _log.debug("Prediction notification skipped: from_address not configured")
        return 0

    sent_count = 0

    for alert in alerts:
        service_name = alert.get("service_name", "")
        severity = alert.get("severity", "low")

        recipients = _lookup_email_recipients(service_name, severity)
        if not recipients:
            _log.debug("No email contacts for service=%s severity=%s", service_name, severity)
            continue

        subject = f"[Corvin Prediction] {severity.upper()}: {alert.get('title', 'Potential failure detected')}"
        html_body = _build_prediction_email_html(alert)

        try:
            from azure.communication.email import EmailClient

            client = EmailClient.from_connection_string(connection_string)
            message = {
                "senderAddress": from_address,
                "recipients": {"to": [{"address": r} for r in recipients]},
                "content": {
                    "subject": subject,
                    "html": html_body,
                },
            }
            poller = client.begin_send(message)
            poller.result()
            sent_count += 1
            _log.info(
                "Prediction email sent for service=%s alert_type=%s to %d recipients",
                service_name,
                alert.get("alert_type"),
                len(recipients),
            )
        except Exception as exc:
            _log.warning(
                "Prediction email failed for service=%s: %s",
                service_name,
                exc,
            )

    return sent_count

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

        # ── Confidence colours — matches frontend exactly ─────────────────────
        conf_colours = {
            "HIGH":   ("#22c55e", "#f0fdf4", "#bbf7d0", "✓ ALL CLEAR — HIGH CONFIDENCE"),
            "MEDIUM": ("#f97316", "#fff7ed", "#fed7aa", "⚠ MEDIUM CONFIDENCE"),
            "LOW":    ("#ef4444", "#fef2f2", "#fecaca", "⚠ LOW CONFIDENCE"),
        }
        conf_hex, conf_bg, conf_border, conf_banner = conf_colours.get(
            confidence, ("#6b7280", "#f9fafb", "#e5e7eb", confidence)
        )

        ado_row = ""
        if ado_work_item_url:
            ado_row = f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid #e2e8f0;
                   font-size:12px;text-transform:uppercase;letter-spacing:1.5px;
                   color:#64748b;font-weight:700;width:160px;vertical-align:top;">
                Azure DevOps
              </td>
              <td style="padding:14px 0;border-bottom:1px solid #e2e8f0;vertical-align:top;">
                <a href="{ado_work_item_url}"
                   style="display:inline-block;padding:8px 20px;
                          background:#0078d4;color:#ffffff;border-radius:6px;
                          text-decoration:none;font-size:13px;font-weight:700;">
                  📋 View Work Item →
                </a>
              </td>
            </tr>"""

        # ── Plain-text fallback ───────────────────────────────────────────────
        plain_text = "\n".join(filter(None, [
            f"Corvin RCA — {service} ({env})",
            f"Confidence: {confidence}",
            f"Description: {description}",
            f"What Broke: {root_cause}",
            f"Azure DevOps: {ado_work_item_url}" if ado_work_item_url else "",
            "Full RCA report attached as PDF.",
            "--", "Corvin AI SRE Co-Pilot",
        ]))

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Corvin RCA</title>
</head>
<body style="margin:0;padding:0;background:#dde3ea;
     font-family:'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#dde3ea;padding:28px 0;">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0"
       style="max-width:700px;width:100%;border-radius:6px;overflow:hidden;
              box-shadow:0 4px 24px rgba(0,0,0,.18);">

  <!-- ══ HEADER ══ -->
  <tr><td style="background:linear-gradient(135deg,#050d1a 0%,#0d2137 30%,#0a3d7a 65%,#0078d4 100%);
      padding:40px 52px 36px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;">
        <!-- Glow dot accent -->
        <div style="width:42px;height:4px;border-radius:4px;
             background:linear-gradient(90deg,#22c55e,#0078d4);margin-bottom:14px;"></div>
        <div style="font-size:10px;letter-spacing:4px;text-transform:uppercase;
             color:#60a5fa;font-weight:700;margin-bottom:10px;">AI SRE CO-PILOT</div>
        <div style="font-size:38px;font-weight:900;color:#ffffff;letter-spacing:-1.5px;
             line-height:1.05;">⚡ Corvin</div>
        <div style="font-size:13px;color:#93c5fd;margin-top:8px;letter-spacing:.3px;">
          Root Cause Analysis Report
        </div>
      </td>
      <td align="right" style="vertical-align:middle;">
        <div style="background:rgba(255,255,255,.09);
             border:1px solid rgba(255,255,255,.18);border-radius:10px;
             padding:16px 24px;text-align:center;min-width:100px;">
          <div style="font-size:10px;color:#93c5fd;text-transform:uppercase;
               letter-spacing:2px;margin-bottom:6px;font-weight:600;">Environment</div>
          <div style="font-size:22px;font-weight:900;color:#38bdf8;
               letter-spacing:2px;">{env.upper()}</div>
        </div>
      </td>
    </tr></table>
  </td></tr>

  <!-- ══ CONFIDENCE BANNER ══ -->
  <tr><td style="background:{conf_bg};border-bottom:3px solid {conf_hex};
      padding:15px 52px;">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;padding-right:10px;">
        <div style="width:12px;height:12px;border-radius:50%;
             background:{conf_hex};"></div>
      </td>
      <td style="vertical-align:middle;">
        <span style="font-size:13px;font-weight:800;color:{conf_hex};
              letter-spacing:1.5px;text-transform:uppercase;">
          {conf_banner}
        </span>
      </td>
    </tr></table>
  </td></tr>

  <!-- ══ BODY ══ -->
  <tr><td style="background:#ffffff;padding:38px 52px;">

    <!-- Service block -->
    <div style="margin-bottom:30px;">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:2px;
           color:#94a3b8;font-weight:700;margin-bottom:6px;">Service Under Investigation</div>
      <div style="font-size:30px;font-weight:800;color:#0d2137;letter-spacing:-.5px;">
        {service}
      </div>
    </div>

    <!-- Data table -->
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-top:1px solid #e2e8f0;">

      <!-- Description row -->
      <tr>
        <td style="padding:18px 20px 18px 0;border-bottom:1px solid #e2e8f0;
             font-size:11px;text-transform:uppercase;letter-spacing:1.5px;
             color:#64748b;font-weight:700;width:140px;vertical-align:top;">
          Description
        </td>
        <td style="padding:18px 0;border-bottom:1px solid #e2e8f0;
             font-size:14px;color:#334155;line-height:1.7;vertical-align:top;">
          {description}
        </td>
      </tr>

      <!-- What Broke row -->
      <tr>
        <td style="padding:18px 20px 18px 0;border-bottom:1px solid #e2e8f0;
             font-size:11px;text-transform:uppercase;letter-spacing:1.5px;
             color:#64748b;font-weight:700;vertical-align:top;">
          What Broke
        </td>
        <td style="padding:18px 0;border-bottom:1px solid #e2e8f0;vertical-align:top;">
          <div style="background:{conf_bg};border-left:4px solid {conf_hex};
               border-radius:0 6px 6px 0;padding:14px 18px;
               font-size:14px;color:#1e293b;line-height:1.75;font-weight:500;">
            {root_cause}
          </div>
        </td>
      </tr>

      <!-- Confidence row -->
      <tr>
        <td style="padding:18px 20px 18px 0;border-bottom:1px solid #e2e8f0;
             font-size:11px;text-transform:uppercase;letter-spacing:1.5px;
             color:#64748b;font-weight:700;vertical-align:middle;">
          Confidence
        </td>
        <td style="padding:18px 0;border-bottom:1px solid #e2e8f0;vertical-align:middle;">
          <span style="display:inline-block;padding:6px 20px;
                background:{conf_bg};border:2px solid {conf_border};
                border-radius:50px;font-size:13px;font-weight:800;
                color:{conf_hex};letter-spacing:.5px;">
            {confidence}
          </span>
        </td>
      </tr>

      <!-- AzDO row (conditional) -->
      {ado_row}

      <!-- PDF row -->
      <tr>
        <td style="padding:18px 20px 18px 0;font-size:11px;text-transform:uppercase;
             letter-spacing:1.5px;color:#64748b;font-weight:700;vertical-align:middle;">
          RCA Report
        </td>
        <td style="padding:18px 0;vertical-align:middle;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="font-size:30px;vertical-align:middle;padding-right:14px;">📄</td>
            <td style="vertical-align:middle;">
              <div style="font-size:14px;font-weight:700;color:#0d2137;">
                Full Report Attached
              </div>
              <div style="font-size:12px;color:#64748b;margin-top:3px;">
                Evidence summary · Root cause · Fix strategy
              </div>
            </td>
          </tr></table>
        </td>
      </tr>

    </table>
  </td></tr>

  <!-- ══ FOOTER ══ -->
  <tr><td style="background:#f1f5f9;padding:18px 52px;border-top:1px solid #e2e8f0;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:12px;color:#94a3b8;">
        Generated by <strong style="color:#0078d4;">Corvin AI SRE Co-Pilot</strong>
        &nbsp;·&nbsp; ID:
        <span style="font-family:monospace;color:#64748b;">{result.request_id[:8]}…</span>
      </td>
      <td align="right" style="font-size:11px;color:#cbd5e1;font-weight:600;">
        MetLife · Australia
      </td>
    </tr></table>
  </td></tr>

  <!-- ══ BOTTOM ACCENT ══ -->
  <tr><td style="height:5px;
      background:linear-gradient(90deg,#0078d4 0%,#22c55e 50%,#0078d4 100%);"></td></tr>

</table>
</td></tr>
</table>
</body></html>"""

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
                "plainText": plain_text,
                "html": html_body,
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

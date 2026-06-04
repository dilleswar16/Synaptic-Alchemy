"""
Compliance Evidence Pack Builder — Feature 10.

Generates a tamper-evident audit bundle for a completed investigation.
Supports two output formats:
  - ZIP: complete archive with JSON evidence files, markdown documents,
         manifest.json, and integrity.sha256 (SHA-256 of manifest)
  - PDF: single document with all sections, watermark, header/footer

Designed for SOX / SOC2 / ISO27001 auditors who need a portable, verifiable
record of an incident investigation including: trigger, evidence, RCA, fix
actions taken, approval records, and (when available) the post-mortem.

Config key: ``compliance_pack`` in config/policies/investigation.yaml.
No customer-specific strings appear in this module.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any

from corvin.core.contracts import InvestigationResult, PostMortemOutput

_log = logging.getLogger(__name__)


class CompliancePackBuilder:
    """Builds ZIP and PDF compliance evidence packs from investigation results.

    Args:
        config: The ``compliance_pack`` section from investigation.yaml.
                When None, sensible defaults are used.
    """

    _WATERMARK_DEFAULT = "CONFIDENTIAL — FOR AUDIT USE"
    _FRAMEWORKS_DEFAULT = ["SOX", "SOC2", "ISO27001"]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._watermark: str = cfg.get("watermark_text", self._WATERMARK_DEFAULT)
        self._frameworks: list[str] = cfg.get("supported_frameworks", self._FRAMEWORKS_DEFAULT)
        self._include_raw_evidence: bool = bool(cfg.get("include_raw_evidence", True))

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def reportlab_available() -> bool:
        """Return True when reportlab is installed and PDF generation is possible."""
        try:
            import reportlab  # noqa: F401
            return True
        except ImportError:
            return False

    def build_zip(
        self,
        result: InvestigationResult,
        post_mortem: PostMortemOutput | None = None,
        approved_at: datetime | None = None,
    ) -> bytes:
        """Build the full ZIP evidence bundle in memory. Returns raw bytes."""
        now = datetime.now(timezone.utc)
        inv_id = result.request_id
        prefix = f"corvin-evidence-pack-{inv_id}/"

        buf = io.BytesIO()
        file_registry: list[dict[str, str]] = []

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # ── investigation.json ────────────────────────────────────────
            inv_json = json.dumps(
                result.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                default=str,
            ).encode()
            zf.writestr(f"{prefix}investigation.json", inv_json)
            file_registry.append({"file": "investigation.json", "sha256": _sha256(inv_json)})

            # ── rca.md ────────────────────────────────────────────────────
            rca_md = self._render_rca_md(result).encode()
            zf.writestr(f"{prefix}rca.md", rca_md)
            file_registry.append({"file": "rca.md", "sha256": _sha256(rca_md)})

            # ── fix_strategy.md ───────────────────────────────────────────
            fix_md = self._render_fix_md(result).encode()
            zf.writestr(f"{prefix}fix_strategy.md", fix_md)
            file_registry.append({"file": "fix_strategy.md", "sha256": _sha256(fix_md)})

            # ── approval_audit.json ───────────────────────────────────────
            approval_json = json.dumps(
                self._render_approval_audit(result, approved_at=approved_at),
                indent=2,
                sort_keys=True,
                default=str,
            ).encode()
            zf.writestr(f"{prefix}approval_audit.json", approval_json)
            file_registry.append({"file": "approval_audit.json", "sha256": _sha256(approval_json)})

            # ── Raw evidence (optional) ───────────────────────────────────
            if self._include_raw_evidence:
                ev = result.evidence
                evidence_files = {
                    "evidence/apim_logs.json": ev.log_analytics_apim,
                    "evidence/container_metrics.json": ev.container_resource_metrics,
                    "evidence/container_inventory.json": ev.container_inventory,
                    "evidence/pod_restarts.json": ev.pod_restarts,
                    "evidence/oom_events.json": ev.oom_kill_events,
                    "evidence/autoscaler_events.json": ev.autoscaler_events,
                    "evidence/health_probe_failures.json": ev.health_probe_failures,
                    "evidence/aks_context.json": ev.aks_context,
                }
                for fname, data in evidence_files.items():
                    raw = json.dumps(data, indent=2, sort_keys=True, default=str).encode()
                    zf.writestr(f"{prefix}{fname}", raw)
                    file_registry.append({"file": fname, "sha256": _sha256(raw)})

            # ── Post-mortem (if available) ────────────────────────────────
            if post_mortem is not None:
                pm_bytes = post_mortem.markdown.encode()
                zf.writestr(f"{prefix}postmortem.md", pm_bytes)
                file_registry.append({"file": "postmortem.md", "sha256": _sha256(pm_bytes)})

            # ── manifest.json ─────────────────────────────────────────────
            manifest = {
                "investigation_id": inv_id,
                "generated_at": now.isoformat(),
                "service_name": result.request.service_name,
                "environment": result.request.environment,
                "watermark": self._watermark,
                "compliance_frameworks": self._frameworks,
                "files": file_registry,
            }
            manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
            zf.writestr(f"{prefix}manifest.json", manifest_bytes)

            # ── integrity.sha256 ──────────────────────────────────────────
            sha256_hex = _sha256(manifest_bytes)
            integrity_content = f"{sha256_hex}  manifest.json\n".encode()
            zf.writestr(f"{prefix}integrity.sha256", integrity_content)

        return buf.getvalue()

    def build_pdf(
        self,
        result: InvestigationResult,
        post_mortem: PostMortemOutput | None = None,
        approved_at: datetime | None = None,
    ) -> bytes:
        """Build a single-document PDF compliance pack.

        Falls back to a UTF-8 plain-text document (with .txt content) when
        reportlab is not installed. The route adjusts the Content-Type header
        accordingly when the fallback is used.
        """
        try:
            return self._build_pdf_reportlab(result, post_mortem, approved_at=approved_at)
        except ImportError:
            _log.warning("reportlab not installed — falling back to plain text document")
            return self._build_pdf_plain_text(result, post_mortem, approved_at=approved_at)

    # ── Private rendering helpers ───────────────────────────────────────────

    def _render_rca_md(self, result: InvestigationResult) -> str:
        r = result.rca
        lines = [
            f"# Root Cause Analysis — {result.request.service_name}",
            f"",
            f"**Investigation ID:** `{result.request_id}`  ",
            f"**Service:** {result.request.service_name}  ",
            f"**Environment:** {result.request.environment}  ",
            f"**Generated:** {result.completed_at.isoformat()}  ",
            f"",
            f"---",
            f"",
            f"## Summary",
            f"",
            r.summary,
            f"",
            f"## Root Cause",
            f"",
            r.root_cause,
            f"",
            f"## Confidence",
            f"",
            f"**Level:** {r.confidence.value.upper()}  ",
            f"**Reasoning:** {r.confidence_reasoning}",
            f"",
            f"## Contributing Factors",
            f"",
        ]
        for factor in r.contributing_factors:
            lines.append(f"- {factor}")
        lines += [
            f"",
            f"## Evidence References",
            f"",
        ]
        for ref in r.evidence_references:
            lines.append(f"- {ref}")
        return "\n".join(lines)

    def _render_fix_md(self, result: InvestigationResult) -> str:
        fs = result.fix_strategy
        lines = [
            f"# Fix Strategy — {result.request.service_name}",
            f"",
            f"**Investigation ID:** `{result.request_id}`  ",
            f"",
            f"## Summary",
            f"",
            fs.summary,
            f"",
            f"## Justification",
            f"",
            fs.justification,
            f"",
            f"## Actions",
            f"",
        ]
        for i, action in enumerate(fs.actions, 1):
            lines += [
                f"### {i}. {action.title}",
                f"",
                f"**Type:** {action.action_type.value}  ",
                f"**Risk:** {action.risk_level.value.upper()}  ",
                f"**Requires Approval:** {'Yes' if action.requires_approval else 'No'}  ",
                f"**Estimated Impact:** {action.estimated_impact}",
                f"",
                action.description,
                f"",
            ]
        return "\n".join(lines)

    def _render_approval_audit(
        self,
        result: InvestigationResult,
        approved_at: datetime | None = None,
    ) -> dict[str, Any]:
        req = result.request
        return {
            "investigation_id": result.request_id,
            "service_name": req.service_name,
            "environment": req.environment,
            "trigger_source": req.trigger_source.value,
            "incident_priority": req.incident_priority,
            "approval_status": req.approval_status.value,
            "created_at": req.created_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "approved_by": getattr(req, "approved_by", None),
            "approved_at": approved_at.isoformat() if approved_at else None,
        }

    def _build_pdf_reportlab(
        self,
        result: InvestigationResult,
        post_mortem: PostMortemOutput | None,
        approved_at: datetime | None = None,
    ) -> bytes:
        """Build PDF using reportlab. Raises ImportError when not installed."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            HRFlowable,
            PageBreak,
        )

        buf = io.BytesIO()
        now = datetime.now(timezone.utc)
        inv_id = result.request_id

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CorvinTitle",
            parent=styles["Title"],
            fontSize=20,
            spaceAfter=12,
        )
        h2_style = ParagraphStyle(
            "CorvinH2",
            parent=styles["Heading2"],
            fontSize=14,
            spaceBefore=12,
            spaceAfter=6,
        )
        watermark_style = ParagraphStyle(
            "CorvinWatermark",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
        )
        body_style = styles["Normal"]

        story = []

        # Header
        story.append(Paragraph(
            f"Corvin Compliance Evidence Pack",
            title_style,
        ))
        story.append(Paragraph(
            f"<b>{self._watermark}</b>",
            watermark_style,
        ))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"Investigation ID: <code>{inv_id}</code> | "
            f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Frameworks: {', '.join(self._frameworks)}",
            body_style,
        ))
        story.append(HRFlowable(width="100%", thickness=1))
        story.append(Spacer(1, 0.3 * cm))

        # RCA section
        story.append(Paragraph("Root Cause Analysis", h2_style))
        story.append(Paragraph(f"<b>Summary:</b> {result.rca.summary}", body_style))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(f"<b>Root Cause:</b>", body_style))
        story.append(Paragraph(result.rca.root_cause, body_style))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"<b>Confidence:</b> {result.rca.confidence.value.upper()} — {result.rca.confidence_reasoning}",
            body_style,
        ))

        # Fix strategy section
        story.append(Paragraph("Fix Strategy", h2_style))
        story.append(Paragraph(result.fix_strategy.summary, body_style))
        for i, action in enumerate(result.fix_strategy.actions, 1):
            story.append(Paragraph(
                f"<b>{i}. {action.title}</b> "
                f"[{action.action_type.value} / {action.risk_level.value.upper()}]",
                body_style,
            ))
            story.append(Paragraph(action.description, body_style))

        # Approval audit section
        story.append(Paragraph("Approval Audit", h2_style))
        audit = self._render_approval_audit(result, approved_at=approved_at)
        for k, v in audit.items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", body_style))

        # Post-mortem (if available)
        if post_mortem:
            story.append(PageBreak())
            story.append(Paragraph("Post-Mortem", h2_style))
            for line in post_mortem.markdown.split("\n"):
                if line.strip():
                    story.append(Paragraph(line, body_style))

        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )
        doc.build(story)
        return buf.getvalue()

    def _build_pdf_plain_text(
        self,
        result: InvestigationResult,
        post_mortem: PostMortemOutput | None,
        approved_at: datetime | None = None,
    ) -> bytes:
        """Plain-text compliance document used when reportlab is not installed.

        Returns UTF-8 encoded text. The caller (route handler) should detect the
        ImportError fallback and serve this with Content-Type: text/plain and a
        .txt filename rather than claiming it is a PDF.
        """
        now = datetime.now(timezone.utc)
        inv_id = result.request_id
        sep = "=" * 60
        lines = [
            self._watermark,
            "",
            "CORVIN COMPLIANCE EVIDENCE PACK",
            sep,
            f"Investigation ID : {inv_id}",
            f"Generated        : {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"Frameworks       : {', '.join(self._frameworks)}",
            "",
            sep,
            "ROOT CAUSE ANALYSIS",
            sep,
            f"Summary    : {result.rca.summary}",
            f"Root Cause : {result.rca.root_cause}",
            f"Confidence : {result.rca.confidence.value.upper()}",
            f"Reasoning  : {result.rca.confidence_reasoning}",
            "",
            "Contributing Factors:",
        ]
        for factor in result.rca.contributing_factors:
            lines.append(f"  - {factor}")
        lines += [
            "",
            sep,
            "FIX STRATEGY",
            sep,
            result.fix_strategy.summary,
            "",
        ]
        for i, a in enumerate(result.fix_strategy.actions, 1):
            lines += [
                f"{i}. {a.title}",
                f"   Type   : {a.action_type.value}",
                f"   Risk   : {a.risk_level.value.upper()}",
                f"   Impact : {a.estimated_impact}",
                f"   Details: {a.description}",
                "",
            ]
        lines += [
            sep,
            "APPROVAL AUDIT",
            sep,
        ]
        for k, v in self._render_approval_audit(result, approved_at=approved_at).items():
            lines.append(f"{k:<20}: {v}")
        if post_mortem:
            lines += ["", sep, "POST-MORTEM", sep, post_mortem.markdown]

        return "\n".join(lines).encode("utf-8", errors="replace")


def _sha256(data: bytes) -> str:
    """Return hex SHA-256 of *data*."""
    return hashlib.sha256(data).hexdigest()

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from corvin.core.contracts import InvestigationResult


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_ts(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2026", "...")
    )


def _p(style: ParagraphStyle, text: str) -> Paragraph:
    return Paragraph(escape(_norm(text)), style)


def _risk_color(risk: str):
    risk_l = (risk or "").lower()
    if risk_l == "high":
        return colors.HexColor("#dc2626")
    if risk_l == "medium":
        return colors.HexColor("#d97706")
    return colors.HexColor("#059669")


def _confidence_color(conf: str):
    conf_l = (conf or "").lower()
    if conf_l == "high":
        return colors.HexColor("#059669")
    if conf_l == "medium":
        return colors.HexColor("#d97706")
    return colors.HexColor("#dc2626")


def build_rca_pdf(result: InvestigationResult) -> bytes:
    conf = result.rca.confidence.value.upper()
    generated_at = _fmt_ts(datetime.now(timezone.utc))
    confidence_color = _confidence_color(result.rca.confidence.value)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CorvinTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CorvinSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#475569"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.white,
            spaceAfter=2,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#fde68a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#c2410c"),
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionBodyLead",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#334155"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Item",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=10,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TinyLabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.3,
            leading=10.5,
            textColor=colors.HexColor("#64748b"),
            alignment=TA_LEFT,
            spaceAfter=1,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TinyValue",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11.5,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="RiskHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            alignment=TA_RIGHT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            spaceBefore=8,
        )
    )

    story: list = []
    # Cover block (branded)
    cover = Table(
        [
            [_p(styles["CoverTitle"], "CORVIN RCA REPORT")],
            [_p(styles["CoverSub"], "Blameless, structured incident analysis for operators")],
        ],
        colWidths=[178 * mm],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#f97316")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(cover)
    story.append(Spacer(1, 7))

    story.append(_p(styles["CorvinSub"], "Structured Root Cause Analysis for SRE Review"))
    story.append(HRFlowable(width="100%", thickness=1.1, color=colors.HexColor("#f97316"), spaceAfter=10))

    if result.confidence_warning:
        warning_table = Table(
            [[_p(styles["TinyLabel"], "⚠️ LOW CONFIDENCE"), _p(styles["Body"], "Corvin generated this RCA with low confidence due to insufficient or ambiguous evidence. Manual review is strongly recommended.")]],
            colWidths=[38*mm, 140*mm]
        )
        warning_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#ef4444")),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#b91c1c")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ]))
        story.append(warning_table)
        story.append(Spacer(1, 10))

    meta_table = Table(
        [
            [_p(styles["TinyLabel"], "Generated"), _p(styles["TinyValue"], generated_at), _p(styles["TinyLabel"], "RCA Confidence"), Paragraph(f"<b>{escape(conf)}</b>", ParagraphStyle(name="_conf", parent=styles["TinyValue"], textColor=confidence_color))],
            [_p(styles["TinyLabel"], "Request ID"), _p(styles["TinyValue"], result.request_id), _p(styles["TinyLabel"], "Service"), _p(styles["TinyValue"], result.request.service_name)],
            [_p(styles["TinyLabel"], "Environment"), _p(styles["TinyValue"], result.request.environment), _p(styles["TinyLabel"], "Trigger"), _p(styles["TinyValue"], result.request.trigger_source.value)],
        ],
        colWidths=[32 * mm, 68 * mm, 33 * mm, 45 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Evidence snapshot at a glance
    story.append(_p(styles["SectionHeading"], "Evidence Snapshot"))
    evidence_snapshot = Table(
        [
            ["Application Logs", str(len(result.evidence.elastic_logs)), "Application Metrics", str(len(result.evidence.elastic_metrics)), "API Gateway Logs", str(len(result.evidence.log_analytics_apim))],
            ["K8s Resource Usage", str(len(result.evidence.container_resource_metrics)), "K8s Cluster Health", str(len(result.evidence.aks_context.keys())), "Evidence Collected", _fmt_ts(result.evidence.collected_at)],
            ["AKS Context Keys", ", ".join(sorted(result.evidence.aks_context.keys())) or "-", "", "", "", ""],
        ],
        colWidths=[31 * mm, 20 * mm, 35 * mm, 22 * mm, 33 * mm, 37 * mm],
    )
    evidence_snapshot.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 2), (5, 2)),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#fed7aa")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#fdba74")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTNAME", (4, 0), (4, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTNAME", (3, 0), (3, -1), "Helvetica"),
                ("FONTNAME", (5, 0), (5, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#9a3412")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#9a3412")),
                ("TEXTCOLOR", (4, 0), (4, -1), colors.HexColor("#9a3412")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#111827")),
                ("TEXTCOLOR", (3, 0), (3, -1), colors.HexColor("#111827")),
                ("TEXTCOLOR", (5, 0), (5, -1), colors.HexColor("#111827")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(evidence_snapshot)

    story.append(_p(styles["SectionHeading"], "Audit Trail Snapshot"))
    timeline_table = Table(
        [
            ["Stage", "Timestamp (UTC)", "Notes"],
            ["Triggered", _fmt_ts(result.request.created_at), "Investigation request accepted"],
            ["Evidence", _fmt_ts(result.evidence.collected_at), "Evidence collection complete"],
            ["RCA", _fmt_ts(result.rca.generated_at), "Root cause analysis generated"],
            ["Fix Strategy", _fmt_ts(result.fix_strategy.generated_at), "Remediation strategy generated"],
            ["Completed", _fmt_ts(result.completed_at), "Pipeline complete"],
        ],
        colWidths=[30 * mm, 45 * mm, 103 * mm],
    )
    timeline_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(timeline_table)
    story.append(Spacer(1, 5))

    story.append(_p(styles["SectionHeading"], "1. RCA Summary"))
    story.append(_p(styles["Body"], result.rca.summary))

    story.append(_p(styles["SectionHeading"], "2. Root Cause"))
    story.append(_p(styles["Body"], result.rca.root_cause))
    if result.rca.confidence_reasoning:
        story.append(Spacer(1, 6))
        explainer_table = Table(
            [
                [_p(styles["TinyLabel"], "🧠 WHAT WOULD A SENIOR SRE DO? · CORVIN'S RATIONALE")],
                [_p(styles["SectionBodyLead"], result.rca.confidence_reasoning)],
            ],
            colWidths=[178 * mm],
        )
        explainer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#f97316")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#fed7aa")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(explainer_table)
        story.append(Spacer(1, 6))

    story.append(_p(styles["SectionHeading"], "3. Contributing Factors"))
    if result.rca.contributing_factors:
        for i, factor in enumerate(result.rca.contributing_factors, start=1):
            story.append(_p(styles["Item"], f"{i}. {factor}"))
    else:
        story.append(_p(styles["Body"], "No contributing factors provided."))

    story.append(_p(styles["SectionHeading"], "4. Evidence References"))
    if result.rca.evidence_references:
        for i, ref in enumerate(result.rca.evidence_references, start=1):
            story.append(_p(styles["Item"], f"{i}. {ref}"))
    else:
        story.append(_p(styles["Body"], "No evidence references provided."))

    story.append(_p(styles["SectionHeading"], "5. Fix Strategy"))
    story.append(_p(styles["Body"], result.fix_strategy.summary))

    story.append(_p(styles["SectionHeading"], "6. Recommended Actions"))
    if result.fix_strategy.actions:
        action_summary_rows = [["#", "Action", "Risk", "Estimated Impact"]]
        for i, action in enumerate(result.fix_strategy.actions, start=1):
            action_summary_rows.append(
                [
                    _p(styles["Body"], str(i)),
                    _p(styles["Body"], action.title),
                    Paragraph(f"<b>{escape(action.risk_level.value.upper())}</b>", ParagraphStyle(name=f"risk-{i}", parent=styles["Body"], textColor=_risk_color(action.risk_level.value))),
                    _p(styles["Body"], action.estimated_impact),
                ]
            )

        summary_table = Table(
            action_summary_rows,
            colWidths=[10 * mm, 86 * mm, 22 * mm, 60 * mm],
            repeatRows=1,
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fffaf3")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#fdba74")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#fed7aa")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 7))

        for i, action in enumerate(result.fix_strategy.actions, start=1):
            risk = action.risk_level.value.upper()
            risk_style = ParagraphStyle(
                name=f"risk-head-{i}",
                parent=styles["RiskHeader"],
                textColor=_risk_color(action.risk_level.value),
            )
            action_card = Table(
                [
                    [_p(styles["Body"], f"{i}. {action.title}"), Paragraph(f"<b>RISK: {escape(risk)}</b>", risk_style)],
                    [_p(styles["SectionBodyLead"], f"Impact: {action.estimated_impact}"), ""],
                    [_p(styles["Body"], action.description), ""],
                ],
                colWidths=[145 * mm, 33 * mm],
            )
            action_card.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 1), (1, 1)),
                        ("SPAN", (0, 2), (1, 2)),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff7ed")),
                        ("BACKGROUND", (0, 1), (-1, 2), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#fdba74")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#fed7aa")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(action_card)
            story.append(Spacer(1, 6))
    else:
        story.append(_p(styles["Body"], "No actions proposed."))

    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cbd5e1"), spaceBefore=6, spaceAfter=6))
    story.append(_p(styles["Caption"], "This report is generated by Corvin for operational review."))
    story.append(_p(styles["Caption"], "All recommended actions require human approval."))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=f"Corvin RCA {result.request_id}",
        author="Corvin",
        subject="Root Cause Analysis",
    )
    doc.build(story)
    return buffer.getvalue()

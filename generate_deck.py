"""
Generate Corvin Hackathon Demo PPTX from slide content.
Run: python generate_deck.py
Output: corvin-deck.pptx
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── Palette ──────────────────────────────────────────────
BG_DEEP = RGBColor(0x05, 0x0A, 0x0E)
BG_CARD = RGBColor(0x0F, 0x19, 0x23)
TEAL_400 = RGBColor(0x2D, 0xD4, 0xBF)
TEAL_500 = RGBColor(0x14, 0xB8, 0xA6)
TEAL_600 = RGBColor(0x0D, 0x94, 0x88)
TEAL_700 = RGBColor(0x0F, 0x76, 0x6E)
WHITE = RGBColor(0xF1, 0xF5, 0xF9)
TEXT_SEC = RGBColor(0x94, 0xA3, 0xB8)
TEXT_MUTED = RGBColor(0x64, 0x74, 0x8B)
RED = RGBColor(0xEF, 0x44, 0x44)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
CYAN = RGBColor(0x06, 0xB6, 0xD4)
PURPLE = RGBColor(0x8B, 0x5C, 0xF6)
GREEN = RGBColor(0x10, 0xB9, 0x81)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def set_slide_bg(slide, color=BG_DEEP):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_text(slide, left, top, width, height, text, size=18, color=WHITE,
             bold=False, align=PP_ALIGN.LEFT, font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = align
    return txBox


def add_rounded_rect(slide, left, top, width, height, fill_color=BG_CARD,
                     border_color=None, text="", text_size=11, text_color=WHITE,
                     bold=False, align=PP_ALIGN.CENTER):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    if text:
        tf = shape.text_frame
        tf.word_wrap = True
        tf.paragraphs[0].text = text
        tf.paragraphs[0].font.size = Pt(text_size)
        tf.paragraphs[0].font.color.rgb = text_color
        tf.paragraphs[0].font.bold = bold
        tf.paragraphs[0].font.name = "Calibri"
        tf.paragraphs[0].alignment = align
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return shape


def add_pill(slide, left, top, text, dot_color=TEAL_500):
    pill = add_rounded_rect(slide, left, top, Inches(2.2), Inches(0.38),
                            fill_color=RGBColor(0x12, 0x1A, 0x28),
                            border_color=RGBColor(0x1E, 0x2D, 0x3D),
                            text=text, text_size=9, text_color=TEXT_SEC)
    dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, left + Inches(0.15),
                                  top + Inches(0.12), Inches(0.12), Inches(0.12))
    dot.fill.solid()
    dot.fill.fore_color.rgb = dot_color
    dot.line.fill.background()
    return pill


def add_arrow_down(slide, cx, top, length=Inches(0.4)):
    shape = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, cx - Inches(0.12),
                                    top, Inches(0.24), length)
    shape.fill.solid()
    shape.fill.fore_color.rgb = TEAL_600
    shape.line.fill.background()
    return shape


def add_multiline(slide, left, top, width, height, lines, size=11, color=TEXT_SEC, spacing=1.2):
    """lines = list of (text, color, bold, size_override)"""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(lines):
        txt = item[0]
        c = item[1] if len(item) > 1 else color
        b = item[2] if len(item) > 2 else False
        s = item[3] if len(item) > 3 else size
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = txt
        p.font.size = Pt(s)
        p.font.color.rgb = c
        p.font.bold = b
        p.font.name = "Calibri"
        p.space_after = Pt(spacing)
    return txBox


# ═══════════════════════════════════════════════════════════
prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
blank = prs.slide_layouts[6]  # Blank layout

# ═══════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_rounded_rect(s, Inches(5.4), Inches(1.0), Inches(2.5), Inches(0.38),
                 fill_color=RGBColor(0x0D, 0x25, 0x20), border_color=TEAL_700,
                 text="Hackathon 2026", text_size=9, text_color=TEAL_400, bold=True)
add_text(s, Inches(2), Inches(2.0), Inches(9.3), Inches(1.6),
         "Corvin", size=72, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(2), Inches(3.6), Inches(9.3), Inches(1.0),
         "Your AI SRE Co-Pilot. From alert to root cause\nin seconds — not hours.",
         size=20, color=TEXT_SEC, align=PP_ALIGN.CENTER)
# Pills
pill_y = Inches(5.0)
add_pill(s, Inches(3.0), pill_y, "  Azure-Native", TEAL_500)
add_pill(s, Inches(5.5), pill_y, "  GPT-5.1 Powered", CYAN)
add_pill(s, Inches(8.0), pill_y, "  Human-in-the-Loop", GREEN)

# ═══════════════════════════════════════════════════════════
# SLIDE 2 — THE PROBLEM
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "THE PROBLEM", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.2), Inches(10.3), Inches(1.2),
         "It's 3 AM. An alert fires.\nNow what?",
         size=40, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
# Stat cards
stats = [("37m", "Avg time to\nfind root cause", RED),
         ("12+", "Dashboards &\ntools to check", AMBER),
         ("80%", "Incidents are\nrepeat patterns", RED),
         ("$$$", "Every minute of\ndowntime costs", AMBER)]
for i, (val, label, clr) in enumerate(stats):
    x = Inches(1.5 + i * 2.8)
    y = Inches(3.2)
    add_rounded_rect(s, x, y, Inches(2.3), Inches(1.8), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.2), y + Inches(0.25), Inches(1.9), Inches(0.8),
             val, size=36, color=clr, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.2), y + Inches(1.1), Inches(1.9), Inches(0.6),
             label, size=10, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
add_text(s, Inches(1.5), Inches(5.5), Inches(10.3), Inches(0.8),
         "Engineers scramble across Splunk, Grafana, Azure Portal, K8s logs —\npiecing together context manually, under pressure.",
         size=14, color=TEXT_SEC, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 3 — THE SOLUTION
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "THE SOLUTION", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(2.0), Inches(10.3), Inches(2.0),
         '"You don\'t need more dashboards.\nYou need an AI co-pilot that\nalready knows your systems."',
         size=30, color=TEXT_SEC, align=PP_ALIGN.CENTER)
# Separator line
sep = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.2), Inches(4.3), Inches(0.9), Inches(0.04))
sep.fill.solid()
sep.fill.fore_color.rgb = TEAL_500
sep.line.fill.background()
add_text(s, Inches(2), Inches(4.8), Inches(9.3), Inches(1.2),
         "Corvin connects to your existing Azure infrastructure, gathers evidence\nfrom every source, and delivers a structured Root Cause Analysis\nwith fix strategies — before your engineer finishes their coffee.",
         size=14, color=TEXT_SEC, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 4 — HOW IT WORKS (Workflow)
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "HOW IT WORKS", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "From Alert to Answer.", size=40, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
steps = [("⚡", "Trigger", "Azure Alert\nor Manual"),
         ("🔍", "Enrich", "Gather logs,\nmetrics, context"),
         ("🧠", "AI Investigate", "GPT-5.1 with\nchain-of-thought"),
         ("🎯", "RCA", "Root cause +\nfix strategy"),
         ("✅", "Approve & Fix", "Human approves,\nCorvin executes")]
for i, (icon, lbl, sub) in enumerate(steps):
    x = Inches(0.8 + i * 2.5)
    y = Inches(2.8)
    bc = TEAL_700 if lbl == "AI Investigate" else RGBColor(0x1E, 0x2D, 0x3D)
    add_rounded_rect(s, x, y, Inches(2.0), Inches(2.2), BG_CARD, border_color=bc)
    add_text(s, x + Inches(0.3), y + Inches(0.2), Inches(1.4), Inches(0.5),
             icon, size=28, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.1), y + Inches(0.85), Inches(1.8), Inches(0.4),
             lbl, size=13, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.1), y + Inches(1.35), Inches(1.8), Inches(0.7),
             sub, size=9, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
    if i < 4:
        add_text(s, x + Inches(2.0), y + Inches(0.85), Inches(0.5), Inches(0.4),
                 "→", size=18, color=TEAL_600, align=PP_ALIGN.CENTER)
add_text(s, Inches(1.5), Inches(5.5), Inches(10.3), Inches(0.6),
         "Every step is streamed in real-time — watch the AI think, see evidence arrive, get results as they form.",
         size=13, color=TEXT_SEC, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 5 — AI ENGINE + TERMINAL
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(0.8), Inches(0.5), Inches(4), Inches(0.4),
         "UNDER THE HOOD", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(0.8), Inches(1.0), Inches(5.5), Inches(1.0),
         "Not just an\nLLM wrapper.", size=36, color=WHITE, bold=True)
features = [("Site Knowledge Injection",
             "Real infrastructure topology — APIM routing, AKS clusters, service dependencies — baked into every prompt"),
            ("Runbook Matching",
             "Automatically surfaces relevant runbooks based on error patterns — tribal knowledge at scale"),
            ("Chain-of-Thought Reasoning",
             "GPT-5.1's thinking process is streamed live — full transparency, never a black box"),
            ("Incident Memory",
             "Every investigation teaches the system — past incidents inform future analysis")]
for i, (title, desc) in enumerate(features):
    y = Inches(2.5 + i * 1.1)
    add_text(s, Inches(1.1), y, Inches(0.3), Inches(0.3), "◆", size=14, color=TEAL_400)
    add_text(s, Inches(1.5), y, Inches(4.5), Inches(0.3), title, size=13, color=WHITE, bold=True)
    add_text(s, Inches(1.5), y + Inches(0.3), Inches(4.5), Inches(0.5), desc, size=10, color=TEXT_MUTED)

# Terminal mock
term_x, term_y = Inches(7.0), Inches(1.2)
term_w, term_h = Inches(5.8), Inches(5.5)
add_rounded_rect(s, term_x, term_y, term_w, term_h,
                 fill_color=RGBColor(0x0C, 0x11, 0x17),
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
# Terminal dots
for j, clr in enumerate([RED, AMBER, GREEN]):
    d = s.shapes.add_shape(MSO_SHAPE.OVAL, term_x + Inches(0.3 + j * 0.25),
                            term_y + Inches(0.25), Inches(0.12), Inches(0.12))
    d.fill.solid()
    d.fill.fore_color.rgb = clr
    d.line.fill.background()
add_multiline(s, term_x + Inches(0.3), term_y + Inches(0.7), Inches(5.2), Inches(4.5), [
    ("$ corvin investigate fundapis --env dev", TEXT_MUTED, False, 10),
    ("", TEXT_MUTED),
    ("● Collecting evidence from 4 sources...", GREEN, False, 10),
    ("  Container Logs   200 records   8.7s", TEXT_SEC, False, 9),
    ("  APIM Gateway     47 records    12.1s", TEXT_SEC, False, 9),
    ("  AKS Context      12 records    4.0s", TEXT_SEC, False, 9),
    ("  Azure Activity   3 records     2.3s", TEXT_SEC, False, 9),
    ("", TEXT_MUTED),
    ("◆ AI analyzing with chain-of-thought...", AMBER, False, 10),
    ('  "Examining 503 spike → HikariCP pool exhaustion..."', TEXT_MUTED, False, 9),
    ("", TEXT_MUTED),
    ("✓ Root Cause: HikariCP connection pool exhaustion", GREEN, False, 10),
    ("  Confidence: 87%", AMBER, False, 9),
    ("  Fix: kubectl scale deploy chad-fundapis --replicas=4", WHITE, False, 9),
    ("", TEXT_MUTED),
    ("⏱️ Total: 27.1s   Awaiting approval → █", TEXT_SEC, False, 9),
], size=10, color=TEXT_SEC)

# ═══════════════════════════════════════════════════════════
# SLIDE 6 — COMMAND CENTER
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "COMMAND CENTER", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "Chat with your infrastructure.", size=38, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(2), Inches(2.0), Inches(9.3), Inches(0.6),
         "An agentic chatbot that doesn't just answer — it acts. Runs real investigations,\nqueries live Azure data, simulates blast radius, calls 16 tools autonomously.",
         size=14, color=TEXT_SEC, align=PP_ALIGN.CENTER)
cards = [("💬 Natural Language", '"Why is fundapis throwing 503s in dev?"'),
         ("🔮 What-If Analysis", '"What\'s the blast radius if fundsso goes down?"'),
         ("📊 Live Intelligence", '"Give me a morning briefing on last 24 hours"')]
for i, (title, desc) in enumerate(cards):
    x = Inches(1.3 + i * 3.8)
    y = Inches(3.2)
    add_rounded_rect(s, x, y, Inches(3.3), Inches(1.5), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.2), y + Inches(0.2), Inches(2.9), Inches(0.4),
             title, size=11, color=TEAL_400, bold=True)
    add_text(s, x + Inches(0.2), y + Inches(0.7), Inches(2.9), Inches(0.6),
             desc, size=10, color=TEXT_MUTED)
pill_y = Inches(5.3)
pills = [("  Agentic Tool Use", TEAL_500), ("  Streaming Responses", CYAN),
         ("  Multi-Turn Context", GREEN), ("  Speculative Analysis", PURPLE)]
for i, (txt, clr) in enumerate(pills):
    add_pill(s, Inches(1.0 + i * 3.0), pill_y, txt, clr)

# ═══════════════════════════════════════════════════════════
# SLIDE 7 — AGENTIC AI (24 TOOLS)
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.3), Inches(4), Inches(0.4),
         "AGENTIC AI", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(0.7), Inches(10.3), Inches(0.7),
         "24 Tools. 6 Reasoning Rounds.", size=36, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(2), Inches(1.4), Inches(9.3), Inches(0.6),
         "The LLM doesn't just generate text — it autonomously decides which tools to call,\ninterprets results, chains actions, and iterates up to 6 rounds per message.",
         size=12, color=TEXT_SEC, align=PP_ALIGN.CENTER)
# Left card: 16 Agent Tools
add_rounded_rect(s, Inches(0.8), Inches(2.3), Inches(5.8), Inches(4.2), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(1.0), Inches(2.4), Inches(5.4), Inches(0.4),
         "🤖 Command Center — 16 Agent Tools", size=11, color=TEAL_400, bold=True)
agent_tools = ["📊 Platform Stats", "📋 Recent Incidents", "🔎 Investigation Detail",
               "📡 Predictive Alerts", "🎯 Service Score", "💰 ROI Metrics",
               "🏗️ Service Topology", "💥 Blast Radius", "📋 Post-Mortem",
               "🔄 Similar Incidents", "📖 Site Knowledge", "📓 Runbook Lookup",
               "⚡ Run KQL Live", "☸️ AKS Health Live", "📈 APIM Analytics",
               "🔍 Elastic Query"]
for i, tool in enumerate(agent_tools):
    col = i % 2
    row = i // 2
    add_text(s, Inches(1.1 + col * 2.8), Inches(2.95 + row * 0.4), Inches(2.6), Inches(0.35),
             tool, size=9, color=TEXT_SEC)
# Right card: 8 Pipeline Toolset
add_rounded_rect(s, Inches(6.9), Inches(2.3), Inches(5.8), Inches(4.2), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(7.1), Inches(2.4), Inches(5.4), Inches(0.4),
         "⚙️ Investigation Pipeline — 8 Toolset Tools", size=11, color=TEAL_400, bold=True)
toolsets = [("AKS", "Pod context, CrashLoop, OOMKill"),
            ("APIM", "Gateway errors, 5xx, latency spikes"),
            ("Elastic", "App logs + APM metrics"),
            ("Activity", '"What changed?" correlation'),
            ("Knowledge", "Infra facts + incident learnings"),
            ("Runbooks", "Keyword-matched procedures")]
for i, (badge, desc) in enumerate(toolsets):
    y = Inches(3.0 + i * 0.42)
    add_rounded_rect(s, Inches(7.2), y, Inches(1.0), Inches(0.3),
                     fill_color=RGBColor(0x0D, 0x25, 0x20), border_color=TEAL_700,
                     text=badge, text_size=8, text_color=TEAL_400, bold=True)
    add_text(s, Inches(8.4), y, Inches(4.0), Inches(0.3), desc, size=9, color=TEXT_SEC)
# Tool-call loop
add_text(s, Inches(7.1), Inches(5.7), Inches(5.4), Inches(0.3),
         "TOOL-CALL LOOP", size=8, color=TEXT_MUTED, bold=True)
add_text(s, Inches(7.1), Inches(6.0), Inches(5.4), Inches(0.3),
         "User → LLM decides → Tool call → Result → LLM reasons → ...repeat ×6",
         size=9, color=TEXT_SEC)
# Bottom pills
pill_y = Inches(6.8)
for i, (txt, clr) in enumerate([('  tool_choice="auto"', TEAL_500),
                                  ("  6 rounds max", AMBER),
                                  ("  20+ APIM templates", CYAN),
                                  ("  Streaming SSE", PURPLE)]):
    add_pill(s, Inches(1.0 + i * 3.0), pill_y, txt, clr)

# ═══════════════════════════════════════════════════════════
# SLIDE 8 — KEY FEATURES
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "CAPABILITIES", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "Enterprise Intelligence, Built In.", size=38, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
features = [("💥", "Blast Radius Estimator", "Calculates affected services, users, and revenue impact before any action is taken."),
            ("📡", "Predictive Detection", "Spots anomaly trends before they become incidents — proactive, not reactive."),
            ("🎯", "Corvin Score", "Real-time service health gauge: incident frequency, MTTR, confidence, recency."),
            ("📋", "Auto Post-Mortem", "One-click blameless post-mortems with timeline, impact analysis, and lessons learned."),
            ("🏗️", "Service Topology", "Interactive dependency graph with live health overlays — see how services connect."),
            ("⏱️", "SLA Countdown", "Priority-aware timers with breach predictions — P1 incidents get red-zone treatment.")]
for i, (icon, title, desc) in enumerate(features):
    col = i % 3
    row = i // 3
    x = Inches(0.8 + col * 4.0)
    y = Inches(2.3 + row * 2.4)
    add_rounded_rect(s, x, y, Inches(3.6), Inches(2.0), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.25), y + Inches(0.2), Inches(1), Inches(0.5),
             icon, size=24)
    add_text(s, x + Inches(0.25), y + Inches(0.7), Inches(3.0), Inches(0.4),
             title, size=13, color=WHITE, bold=True)
    add_text(s, x + Inches(0.25), y + Inches(1.15), Inches(3.0), Inches(0.7),
             desc, size=10, color=TEXT_MUTED)

# ═══════════════════════════════════════════════════════════
# SLIDE 9 — INTEGRATIONS
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "INTEGRATIONS", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "Plugs Into What You Already Use.", size=38, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(2), Inches(2.0), Inches(9.3), Inches(0.6),
         "No new agents to deploy. No data migration. Corvin reads from your\nexisting tools and starts delivering value from day one.",
         size=14, color=TEXT_SEC, align=PP_ALIGN.CENTER)
integrations = [("Azure Monitor Alerts", RGBColor(0x00, 0x78, 0xD4)),
                ("Azure Log Analytics", RGBColor(0x00, 0x78, 0xD4)),
                ("Azure Kubernetes Service", RGBColor(0x32, 0x6C, 0xE5)),
                ("Azure APIM", RGBColor(0x00, 0x78, 0xD4)),
                ("Elastic / Kibana", AMBER),
                ("Microsoft Teams", RGBColor(0x7B, 0x83, 0xEB)),
                ("Azure DevOps", RGBColor(0x00, 0x78, 0xD4)),
                ("Azure Activity Log", RGBColor(0x00, 0x78, 0xD4)),
                ("PostgreSQL", RGBColor(0x33, 0x67, 0x91)),
                ("REST API", GREEN)]
for i, (name, clr) in enumerate(integrations):
    col = i % 5
    row = i // 5
    add_pill(s, Inches(0.6 + col * 2.5), Inches(3.2 + row * 0.6), f"  {name}", clr)
# Delivery surfaces
surfaces = [("🌐", "Web App"), ("💬", "Teams Bot"), ("⌨️", "CLI"), ("🔌", "REST API")]
for i, (icon, lbl) in enumerate(surfaces):
    x = Inches(2.0 + i * 2.5)
    y = Inches(5.2)
    add_rounded_rect(s, x, y, Inches(2.0), Inches(1.2), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.3), y + Inches(0.15), Inches(1.4), Inches(0.5),
             icon, size=24, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.3), y + Inches(0.65), Inches(1.4), Inches(0.4),
             lbl, size=11, color=WHITE, bold=True, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 10 — ARCHITECTURE
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.3), Inches(4), Inches(0.4),
         "ARCHITECTURE", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(0.7), Inches(10.3), Inches(0.7),
         "End-to-End Data Flow.", size=34, color=WHITE, bold=True, align=PP_ALIGN.CENTER)

# Tier 1: Triggers
tier1_items = [("⚡ Azure Alerts", "Action Group webhook", AMBER),
               ("🎮 Alert Simulator", "10+ failure scenarios", PURPLE),
               ("⌨️ CLI / API / Teams", "Manual triggers", CYAN)]
for i, (name, sub, clr) in enumerate(tier1_items):
    x = Inches(2.5 + i * 3.0)
    add_rounded_rect(s, x, Inches(1.5), Inches(2.5), Inches(0.7), BG_CARD,
                     border_color=clr, text=f"{name}\n{sub}", text_size=9, text_color=clr)
add_arrow_down(s, Inches(6.65), Inches(2.25))
add_text(s, Inches(7.5), Inches(2.25), Inches(2.5), Inches(0.3),
         "POST /investigate", size=7, color=TEXT_MUTED)

# Tier 2: Enrichment
add_rounded_rect(s, Inches(1.0), Inches(2.8), Inches(11.3), Inches(1.1),
                 fill_color=RGBColor(0x08, 0x12, 0x12),
                 border_color=RGBColor(0x0D, 0x2A, 0x26))
add_text(s, Inches(1.2), Inches(2.85), Inches(5), Inches(0.25),
         "ENRICHMENT LAYER — PARALLEL GATHER", size=7, color=TEAL_600, bold=True)
enrich_items = ["📊 APIM Gateway", "☸️ AKS Context", "📦 Container Logs",
                "📝 Activity Log", "🔍 Elastic"]
for i, name in enumerate(enrich_items):
    x = Inches(1.3 + i * 2.2)
    add_rounded_rect(s, x, Inches(3.15), Inches(1.9), Inches(0.55), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D),
                     text=name, text_size=9, text_color=WHITE)
add_arrow_down(s, Inches(6.65), Inches(3.8))
add_text(s, Inches(7.5), Inches(3.8), Inches(3), Inches(0.3),
         "EvidenceBundle (JSON)", size=7, color=TEXT_MUTED)

# Tier 3: AI Engine
add_rounded_rect(s, Inches(3.0), Inches(4.25), Inches(7.3), Inches(0.85),
                 fill_color=RGBColor(0x08, 0x1A, 0x18),
                 border_color=TEAL_700,
                 text="🧠  AI Investigation Engine  (GPT-5.1 + Responses API + 24 Tools)",
                 text_size=13, text_color=TEAL_400, bold=True)
add_text(s, Inches(3.2), Inches(4.8), Inches(6.9), Inches(0.25),
         "Chain-of-thought → tool calls (up to 6 rounds) → structured JSON output",
         size=7, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
add_arrow_down(s, Inches(6.65), Inches(5.15))

# Tier 4: Outputs
outputs = ["🎯 RCA", "🛠️ Fix Strategy", "💥 Blast Radius", "📋 Post-Mortem", "📈 Score"]
for i, name in enumerate(outputs):
    x = Inches(1.3 + i * 2.2)
    add_rounded_rect(s, x, Inches(5.5), Inches(1.9), Inches(0.55), BG_CARD,
                     border_color=TEAL_700, text=name, text_size=9, text_color=WHITE)
add_arrow_down(s, Inches(6.65), Inches(6.1))

# Tier 5: Delivery
delivery = [("🌐 React Web", TEAL_400), ("💬 Teams Bot", TEAL_400),
            ("⌨️ CLI REPL", TEAL_400), ("🔌 REST API", TEAL_400)]
for i, (name, clr) in enumerate(delivery):
    x = Inches(2.0 + i * 2.5)
    add_rounded_rect(s, x, Inches(6.55), Inches(2.0), Inches(0.5),
                     BG_CARD, border_color=TEAL_600,
                     text=name, text_size=10, text_color=clr, bold=True)

# ═══════════════════════════════════════════════════════════
# SLIDE 11 — TECH STACK
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "TECH STACK", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "Built With Production-Grade Tools.", size=38, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
# Backend card
add_rounded_rect(s, Inches(0.8), Inches(2.2), Inches(5.8), Inches(4.5), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(1.0), Inches(2.3), Inches(5.4), Inches(0.4),
         "🐍 Backend — Python", size=12, color=TEAL_400, bold=True)
backend = ["FastAPI + Uvicorn", "SQLAlchemy 2.0", "PostgreSQL + Alembic",
           "LiteLLM + OpenAI SDK", "Azure SDK Suite", "Kubernetes Client",
           "Elasticsearch 9.x", "Bot Framework SDK", "Pydantic + Settings",
           "ReportLab (PDF)", "httpx + aiohttp", "pytest + ruff"]
for i, name in enumerate(backend):
    col = i % 2
    row = i // 2
    add_text(s, Inches(1.2 + col * 2.7), Inches(2.85 + row * 0.55), Inches(2.5), Inches(0.35),
             f"• {name}", size=10, color=TEXT_SEC)
# Frontend card
add_rounded_rect(s, Inches(6.9), Inches(2.2), Inches(5.8), Inches(4.5), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(7.1), Inches(2.3), Inches(5.4), Inches(0.4),
         "⚛️ Frontend — React + TypeScript", size=12, color=TEAL_400, bold=True)
frontend = ["React 18 + Vite 5", "TypeScript 5.4", "Tailwind CSS 4",
            "React Router 6", "TanStack Query 5", "Recharts + Nivo",
            "React Flow (Topology)", "Framer Motion", "Mermaid.js",
            "jsPDF + html2canvas"]
for i, name in enumerate(frontend):
    col = i % 2
    row = i // 2
    add_text(s, Inches(7.3 + col * 2.7), Inches(2.85 + row * 0.55), Inches(2.5), Inches(0.35),
             f"• {name}", size=10, color=TEXT_SEC)
# AI Model callout
add_text(s, Inches(7.1), Inches(5.8), Inches(5.4), Inches(0.3),
         "🧠 AI Model", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(7.3), Inches(6.1), Inches(5.2), Inches(0.3),
         "• Azure AI Foundry GPT-5.1 (Responses API)", size=10, color=WHITE, bold=True)
add_text(s, Inches(7.5), Inches(6.4), Inches(5.0), Inches(0.3),
         "Chain-of-thought reasoning │ Streaming │ Function calling", size=8, color=TEXT_MUTED)

# ═══════════════════════════════════════════════════════════
# SLIDE 12 — BY THE NUMBERS
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "BY THE NUMBERS", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "What We Built.", size=42, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
stats_row1 = [("32K+", "Lines of code\n(Python + TypeScript)"),
              ("42", "API endpoints\n(REST + SSE streaming)"),
              ("24", "AI tool functions\n(agentic + pipeline)"),
              ("13", "Adapters &\nintegrations")]
stats_row2 = [("437", "Automated tests\n(all passing ✅)"),
              ("14", "Database\nmigrations"),
              ("20+", "APIM analytics\nquery templates"),
              ("5", "SSE event types\n(real-time streaming)")]
for row_idx, row_stats in enumerate([stats_row1, stats_row2]):
    for i, (val, label) in enumerate(row_stats):
        x = Inches(1.0 + i * 3.0)
        y = Inches(2.5 + row_idx * 2.3)
        add_rounded_rect(s, x, y, Inches(2.5), Inches(1.8), BG_CARD,
                         border_color=RGBColor(0x1E, 0x2D, 0x3D))
        add_text(s, x + Inches(0.2), y + Inches(0.2), Inches(2.1), Inches(0.7),
                 val, size=34, color=TEAL_400, bold=True, align=PP_ALIGN.CENTER)
        add_text(s, x + Inches(0.2), y + Inches(1.0), Inches(2.1), Inches(0.6),
                 label, size=9, color=TEXT_MUTED, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 13 — LIVE DEMO
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(0.8), Inches(0.5), Inches(4), Inches(0.4),
         "LIVE DEMO", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(0.8), Inches(1.0), Inches(5.5), Inches(0.8),
         "Let's see it in action.", size=34, color=WHITE, bold=True)
demo_steps = [("Alert: 503 Spike on fundapis", "Azure Monitor fires — API error rate jumps to 40%"),
              ("Evidence gathered automatically", "Container logs, APIM gateway, AKS context — all in parallel"),
              ("AI thinking streamed live", "Watch chain-of-thought reasoning unfold in real time"),
              ("RCA + Fix in ~30 seconds", "Root cause, confidence score, kubectl commands ready"),
              ("One-click approve & execute", "Human reviews → approves → Corvin runs the fix")]
for i, (title, desc) in enumerate(demo_steps):
    y = Inches(2.2 + i * 1.0)
    # timeline dot
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.0), y + Inches(0.05),
                              Inches(0.18), Inches(0.18))
    dot.fill.solid()
    dot.fill.fore_color.rgb = TEAL_400
    dot.line.fill.background()
    add_text(s, Inches(1.4), y - Inches(0.05), Inches(5.0), Inches(0.35),
             title, size=12, color=WHITE, bold=True)
    add_text(s, Inches(1.4), y + Inches(0.3), Inches(5.0), Inches(0.3),
             desc, size=9, color=TEXT_MUTED)
# Right side — speed card
add_rounded_rect(s, Inches(7.5), Inches(1.5), Inches(5.0), Inches(2.0), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(7.8), Inches(1.7), Inches(4.4), Inches(0.5),
         "⚡", size=36, align=PP_ALIGN.CENTER)
add_text(s, Inches(7.8), Inches(2.2), Inches(4.4), Inches(0.5),
         "~30 seconds", size=24, color=TEAL_400, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(7.8), Inches(2.8), Inches(4.4), Inches(0.4),
         "From alert to actionable fix", size=11, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
# Before/After
add_rounded_rect(s, Inches(7.5), Inches(3.8), Inches(5.0), Inches(1.3), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(8.0), Inches(3.9), Inches(1.5), Inches(0.3),
         "BEFORE", size=8, color=TEXT_MUTED, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(8.0), Inches(4.2), Inches(1.5), Inches(0.5),
         "37m", size=28, color=RED, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(9.7), Inches(4.3), Inches(0.6), Inches(0.4),
         "→", size=22, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
add_text(s, Inches(10.5), Inches(3.9), Inches(1.5), Inches(0.3),
         "AFTER", size=8, color=TEXT_MUTED, bold=True, align=PP_ALIGN.CENTER)
add_text(s, Inches(10.5), Inches(4.2), Inches(1.5), Inches(0.5),
         "30s", size=28, color=TEAL_400, bold=True, align=PP_ALIGN.CENTER)
# Live on Azure card
add_rounded_rect(s, Inches(7.5), Inches(5.4), Inches(5.0), Inches(1.6), BG_CARD,
                 border_color=RGBColor(0x1E, 0x2D, 0x3D))
add_text(s, Inches(7.8), Inches(5.5), Inches(4.4), Inches(0.3),
         "LIVE ON AZURE", size=8, color=TEXT_MUTED, bold=True, align=PP_ALIGN.CENTER)
add_rounded_rect(s, Inches(7.8), Inches(5.9), Inches(4.4), Inches(0.42),
                 fill_color=RGBColor(0x0D, 0x25, 0x20), border_color=TEAL_700,
                 text="🌐 React UI — Azure Static Web Apps", text_size=9, text_color=TEAL_400)
add_rounded_rect(s, Inches(7.8), Inches(6.4), Inches(4.4), Inches(0.42),
                 fill_color=RGBColor(0x14, 0x14, 0x28), border_color=PURPLE,
                 text="🔌 FastAPI Backend — Azure App Service", text_size=9,
                 text_color=RGBColor(0xA5, 0xB4, 0xFC))

# ═══════════════════════════════════════════════════════════
# SLIDE 14 — SAFETY / GOVERNANCE
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "GOVERNANCE", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "AI That You Can Trust.", size=40, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
safety = [("🔒", "Human-in-the-Loop",
           "No fix executes without explicit human approval. Full audit trail on every action."),
          ("🧠", "Transparent Reasoning",
           "Chain-of-thought is streamed and stored. See exactly how the AI reaches conclusions."),
          ("📊", "Confidence Scoring",
           "Every RCA includes a confidence percentage with reasoning — you know when to trust it.")]
for i, (icon, title, desc) in enumerate(safety):
    x = Inches(1.0 + i * 4.0)
    y = Inches(2.5)
    add_rounded_rect(s, x, y, Inches(3.5), Inches(2.8), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.5), y + Inches(0.3), Inches(2.5), Inches(0.5),
             icon, size=28, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.3), y + Inches(1.0), Inches(2.9), Inches(0.4),
             title, size=14, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.3), y + Inches(1.6), Inches(2.9), Inches(0.9),
             desc, size=10, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
pill_y = Inches(5.8)
for i, (txt, clr) in enumerate([("  Read-Only Evidence", TEAL_500),
                                  ("  Approval Gate", AMBER),
                                  ("  Full Audit Trail", CYAN)]):
    add_pill(s, Inches(2.8 + i * 2.8), pill_y, txt, clr)

# ═══════════════════════════════════════════════════════════
# SLIDE 15 — IMPACT
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1), Inches(0.5), Inches(4), Inches(0.4),
         "IMPACT", size=10, color=TEAL_400, bold=True)
add_text(s, Inches(1.5), Inches(1.0), Inches(10.3), Inches(0.8),
         "What Changes With Corvin.", size=40, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
impact_stats = [("74×", "Faster investigation\n(37 min → 30 sec)"),
                ("90%", "Reduction in\nMTTR"),
                ("24/7", "Always-on AI\nSRE coverage"),
                ("0", "New agents\nto deploy")]
for i, (val, label) in enumerate(impact_stats):
    x = Inches(1.0 + i * 3.0)
    y = Inches(2.8)
    add_rounded_rect(s, x, y, Inches(2.6), Inches(2.2), BG_CARD,
                     border_color=RGBColor(0x1E, 0x2D, 0x3D))
    add_text(s, x + Inches(0.2), y + Inches(0.3), Inches(2.2), Inches(0.8),
             val, size=40, color=TEAL_400, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, x + Inches(0.2), y + Inches(1.3), Inches(2.2), Inches(0.7),
             label, size=11, color=TEXT_MUTED, align=PP_ALIGN.CENTER)
add_text(s, Inches(2), Inches(5.5), Inches(9.3), Inches(0.6),
         "Plugs into your existing Azure stack.\nNo new infra. No data migration. Value from day one.",
         size=14, color=TEXT_SEC, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SLIDE 16 — CLOSING
# ═══════════════════════════════════════════════════════════
s = prs.slides.add_slide(blank)
set_slide_bg(s)
add_text(s, Inches(1.5), Inches(1.5), Inches(10.3), Inches(2.5),
         "Investigate smarter.\nResolve faster.\nSleep better.",
         size=48, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
# Separator
sep = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.2), Inches(4.2), Inches(0.9), Inches(0.04))
sep.fill.solid()
sep.fill.fore_color.rgb = TEAL_500
sep.line.fill.background()
add_text(s, Inches(2), Inches(4.5), Inches(9.3), Inches(0.5),
         "Corvin — Your AI SRE Co-Pilot", size=18, color=TEXT_SEC, align=PP_ALIGN.CENTER)
# Pills
pill_y = Inches(5.3)
for i, (txt, clr) in enumerate([("  Azure-Native", TEAL_500),
                                  ("  Python + React + FastAPI", CYAN),
                                  ("  GPT-5.1 Powered", GREEN)]):
    add_pill(s, Inches(2.8 + i * 2.8), pill_y, txt, clr)
# Live links
add_rounded_rect(s, Inches(4.2), Inches(6.0), Inches(2.2), Inches(0.5),
                 fill_color=TEAL_700, border_color=TEAL_600,
                 text="🌐 Try Live UI", text_size=11, text_color=WHITE, bold=True)
add_rounded_rect(s, Inches(6.8), Inches(6.0), Inches(2.2), Inches(0.5),
                 fill_color=BG_CARD, border_color=TEAL_600,
                 text="🔌 API Docs", text_size=11, text_color=TEAL_400, bold=True)
# URLs below buttons
add_text(s, Inches(2.5), Inches(6.6), Inches(8.3), Inches(0.3),
         "mango-hill-0639bd600.7.azurestaticapps.net   │   corvin-api-akhyb9aaa8hpbxg9.australiaeast-01.azurewebsites.net",
         size=7, color=TEXT_MUTED, align=PP_ALIGN.CENTER)

# ═══════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════
output = "corvin-deck.pptx"
prs.save(output)
print(f"✅ Saved {output} — {len(prs.slides)} slides")

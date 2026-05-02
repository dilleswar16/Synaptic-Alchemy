# Corvin V3 — Scope and Capabilities

## What Is V3?

V3 is the **Premium Polish & Reporting** release. It focuses on making Corvin
visually stunning, demonstrating SRE team health trends over time, and completing
the incident lifecycle workflow with the auto-generated Blameless Post-Mortem.

This version is designed specifically for the hackathon presentation to highlight
the "Ways of Working" theme—automating tedious reporting tasks and presenting
a premium, enterprise-grade user interface.

---

## V3 Focus Areas

1. **Premium React Dashboard** — Full Glassmorphism / Dark Mode CSS overhaul with micro-animations. A new SRE Health Dashboard homepage showing MTTR, auto-resolved rates, and daily investigation counts.
2. **Streaming AI Visualizer** — During an investigation, the UI parses the incoming JSON stream and renders the RCA tokens flowing in real-time as readable prose.
3. **Blameless Post-Mortem Auto-Generator** — A new API endpoint that uses the V2.5 Transparency Replay payload to write a formatted Markdown post-mortem (detection timeline + RCA + fix + prevention steps) for completed incidents.

---

## What About Semantic Search (RAG)?

*Note: Semantic Search (vectorized RAG) is officially scheduled for **V4**.*
The current keyword-based runbook injection ("Poor Man's RAG" built in V1.5) provides perfectly deterministic, reliable results for the hackathon demo without the infrastructure overhead of standing up a Vector Database right before the presentation. This represents a deliberate architectural roadmap decision.

---

## V3 Exit Criteria

- [ ] The React UI uses a custom CSS design system with dark mode, glassmorphism panels, and smooth animations.
- [ ] A Post-Mortem Markdown document is auto-generated and available for download on resolved investigations.
- [ ] The SRE Health Dashboard homepage displays current metric cards.
- [ ] V2 and V2.5 capabilities remain fully stable.

---

## Notes

V3 is the final submission version. The focus is entirely on Visual Impact
and Enterprise Value (reporting/compliance).


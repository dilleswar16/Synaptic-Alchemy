# Corvin V3 — Scope and Capabilities

## What Is V3?

V3 is the **Premium Polish & Reporting** release. It focuses on making Corvin
visually stunning, demonstrating SRE team health trends over time, and completing
the post-incident workflow with the auto-generated Blameless Post-Mortem.

---

## V3 Focus Areas

1. **Premium React Dashboard** — Full Glassmorphism / Dark Mode CSS overhaul with micro-animations, live pulsating AI activity nodes, and a premium UI that wows on first glance.
2. **Blameless Post-Mortem Auto-Generator** — When an incident is marked Resolved, Corvin auto-generates a formatted Markdown post-mortem (detection timeline + RCA + fix + prevention steps).
3. **Corvin Score / SRE Health Dashboard** — 30-day view of MTTR, auto-resolved vs human-resolved counts, and incident trend graphs.

---

## V3 Focus Areas

- Slice 1: Premium CSS design system (tokens, dark mode, glassmorphism panels)
- Slice 2: Live AI activity visualiser — animated node graph during investigation
  - **Enhancement A — Real-time JSON token filtering:** During streaming, parse the incoming JSON tokens and render only the human-readable string values (skip keys, brackets, punctuation). Users see prose flowing in rather than raw JSON. Implement as a small `parseStreamToken(accumulated, newToken)` utility in `StreamingProgress.tsx` — strip structural characters and emit only content inside quoted values.
  - **Enhancement B — Reasoning model support (o1/o3):** Switch `config/models/llm.yaml` primary model to `azure/o3` or `azure/o1`. These models expose a `reasoning_content` field (thinking steps) before the final answer. Pipe `reasoning_content` tokens to a separate "Thinking..." box and final answer tokens to the existing terminal box. This gives the true "watch the AI think" experience. Requires `stream_options: {"include_usage": true}` and reading `chunk.choices[0].delta.reasoning_content` in the generator.
- Slice 3: PostMortemService — synthesise RCA + execution timeline into Markdown doc
- Slice 4: Post-mortem page in React UI + download as Markdown
- Slice 5: Corvin Score dashboard page — MTTR trend, auto-resolved rate, incident volume

---

## V3 Exit Criteria

- [ ] The React UI uses a custom CSS design system with dark mode, glassmorphism panels, and smooth animations.
- [ ] A Post-Mortem Markdown document is auto-generated and available for download on every resolved investigation.
- [ ] The Corvin Score dashboard shows meaningful 30-day trend data.
- [ ] V2 and V2.5 capabilities remain fully stable.

---

## Notes

V3 is the final submission version. If time is tight, prioritise the Premium UI
overhaul (Slice 1+2) and the Post-Mortem generator (Slice 3+4) as these have
the highest visual and storytelling impact for the hackathon judges.
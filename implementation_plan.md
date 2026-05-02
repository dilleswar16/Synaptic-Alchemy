# V3 Hackathon Polish & Reporting (Implementation Plan)

This plan outlines the V3 feature set tailored specifically to win the "Ways of Working" hackathon theme.

## Core Objective
Transform Corvin from a powerful backend engine into an enterprise-grade, visually stunning SRE product that automates the incident lifecycle from detection to post-mortem documentation.

---

## 1. Premium React Dashboard (The WOW Factor)
The React application (`apps/web`) will be completely overhauled.
- **Design System:** Deep dark mode by default, glassmorphism panels (frosted glass effects), and smooth micro-animations on state transitions.
- **SRE Health Dashboard (Home):** The default view will feature three primary metric cards:
  - *Investigations Today*
  - *Mean Time To Resolution (MTTR)*
  - *Automation Success Rate*
- **Streaming RCA View:** The investigation detail page will stream the AI's response token-by-token. Instead of rendering raw JSON, the UI will parse the stream and render the RCA and Fix Strategy as prose in real-time, giving the judges the "watch the AI think" experience.

## 2. Auto-Generated Blameless Post-Mortems (Ways of Working)
Automating the most tedious part of an SRE's job: writing incident reports.
- **Backend (`apps/api/routes/investigations.py`):** A new endpoint `GET /investigations/{id}/postmortem`.
- **Logic:** This endpoint takes the transparency payload (from the V2.5 Replay feature) and uses the `RCAGenerator` (or a new `PostMortemGenerator`) to synthesize a professional Markdown document.
- **Content:** The document will contain an Incident Detection Timeline, Root Cause Analysis, Remediation Steps Taken, and Future Prevention Strategies.
- **Frontend:** A prominent "Generate Post-Mortem" button on completed investigations that renders the Markdown or triggers a download.

## 3. V4 / Future Roadmap Prep
To ensure the hackathon presentation is forward-looking:
- **Semantic Search (RAG):** The current exact-keyword runbook matching (Poor Man's RAG) will be documented as transitioning to a fully vectorized Semantic Search database in V4. This avoids heavy infrastructure risk before the demo while showing architectural maturity.

---

## Execution Sequence

### Phase 1: Frontend Foundation (React UI Overhaul)
1. Initialize the new CSS design system (`index.css` with dark mode/glassmorphism tokens).
2. Build the SRE Health Dashboard layout.
3. Implement the Streaming UI consumer to parse and animate incoming RCA tokens.

### Phase 2: Post-Mortem Generator (Backend + Frontend)
1. Build `PostMortemGenerator` in `corvin/strategy/`.
2. Wire the `GET /investigations/{id}/postmortem` API route.
3. Add the "Generate Post-Mortem" UI component to the React app.

### Phase 3: Final Integration & Polish
1. End-to-end testing of the complete V3 flow.
2. Final cosmetic tweaks for the hackathon presentation.

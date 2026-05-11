# Corvin Hackathon Feature Roadmap

**Status at time of writing:** V3+ complete, 381/381 tests passing.  
**Next locked version:** V4 — Semantic Search / Vector RAG (requires pgvector on Azure Postgres).  
**This file:** defines three intermediate versions (V3.5, V3.7, V3.9) that slot between V3+ and V4.

---

## Version Gate Summary

| Version | Theme | Status |
| :--- | :--- | :--- |
| V1–V3+ | Core platform + polish | ✅ Complete |
| **V3.5** | Demo-critical: Alert Simulator, Teams Cards, Blast Radius, Corvin Score | 🔒 Next |
| **V3.7** | Intelligence layer: Predictive Detection, SLA Countdown, Dependency Visualizer, Remediation Preview | 🔒 Locked |
| **V3.9** | Polish + enterprise: ROI Dashboard, Voice TTS, 3AM Mode, Runbook Auto-Update, War Room, Confidence Routing | 🔒 Locked |
| **V4** | Semantic Search / Vector RAG (pgvector) | 🔒 Locked |

Do NOT start a version until the previous version's exit criteria are met.

---

## V3.5 — Demo Core (Build These First)

**Theme:** The 90-second live demo must be possible without any real incident happening.  
**Exit criteria:** Alert Simulator fires a full investigation end-to-end. Teams Adaptive Card appears with working approve button. Dashboard shows Corvin Score gauges. Blast Radius card visible on investigation detail page.

### Feature 1 — Alert Simulator (Fake Incident Button)

**Why first:** Everything else in the demo depends on being able to trigger an investigation on demand. Without this, the live demo is fragile and depends on a real incident.

**What it does:**
- UI button/panel (on Dashboard or Investigations page): "Simulate Alert"
- Presets: 503 Spike / partnerapis, HPA Failure / partnerapis, Memory Leak / fundapis, Auth Errors / fundsso
- Free-text mode: type a natural-language description, pick a service
- POSTs a synthetic Azure Monitor alert payload to `/triggers/azure-alert`
- Fires the full real pipeline: enrich → RCA → fix strategy → Teams card
- Shows the streaming progress panel immediately after

**Implementation notes:**
- Backend: `POST /triggers/simulate` — builds a `CommonAlertSchema`-compatible payload, calls the same handler as real alerts
- Frontend: `SimulateAlertPanel` component on Dashboard page. Preset buttons + optional description field.
- No new adapters needed — re-uses everything already wired

**Demo power: 10/10.** This IS the demo.

---

### Feature 2 — Teams Adaptive Card with Inline Approve/Reject

**Why:** Current Teams integration sends a plain text webhook message. Adaptive Cards give you actual buttons inside Teams that POST back to Corvin. SRE approves without opening a browser.

**What it does:**
- On investigation complete, send an Adaptive Card (JSON) via Teams webhook instead of plain text
- Card contains: service name, environment, confidence badge, root cause summary, top fix action, estimated blast radius (if available), APPROVE / REJECT buttons
- APPROVE button POSTs `{"action": "approve", "investigation_id": "..."}` to `/teams/action`
- REJECT button POSTs `{"action": "reject", ...}` — updates approval_status in DB
- Response card: "✅ Approved by [user] at 14:32" / "❌ Rejected"

**Implementation notes:**
- `corvin/delivery/teams_adapter.py` — add `send_adaptive_card()` method alongside existing `send_message()`
- `apps/teams/router.py` — add `POST /teams/action` endpoint
- Teams requires the webhook to accept the card schema — use `$schema: http://adaptivecards.io/schemas/adaptive-card.json`, `version: 1.4`
- Note: Outbound webhooks don't support action callbacks directly — need Azure Bot Framework registration for full two-way. For hackathon: use a separate `/teams/action` endpoint and document the Bot Framework path as V2.5-style upgrade.

**Demo power: 9/10.** Live card appears in Teams during the demo. Judges click Approve.

---

### Feature 3 — Blast Radius Estimator

**Why:** Translates "CPU throttling on pod X" into "£240/min revenue at risk · 800 affected users." Non-technical judges instantly understand urgency.

**What it does:**
- On investigation complete, compute a `BlastRadiusEstimate`:
  - `affected_services`: from AKS evidence (failing pods) + APIM logs (dependent ApiIds)
  - `estimated_users`: current replica count × configurable users-per-replica (site.md or config)
  - `revenue_risk_per_min`: configurable in `config/policies/investigation.yaml`
  - `downstream_services`: list of APIM ApiIds that route through the affected backend
- Displayed as an amber banner at the top of `InvestigationDetailPage`
- Also included in the Teams Adaptive Card

**Implementation notes:**
- `corvin/strategy/blast_radius.py` — new module, pure calculation, no LLM needed
- Input: `EvidenceBundle` + site config
- Output: `BlastRadiusEstimate` Pydantic model
- Add `blast_radius` field to `InvestigationResult` contract + DB column (migration needed)
- Frontend: `BlastRadiusCard` component — amber background, icons for users/services/revenue

**Demo power: 9/10.**

---

### Feature 4 — Corvin Score (Per-Service Health Gauge)

**Why:** Opens the demo with immediate visual impact. Judges understand the product in 5 seconds without a word spoken.

**What it does:**
- Score 0–100 per service, shown as large circular gauges on the Dashboard
- Formula: weighted average of:
  - Incident frequency last 30 days (lower = better)
  - Average RCA confidence (higher = better)
  - Average MTTR (lower = better)
  - Days since last incident (higher = better)
  - Fix success rate (higher = better)
- Color: green ≥80, amber 50–79, red <50
- Clicking a gauge navigates to that service's investigation history

**Implementation notes:**
- `GET /investigations/score?service_name=X&environment=Y` — new endpoint
- `InvestigationRepository.get_service_score(service, env)` — aggregate query
- Frontend: `ServiceHealthGauge` component — SVG arc gauge, animated fill on load
- Replace the current bar chart section on Dashboard with 3 gauges (fundapis / fundsso / partnerapis)

**Demo power: 8/10.** The first thing on screen.

---

## V3.7 — Intelligence Layer

**Theme:** Proactive detection, explainability, and visual system understanding.  
**Exit criteria:** Predictive alert card visible on dashboard. SLA countdown shown on active investigations. Dependency visualizer renders real AKS/APIM topology. Remediation preview shows before/after state.

### Feature 5 — Predictive Incident Detection ("Pre-Mortem Mode")

**Why:** Every other SRE tool is reactive. Corvin becomes proactive. This is the single biggest philosophical differentiator.

**What it does:**
- Background poller (configurable interval, default 5 min) queries Log Analytics for trending metrics
- Triggers if: memory grows >15%/hr, error rate climbs >5%/min for 3 consecutive windows, or pod restarts accelerate
- Raises a `PredictiveAlert` card on the Dashboard: "⚠ fundapis memory trending toward OOM — estimated breach in ~4 hours. Investigate now?"
- "Investigate Now" button fires a manual investigation with `trigger_source=PREDICTIVE`
- No alert fired yet = no downtime = investigation catches it early

**Implementation notes:**
- `corvin/triggers/predictive.py` — new poller, runs as background task via FastAPI `asyncio.create_task`
- Thresholds configurable in `config/policies/investigation.yaml`
- `PredictiveAlert` stored in a new `predictive_alerts` table or as a special `InvestigationRequest` with `trigger_source=PREDICTIVE`
- Frontend: `PredictiveAlertBanner` on Dashboard — amber pulsing border

**Demo power: 9/10 on story.** "Corvin detected this before the outage happened."

---

### Feature 6 — SLA Breach Countdown

**Why:** Turns abstract uptime percentages into a ticking clock. Approval decisions happen faster.

**What it does:**
- On investigation detail page for active/pending investigations: calculate time remaining until SLA breach
- Formula: `(monthly_budget_seconds - seconds_already_down_this_month) / current_downtime_rate`
- Shows: "⏱ 99.9% SLA breach in 1h 12m" — amber when <2h, red when <30m
- Disappears once fix is approved and executed

**Implementation notes:**
- SLA target configurable in `config/policies/investigation.yaml`
- Downtime seconds sourced from APIM logs (error rate × time window)
- `SlaCountdown` React component — `useEffect` with 1s interval, no backend polling needed once data loaded

**Demo power: 8/10.** The ticking clock creates tension in the live demo.

---

### Feature 7 — One-Click Remediation Preview ("What Will Run")

**Why:** #1 enterprise AI fear: "what is it going to do to my cluster?" Show the exact commands before they run. Builds trust.

**What it does:**
- On Fix Strategy page, each action shows:
  - Current state: "fundapis: 2 replicas / CPU throttle events: 1,200/min"
  - Proposed command: `kubectl scale deployment/fundapis --replicas=5 -n chad`
  - After state: "fundapis: 5 replicas / estimated CPU throttle reduction: ~80%"
- "Approve & Execute" button only enabled after viewing this panel

**Implementation notes:**
- `corvin/execution/preview.py` — builds preview from `FixAction` + current AKS evidence
- Backend: `GET /investigations/{id}/fix-preview` — returns `RemediationPreview` model
- Frontend: `RemediationPreviewPanel` on Fix Strategy page — before/after diff style layout

**Demo power: 8/10.** "We show you exactly what runs before it runs."

---

### Feature 8 — Cross-Service Dependency Visualizer

**Why:** Pure visual impact. Live service graph with incident node glowing red and downstream services in amber. Most visually stunning feature on the list.

**What it does:**
- Auto-generates a service dependency graph from:
  - APIM logs: which ApiIds call which BackendIds
  - AKS: which deployments exist in the `chad` namespace
- Renders as an interactive force-directed graph (D3.js or React Flow)
- Normal state: nodes are neutral
- During/after an incident: affected service node glows red, downstream nodes glow amber
- Clicking a node navigates to that service's latest investigation

**Implementation notes:**
- `GET /investigations/topology` — new endpoint, queries APIM + AKS evidence, returns `{nodes, edges}`
- Frontend: new `TopologyPage` or overlay on Dashboard — React Flow (already available via npm)
- Node colors driven by latest investigation status + Corvin Score
- No new adapters needed — uses existing `LogAnalyticsAdapter` + `AKSAdapter`

**Demo power: 9/10.** Most visually impressive screen in the product.

---

## V3.9 — Enterprise Polish

**Theme:** Business case, operator experience, and learning loop.  
**Exit criteria:** ROI dashboard shows real numbers. Voice briefing plays. 3AM mode toggleable. Runbook auto-update prompts after successful fix. War room channel creation confirmed.

### Feature 9 — Runbook Auto-Update After Successful Fix

**Why:** The learning loop made visible. System gets smarter after every incident. Addresses runbook rot — the real problem where runbooks fall out of date immediately.

**What it does:**
- After a fix is executed + verified (approval_status = `executed`):
  - Prompt appears: "✏ This fix worked. Update the runbook for [service]?"
  - Corvin generates a new resolution step as a Markdown diff (LLM call: "given this RCA and fix, write a concise runbook step")
  - One click appends the step to `knowledge/runbooks/[service].md` and updates `catalog.json` `match_patterns`
- Also writes a `knowledge/learnings/[investigation_id].md` entry automatically (the `learnings/` folder already exists)

**Implementation notes:**
- `POST /investigations/{id}/update-runbook` — triggers LLM generation of runbook diff
- `corvin/core/knowledge_loader.py` — add `append_to_runbook(service, content)` method
- Frontend: `RunbookUpdatePrompt` card on Fix Strategy page when `approval_status = executed`
- Note: `knowledge/learnings/` already exists — this wires it to real content

**Note:** The `knowledge/learnings/` folder exists but nothing writes to it automatically yet. This feature makes it live.

**Demo power: 7/10.** The "it learned from this incident" moment.

---

### Feature 10 — ROI / Cost Impact Dashboard

**Why:** Every non-technical judge will ask "what's the business case?" You answer before they ask, with a real number.

**What it does:**
- Dedicated section on Dashboard: "Corvin ROI This Month"
  - Incidents handled: N
  - Avg MTTR before Corvin (configurable baseline, e.g. 45 min)
  - Avg MTTR with Corvin (calculated from DB)
  - Hours saved: `(baseline_mttr - actual_mttr) × incident_count`
  - Cost saved: `hours_saved × engineer_hourly_rate` (configurable)
- Configurable in `config/policies/investigation.yaml`: `baseline_mttr_minutes`, `engineer_hourly_rate_gbp`

**Implementation notes:**
- `GET /investigations/roi?months=1` — new endpoint
- `InvestigationRepository.get_roi_stats(months)` — aggregate query
- Frontend: `RoiWidget` on Dashboard — large number display, trend arrow

**Demo power: 7/10 on its own. Closing slide: 10/10.** "This month: £3,760 saved."

---

### Feature 11 — Voice Morning Briefing (Azure TTS)

**Why:** Nobody else is doing this. Makes Corvin feel like JARVIS. The most memorable moment in the demo.

**What it does:**
- "▶ Play" button on the Morning Briefing widget
- Calls Azure Cognitive Services Text-to-Speech with the briefing narrative text
- Natural voice reads: *"Good morning. You had two incidents overnight. At 2:15 AM, fundapis experienced a memory spike — resolved in 18 minutes..."*
- Audio plays in-browser via `<audio>` element

**Implementation notes:**
- `GET /investigations/briefing/audio` — streams TTS audio bytes
- Uses `azure-cognitiveservices-speech` Python SDK (already in Azure ecosystem)
- New env var: `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`
- Frontend: add play/pause button to `BriefingWidget`, fetch audio blob, play via Web Audio API

**Demo power: 10/10 for memorability.** Room goes quiet. Judges remember this.

---

### Feature 12 — 3 AM Mode (Minimal Cognitive Load UI)

**Why:** Shows empathy for the user that most tools miss. Most sophisticated SRE tool in the world fails if the sleep-deprived engineer can't read it at 3 AM.

**What it does:**
- Toggle in the NavBar: "☽ 3AM Mode"
- Strips the detail page to 3 sections only: WHAT BROKE · WHY IT BROKE · WHAT TO DO
- Large font (20px+), maximum contrast, single column, no decorative UI
- Hides: audit trail, similar incidents, post-mortem, charts
- Remembers preference in `localStorage`

**Implementation notes:**
- `usePrefersSimpleMode()` hook — reads `localStorage.getItem('corvin-3am-mode')`
- All detail page components accept `simpleMode?: boolean` prop that reduces to essentials
- No backend changes needed

**Demo power: 6/10 as a feature. 10/10 as a story.** "We designed this for engineers woken at 3 AM."

---

### Feature 13 — Confidence-Weighted Approval Routing

**Why:** Smart AI deference. Not everything needs a human. Not everything should run automatically. The system calibrates.

**What it does:**
- High confidence (≥80%) + low-risk action + non-prod environment → auto-approve, notify only
- Medium confidence (50–79%) → standard Teams approval flow
- Low confidence (<50%) → requires 2 approvals + mandatory human RCA review note
- Configurable thresholds in `config/policies/investigation.yaml`

**Implementation notes:**
- `corvin/execution/approval_router.py` — new module, evaluates confidence + risk level + environment
- Called from the investigation stream completion handler
- Policy config: `auto_approve_confidence_threshold`, `dual_approval_confidence_threshold`, `auto_approve_environments`

**Demo power: 7/10.** "Corvin knows when to ask for help and when to handle it."

---

### Feature 14 — Incident War Room (Auto-Create Teams Channel)

**Why:** P1 war room setup takes 15-20 minutes. Corvin makes it instant.

**What it does:**
- For P1 incidents (configurable by alert severity or manual flag):
  - Auto-creates a Teams channel named `INC-YYYY-MM-DD-[service]`
  - Posts the investigation Adaptive Card as the pinned message
  - Posts real-time updates as the investigation progresses

**Implementation notes:**
- Requires Microsoft Graph API access (Teams channel creation)
- New env vars: `MICROSOFT_GRAPH_CLIENT_ID`, `MICROSOFT_GRAPH_CLIENT_SECRET`, `TEAMS_TEAM_ID`
- `corvin/delivery/teams_adapter.py` — add `create_incident_channel()` method
- Gate behind `config/integrations/teams.yaml: war_room_enabled: false` (off by default)

**Demo power: 8/10.** Show the Teams channel auto-appearing during the alert simulation.

---

### Feature 15 — "What Would a Senior SRE Do?" Explainer

**Why:** Explainability is the #1 enterprise AI concern. Proves Corvin isn't a black box.

**What it does:**
- Collapsible section in the RCA panel: "Why did Corvin reach this conclusion?"
- Plain-English narrative: *"I recommended scaling because CPU throttling events exceeded 1,000/min — this pattern correlates with HPA lag 8 of 9 times in your history. I ruled out memory leak because heap metrics are stable."*
- Cites specific evidence numbers and historical incidents

**Implementation notes:**
- Add `explanation` field to `RCAOutput` contract
- `RCAGenerator` builds this in a second LLM pass (or extend the main prompt to include it)
- Frontend: `RcaExplainerSection` — collapsible, below the confidence bar

**Demo power: 8/10.** The judges skeptical of AI will love this most.

---

## Priority Build Order Summary

### For the Hackathon Demo (build in this order):

| # | Feature | Version | Effort | Demo Impact |
| :- | :--- | :--- | :--- | :--- |
| 1 | Alert Simulator | V3.5 | 2h | 🔥 10/10 |
| 2 | Teams Adaptive Card + Approve | V3.5 | 4h | 🔥 9/10 |
| 3 | Blast Radius Estimator | V3.5 | 3h | 🔥 9/10 |
| 4 | Corvin Score Gauge | V3.5 | 2h | ⚡ 8/10 |
| 5 | Remediation Preview | V3.7 | 2h | ⚡ 8/10 |
| 6 | SLA Breach Countdown | V3.7 | 2h | ⚡ 8/10 |
| 7 | Voice Morning Briefing | V3.9 | 3h | 🎯 10/10 memory |
| 8 | Dependency Visualizer | V3.7 | 6h | 🎯 9/10 visual |
| 9 | Predictive Detection | V3.7 | 5h | 🎯 9/10 story |
| 10 | ROI Dashboard | V3.9 | 3h | 🎯 7/10 |
| 11 | Runbook Auto-Update | V3.9 | 3h | 7/10 |
| 12 | 3 AM Mode | V3.9 | 2h | story 10/10 |
| 13 | Confidence Routing | V3.9 | 3h | 7/10 |
| 14 | War Room Channel | V3.9 | 5h | 8/10 |
| 15 | SRE Explainer | V3.9 | 3h | 8/10 |

---

## The 90-Second Demo Script

This is what V3.5 enables (minimum viable demo):

1. Dashboard loads → 3 Corvin Score gauges visible, partnerapis amber (57/100)
2. Click "⚡ Simulate Alert — HPA Failure / partnerapis"
3. Streaming panel opens — Evidence accordion lights up row by row (live)
4. ThinkingPanel shows AI reasoning in purple (chain of thought visible)
5. RCA appears: *"Root cause: HPA misconfiguration. Confidence: High (87%)"*
6. Blast Radius card: *"~800 partner API users · £240/min revenue at risk"*
7. Teams Adaptive Card appears on screen — APPROVE / REJECT buttons visible
8. Click APPROVE — approval_status flips to `approved` in DB
9. Fix executes. Pods scale. Corvin Score for partnerapis ticks up.
10. *(V3.9 add-on)* Voice: *"Incident resolved. Duration: 4 minutes 38 seconds."*

**That sequence, running live, wins the hackathon.**

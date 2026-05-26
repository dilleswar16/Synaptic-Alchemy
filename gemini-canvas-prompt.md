# Gemini Canvas — Corvin Hackathon Presentation Prompt

> **Copy everything below the line into Gemini Canvas** to generate your presentation deck.
> This contains full product context, stats, architecture, and presentation structure.

---

## PROMPT

Create a **10-12 slide hackathon presentation deck** for **Corvin** — an AI-powered SRE (Site Reliability Engineering) Co-Pilot built entirely on Azure. This is for **MetLife's Hackathon 2026**. The audience is senior engineering leaders and judges who evaluate innovation, technical depth, and real-world impact. The deck must feel like a premium SaaS product launch — polished, story-driven, and technically impressive. Not an internal tool walkthrough. Make every slide a mic-drop moment.

### ⏱️ TIME CONSTRAINT
- **Total presentation time: 10 minutes** (~50 seconds per slide average)
- The product walkthrough is woven INTO the slides (slides 8-10 show actual UI screenshots/descriptions)
- There is NO separate "switch to live app" demo segment — the app is shown through the slides themselves
- The presenter may briefly flip to a pre-opened browser tab to show a feature live, then return to slides
- Every slide must earn its place. If it doesn't make judges say "wow", cut it.
- The rest of this document is CONTEXT for you to understand the product deeply. Do NOT try to put everything into slides. Cherry-pick the most impressive bits.

### Suggested 12-Slide Structure
1. **Title + Hook** (15 sec) — Name, tagline, one-liner that grabs attention. Show the live URL.
2. **The Problem** (45 sec) — 3AM pain, 37 minutes, alert fatigue, 5 browser tabs — make judges FEEL the pain
3. **The Solution + Workflow** (1 min) — What Corvin does, the 8-stage pipeline: Trigger → Enrich → Investigate → RCA → Fix → Approve → Execute → Learn. Highlight "30 seconds to RCA."
4. **Agentic AI Engine** (1 min) — 16 tools, 6 reasoning rounds, GPT-5.1, chain-of-thought, streaming — THIS is the intellectual differentiator. Show the tool-calling loop diagram.
5. **Architecture** (45 sec) — 5-tier flow diagram (Triggers → Evidence → AI Engine → Outputs → Delivery). Label data flow between tiers.
6. **Tech Stack** (30 sec) — Two-column: Python backend (12 technologies) + React frontend (10 technologies) + AI model callout
7. **By The Numbers** (30 sec) — Big bold stat cards: 33K+ LOC, 446 tests, 43 endpoints, 16 AI tools, 11 integrations, 16 migrations
8. **Product Tour: Dashboard** (45 sec) — Show/describe the SRE dashboard: Morning Briefing, DORA metrics, Predictive Alerts, Service Topology (React Flow), ROI widget, Corvin Score gauge, Alert Simulator
9. **Product Tour: Command Center** (45 sec) — Show/describe the ChatGPT-style agentic interface: natural language → AI calls tools autonomously → streams thinking → renders Mermaid diagrams → tool result cards. "Ask Corvin anything."
10. **Product Tour: Investigation Flow** (45 sec) — Show/describe: trigger alert → streaming evidence collection → RCA with confidence → fix strategy → blast radius → approve/reject → execute on AKS → post-mortem auto-generated → runbook auto-updated
11. **Impact** (30 sec) — Before/After comparison: 37 min → 30 sec (74x), manual → automated, tribal knowledge → institutionalized. Show the ROI numbers.
12. **Closing** (15 sec) — "Investigate smarter. Resolve faster. Sleep better." + live URLs for judges to try

### Design Direction
- **Dark theme** with teal (#0d9488) as the primary accent color
- Clean, modern, minimal text — big visuals, big numbers, big impact
- Fonts: Inter (headings), JetBrains Mono (code/technical)
- Style inspiration: Vercel's launch decks, Linear's product pages, neubird.ai, flip.ai
- No walls of text. Every slide should have ONE clear takeaway
- Use data visualizations, flow diagrams, and architecture schematics
- For slides 8-10 (Product Tour), describe what the UI looks like so the presenter can either show a screenshot or flip to a live tab
- Include speaker notes for each slide (what to SAY, not what to read)

---

## FULL PRODUCT CONTEXT

### What Is Corvin?
Corvin is an **Azure-native AI SRE Co-Pilot** that monitors Kubernetes applications on AKS, gathers evidence from Azure Log Analytics, APIM, Container Insights, Elastic, and Activity Logs, then uses an LLM (Azure AI Foundry GPT-5.1 via Responses API) to produce structured Root Cause Analysis and fix strategies. SRE teams approve and execute fixes via a React dashboard, Microsoft Teams bot, CLI, or REST API.

**Live URLs (hosted on Azure):**
- React UI: https://mango-hill-0639bd600.7.azurestaticapps.net/
- Backend API (Swagger): https://corvin-api-akhyb9aaa8hpbxg9.australiaeast-01.azurewebsites.net/docs

### The Problem We Solve
- SRE teams spend **37+ minutes** manually investigating each incident
- Alert fatigue: hundreds of alerts, most noise
- 3AM on-call pages → open 5 browser tabs → grep logs → guess root cause → try fixes
- No institutional memory — same incidents recur, same investigation steps repeated
- Knowledge trapped in individual engineers' heads, not in runbooks

### How Corvin Solves It
- **30 seconds** from alert to actionable RCA + fix strategy (74x faster)
- AI gathers evidence from **6 sources in parallel** (APIM, AKS, Container Logs, Activity Log, Elastic, Knowledge Base)
- **Agentic AI** with 16 live tools — the LLM autonomously decides which tools to call, interprets results, and iterates up to 6 rounds
- **Human-in-the-loop** — AI recommends, humans approve, Corvin executes
- **Incident Memory** — learns from past incidents to improve future investigations
- **4 delivery surfaces** — Web Dashboard, Teams Bot, CLI REPL, REST API

---

## ARCHITECTURE (5-tier flow)

```
┌─────────────────────────────────────────────────────────┐
│                    TRIGGER SOURCES                       │
│  Azure Alerts (webhook) │ Alert Simulator (4 scenarios) │
│  CLI │ REST API │ Teams Bot │ Manual                     │
└─────────────────────┬───────────────────────────────────┘
                      │ POST /investigate
                      ▼
┌─────────────────────────────────────────────────────────┐
│              ENRICHMENT LAYER (parallel)                 │
│  📊 APIM Gateway    │ ☸️ AKS Context                    │
│  📦 Container Logs  │ 📝 Activity Log                   │
│  🔍 Elastic         │ 📖 Knowledge + Runbooks           │
│           (20+ KQL templates)                           │
└─────────────────────┬───────────────────────────────────┘
                      │ EvidenceBundle (JSON)
                      ▼
┌─────────────────────────────────────────────────────────┐
│          🧠 AI INVESTIGATION ENGINE                      │
│  Azure AI Foundry GPT-5.1 (Responses API)               │
│  Chain-of-thought │ Function calling │ Streaming SSE     │
│  16 tools │ 6 reasoning rounds │ json_object mode        │
│  RCA + Fix Strategy + Blast Radius + Post-Mortem         │
└─────────────────────┬───────────────────────────────────┘
                      │ InvestigationResult (streamed)
                      ▼
┌─────────────────────────────────────────────────────────┐
│                 OUTPUT ARTIFACTS                         │
│  🎯 RCA Report    │ 🛠️ Fix Strategy   │ 💥 Blast Radius │
│  📋 Post-Mortem   │ 📈 Corvin Score   │ 🔮 Predictions  │
│  📊 DORA Metrics  │ 💰 ROI Dashboard  │ ⏱️ SLA Countdown│
└─────────────────────┬───────────────────────────────────┘
                      │ REST + SSE + PDF + Email
                      ▼
┌─────────────────────────────────────────────────────────┐
│                DELIVERY SURFACES                         │
│  🌐 React Web App  │  💬 Teams Bot (Adaptive Cards)     │
│  ⌨️ CLI REPL       │  🔌 REST API (43 endpoints)        │
│  📧 Email (PDF)    │  📁 SharePoint + ADO Wiki          │
└─────────────────────────────────────────────────────────┘
```

### Storage & Config Layer (side-car)
- **PostgreSQL** with 11 tables, 16 Alembic migrations
- **16 YAML config files** (integrations, models, policies, tools, environments)
- **9 runbooks** with keyword-matching catalog
- **Incident learnings** knowledge base

---

## TECH STACK

### Backend — Python
| Technology | Purpose |
|---|---|
| FastAPI + Uvicorn | Async web framework, 43 REST endpoints |
| SQLAlchemy 2.0 | ORM + async sessions |
| PostgreSQL + Alembic | Persistence + 16 schema migrations |
| LiteLLM + OpenAI SDK | LLM abstraction + Azure AI Foundry |
| Azure SDK Suite | Log Analytics, Container Insights, Activity Log, Comm Services |
| Kubernetes Python Client | AKS pod/deployment/event queries |
| Elasticsearch 9.x | App logs and APM metrics |
| Bot Framework SDK | Teams bot (Adaptive Cards, commands) |
| Pydantic v2 | Domain contracts + validation |
| ReportLab | PDF report generation |
| httpx + aiohttp | Async HTTP clients |
| pytest + ruff | 446 tests + linting |

### Frontend — React + TypeScript
| Technology | Purpose |
|---|---|
| React 18.3 + Vite 5 | SPA framework + build tool |
| TypeScript 5.4 | Type-safe frontend |
| Tailwind CSS 4 | Utility-first styling |
| React Router 6 | Client-side routing |
| TanStack Query 5 | Server state management |
| Recharts + Nivo | Data visualization (area, bar, pie, heatmap) |
| React Flow (@xyflow) | Interactive topology graph |
| Framer Motion | Animations |
| Mermaid.js | Diagram rendering |
| jsPDF + html2canvas | Client-side PDF generation |

### AI Model
- **Azure AI Foundry GPT-5.1** via Responses API
- Chain-of-thought reasoning
- Function calling (16 tools, 6 rounds max)
- Streaming SSE (5 event types: thinking, tool_call, tool_result, text, error)
- json_object response format for structured outputs

---

## AGENTIC AI — THE DIFFERENTIATOR

### Command Center (ChatGPT-style interface)
The **Corvin Command Center** is a ChatGPT-style agentic interface where SREs converse with the platform in natural language. The LLM autonomously decides which tools to call, interprets results, chains actions, and iterates up to 6 reasoning rounds per message.

### 16 Agent Tools (live, callable by the LLM)
| # | Tool | What It Does |
|---|---|---|
| 1 | `get_platform_stats` | Overall SRE health metrics |
| 2 | `list_recent_incidents` | Latest investigations with status |
| 3 | `get_investigation_detail` | Full investigation deep-dive |
| 4 | `get_predictive_alerts` | AI-predicted upcoming issues |
| 5 | `get_service_score` | Corvin Score (0–100 health gauge) |
| 6 | `get_roi` | ROI metrics (hours/cost saved) |
| 7 | `get_service_topology` | Service dependency graph |
| 8 | `get_blast_radius` | Impact estimation |
| 9 | `get_postmortem` | Blameless post-mortem report |
| 10 | `get_similar_incidents` | Incident Memory pattern matching |
| 11 | `get_site_knowledge` | Infrastructure architecture facts |
| 12 | `get_runbook` | Keyword-matched runbook procedures |
| 13 | `run_kql` | Execute live KQL on Log Analytics |
| 14 | `get_aks_health` | Real-time AKS pod/deployment status |
| 15 | `query_apim_analytics` | APIM analytics (20+ KQL templates) |
| 16 | `get_container_resource_metrics` | Container CPU/memory/OOMKill data |

### Tool-Calling Flow
```
User message → LLM decides tool → Execute tool → Return result → LLM reasons → Repeat (up to 6×) → Final response
```

---

## FEATURE INVENTORY (30+ features)

### Core Investigation
- ⚡ **Alert-to-RCA in ~30 seconds** (vs 37 min manual)
- 🧠 **AI Root Cause Analysis** with confidence scoring (High/Medium/Low + reasoning)
- 🛠️ **Fix Strategy Generation** with actionable steps
- 📦 **Parallel Evidence Gathering** from 6 sources
- 🔄 **Streaming SSE** — watch AI think in real-time
- 📋 **Blameless Post-Mortem** auto-generation

### Agentic AI
- 🤖 **Command Center** — ChatGPT-style agentic interface
- 🔧 **16 Live Tools** — LLM autonomously calls tools
- 🔁 **6-Round Reasoning Loop** — iterative investigation
- 💭 **Chain-of-Thought** — visible AI reasoning
- 📊 **Mermaid Diagram Rendering** in chat responses

### Predictive & Proactive
- 🔮 **Predictive Detection** — heuristic trend analysis
- ⏱️ **SLA Countdown** — monthly budget tracking with breach estimation
- 💥 **Blast Radius Estimator** — affected services, users, revenue risk
- 📈 **Corvin Score** — 0–100 service health gauge

### Intelligence Layer
- 🧠 **Incident Memory** — pattern detection from past incidents
- 🌅 **Morning Briefing** — Jarvis-style daily SRE narrative
- 🎯 **Confidence Meter** — High/Medium/Low with reasoning
- 📊 **DORA Metrics** — deployment frequency, MTTR, change failure rate
- 💰 **ROI Dashboard** — hours saved, cost saved, MTTR reduction

### Execution & Approval
- ✅ **Human-in-the-Loop** — Approve/Reject/Acknowledge workflow
- ⚡ **AKS Execution** — restart pods, rollback deployments, scale replicas
- 🔍 **Remediation Preview** — before/after state comparison
- 📝 **Runbook Auto-Update** — LLM suggests new runbook steps

### Delivery Surfaces
- 🌐 **React Dashboard** — full SRE command center (6 pages, 40+ components)
- 💬 **Teams Bot** — Adaptive Cards with inline Approve/Reject
- ⌨️ **CLI REPL** — interactive terminal interface
- 🔌 **REST API** — 43 endpoints with Swagger docs
- 📧 **Email** — PDF reports via Azure Communication Services
- 📁 **SharePoint** — auto-upload RCA docs
- 📖 **ADO Wiki** — auto-publish investigation pages
- 🎫 **Azure Boards** — auto-create work items with routing

### Enterprise Polish
- 🌙 **3AM Mode** — on-call focus mode (hides non-critical UI)
- 🗣️ **Voice TTS** — browser-native speech for briefings
- 🎙️ **Speech Recognition** — voice input for Command Center
- 🌗 **Dark/Light Theme** — full theme toggle
- 🎮 **Alert Simulator** — 4 failure scenarios for demos
- 🗺️ **Service Topology** — React Flow interactive graph with live AKS metrics
- 📄 **PDF Export** — ReportLab-generated RCA reports
- 🎨 **Typewriter Animation** — character-by-character text reveal

---

## BY THE NUMBERS

| Metric | Value |
|---|---|
| **Total Lines of Code** | 33,000+ |
| **Python Backend LOC** | ~20,245 |
| **TypeScript Frontend LOC** | ~12,790 |
| **API Endpoints** | 43 |
| **Automated Tests** | 446 (all passing ✅) |
| **AI Agent Tools** | 16 |
| **Evidence Adapters** | 6 |
| **Database Tables** | 11 |
| **Alembic Migrations** | 16 |
| **External Integrations** | 11 |
| **APIM KQL Templates** | 20+ |
| **Frontend Components** | 40+ |
| **Frontend Pages** | 6 |
| **Config YAML Files** | 16 |
| **Runbooks** | 9 |
| **SSE Event Types** | 5 |
| **Max Tool-Call Rounds** | 6 |
| **Delivery Surfaces** | 4 (Web, Teams, CLI, API) |
| **Alert Simulator Scenarios** | 4 |

---

## IMPACT METRICS (before vs after)

| Metric | Before Corvin | After Corvin | Improvement |
|---|---|---|---|
| **Time to RCA** | 37 minutes | ~30 seconds | **74x faster** |
| **Evidence gathering** | 5 browser tabs, manual | 6 sources, parallel, automated | **100% automated** |
| **Incident documentation** | Manual post-mortem, hours later | Auto-generated, instant | **Blameless + instant** |
| **Knowledge retention** | In people's heads | Incident Memory + Runbooks | **Institutionalized** |
| **3AM experience** | Open laptop, grep logs, guess | "Hey Corvin, what happened?" | **Voice + 3AM Mode** |

---

## SPEAKER NOTES (for the 12 slides)

- **Slide 1 (Title)**: "Corvin — named after Corvinus, the raven king. Wisdom, pattern recognition, observation. That's exactly what this platform does. It's your AI SRE Co-Pilot. And yes, it's live on Azure right now."
- **Slide 2 (Problem)**: "Every SRE knows this drill. 3AM page. You open 5 browser tabs — APIM logs, AKS dashboard, Elastic, Activity logs, runbooks. 37 minutes of manual detective work. And tomorrow? Same incident. Same investigation. Same pain."
- **Slide 3 (Solution)**: "Corvin does this in 30 seconds. An 8-stage pipeline: alert fires, evidence gathered from 6 sources in parallel, AI reasons through the root cause, generates a fix strategy, human approves, Corvin executes on AKS. The AI handles the investigation — you handle the decision."
- **Slide 4 (AI Engine)**: "This isn't a chatbot. It's an agent. 16 live tools the LLM can call — run KQL queries, check AKS health, pull APIM analytics, get container metrics. It reasons through up to 6 rounds, each time deciding what data it needs next. Like a junior SRE that never sleeps and never forgets."
- **Slide 5 (Architecture)**: "Five-tier modular architecture. Triggers at the top, evidence adapters in parallel, the AI brain in the middle, structured outputs, and four delivery surfaces at the bottom. Every layer is independently extensible."
- **Slide 6 (Tech Stack)**: "Python FastAPI backend, React TypeScript frontend, PostgreSQL for persistence, Azure AI Foundry GPT-5.1 for intelligence. 12 backend frameworks, 10 frontend libraries. Production-grade, not a weekend hack."
- **Slide 7 (Numbers)**: "Let the numbers speak. 33,000 lines of code. 446 automated tests — all green. 43 API endpoints. 16 AI tools. 11 integrations. 16 database migrations. This is real engineering."
- **Slide 8 (Dashboard)**: "This is what an SRE sees when they open Corvin. Morning Briefing — Jarvis-style narrative of what happened overnight. DORA metrics. Predictive alerts — issues before they become incidents. Live service topology. ROI dashboard showing time and cost saved."
- **Slide 9 (Command Center)**: "This is our ChatGPT moment. Ask Corvin anything in natural language. It autonomously decides which tools to call, streams its thinking in real time, renders Mermaid diagrams, and presents structured answers. Watch — I type 'What's wrong with fundapis?' and the AI starts reasoning, calling tools, building the picture."
- **Slide 10 (Investigation)**: "Here's the full investigation flow. Alert fires. Evidence streams in from 6 sources. The AI produces an RCA with confidence scoring. Fix strategy with kubectl commands ready to go. Blast radius — who's affected. One click to approve. One click to execute. Post-mortem auto-generated. Runbook auto-updated with what we learned."
- **Slide 11 (Impact)**: "37 minutes down to 30 seconds. That's 74x faster. Evidence gathering? Fully automated. Incident documentation? Instant and blameless. Knowledge? No longer trapped in people's heads — it's in Incident Memory and auto-updated runbooks."
- **Slide 12 (Closing)**: "Investigate smarter. Resolve faster. Sleep better. That's Corvin. The links are right here — try it yourself."

---

## KEY DIFFERENTIATORS (pick 3-4 to weave into your narrative)

1. **Not a chatbot — an agent.** Autonomously calls 16 tools, gathers real evidence, reasons through problems.
2. **Not a prototype — production.** 33,000+ LOC, 446 tests, 16 migrations, live on Azure.
3. **Not one surface — four.** Web, Teams, CLI, API. Meet SREs where they are.
4. **Not reactive — predictive.** Spots issues before they become incidents.
5. **Not a black box — transparent.** Chain-of-thought, confidence scoring, evidence refs, audit trail.
6. **Not just diagnosis — execution.** Human approves, Corvin executes on AKS.
7. **Not one-and-done — learning.** Incident Memory, runbook auto-update, Morning Briefing.

---

## LIVE DEMO LINKS (for judges to try)

- **React Dashboard**: https://mango-hill-0639bd600.7.azurestaticapps.net/
- **API Swagger Docs**: https://corvin-api-akhyb9aaa8hpbxg9.australiaeast-01.azurewebsites.net/docs

---

## LIVE DEMO TIPS (for the presenter)

During slides 8-10, you can briefly flip to a pre-opened browser tab to show the feature live, then return to slides. Have these tabs ready:
1. **Dashboard** — https://mango-hill-0639bd600.7.azurestaticapps.net/ (main dashboard with briefing, DORA, topology)
2. **Command Center** — pre-loaded with a conversation showing tool calls
3. **Investigation Detail** — a completed investigation showing RCA, fix strategy, blast radius
4. **API Docs** — https://corvin-api-akhyb9aaa8hpbxg9.australiaeast-01.azurewebsites.net/docs

---

## IMPORTANT NOTES FOR GEMINI

- The context above is EXHAUSTIVE so you understand the product deeply. Do NOT put all of it into slides.
- Each slide should have max 20-30 words of visible text + one big visual/diagram/number.
- Speaker notes should be conversational bullet prompts, not scripts to read verbatim.
- The "By The Numbers" slide is the fastest crowd-pleaser — make the numbers BIG and bold.
- The "Agentic AI" slide is the intellectual differentiator — this is where judges go "oh, this is different."
- Slides 8-10 (Product Tour) should describe the UI features so the presenter knows what to show. Include placeholder areas for screenshots.

---

*End of prompt. Paste this entire document into Gemini Canvas. It has all the context needed to generate a killer 10-12 slide deck with speaker notes.*

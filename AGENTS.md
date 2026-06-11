# AGENTS.md — Corvin AI Agent Skills

This file is read by any AI agent (Claude, Copilot, Gemini, Cursor, etc.)
when working in this repository. It provides the mental model, rules, and
conventions needed to contribute correctly without breaking things.

**Read this entire file before writing a single line of code.**

---

## What Is This Project?

**Corvin** is an Azure-native SRE Co-Pilot. It monitors Kubernetes applications
running on AKS, queries Azure Log Analytics for evidence, and uses an LLM
(Azure AI Foundry GPT-5.1) to produce structured Root Cause Analysis (RCA)
and fix strategies. An SRE team then approves and executes fixes via Microsoft Teams.

**Corvin now includes a full AI Intelligence Suite** — alert correlation/deduplication,
capacity forecasting, conversational runbook building, and War Games (chaos simulation,
incident replay). All automated actions enforce human-approval gates.

---

## Current Version

**V5.3 "AI INTELLIGENCE SUITE" complete (2026-06-01).** Alert correlation, capacity forecasting, conversational runbook builder, War Games page, War Room banner shipped.  
**V5.4 "AI RUNBOOK MANAGEMENT" complete (2026-06-05).** Full-lifecycle runbook system with DB-backed library, self-updating GitOps loop, predictive alert enrichment, and UI scaffold guide. See [What Changed in V5.4](#what-changed-in-v54-2026-06-05) below.  
**Now building:** Phase 1 — Productization & Genericization. Stripping MetLife/CHAD-specific content and making the platform deployable for any customer through configuration only.

## Active Phase — Productization & Genericization

**Phase:** 1 of 6  
**Goal:** Transform Corvin from a MetLife/CHAD-specific hackathon solution into a reusable product platform.  
**Entry Score:** 28% productized (core engine is generic; assets, config, knowledge base, branding are not).  
**Exit Criteria:** A different customer can deploy and onboard through configuration only — no source-code changes.

**Do NOT work on authentication, RBAC, billing, or multi-tenancy. Those are Phase 3–5.**

Read before starting any Phase 1 work:
- `docs/PRODUCTIZATION_BACKLOG.md` ← 30-item prioritized backlog
- `docs/PRODUCTIZATION_ASSESSMENT.md` ← full audit findings and strategy
- `PROJECT_STATUS.md` ← current phase state and active milestones

**Next actions (in order):**
1. **PB-004** — Remove Azure tenant URL from `.env.example` line 78
2. **PB-001** — Delete `apps/web/public/metlife-logo.svg`
3. **PB-002** — Remove `knowledge/runbooks/chad-*.md` and `fundapis.md`
4. **PB-003** — Rebuild `knowledge/runbooks/catalog.json` (generic keywords only)
5. **PB-006** — Replace MetLife email addresses in test fixtures

---

## What Changed in V5.2 (2026-05-31)

### Font Modernisation
- **Font replaced:** DM Sans → **Plus Jakarta Sans** (Google Fonts, weights 200–800 + italic 400)
- `apps/web/index.html`: updated Google Fonts `<link>` href
- `apps/web/src/index.css`:
  - `--font-display` and `--font-body` now reference `'Plus Jakarta Sans'`
  - `html { font-size }` bumped **14px → 15.5px** (was too small for SaaS readability)
  - Added `letter-spacing: -0.01em` on the html root for tighter modern feel
  - Type scale bumped: `--text-xs: 0.8rem`, `--text-sm: 0.875rem`, `--text-md: 0.9375rem` through `--text-4xl: 2.125rem`

### DB Hygiene — CHAD-Only Demo Seed
- Deleted 5 fake MetLife-style apps from `corvin.db`: Claims Platform, Policy Management, Customer Portal, Data Platform, Infrastructure
- `apps/api/seed_demo.py` completely rewritten — seeds **1 app (CHAD)** with **3 real services** only:
  - `fundapis` (Fund APIs, `chad-fundapis`, status `ok`, routes through APIM)
  - `fundsso` (Fund SSO, `chad-fundsso`, status `ok`, direct SSO via PingFederate)
  - `partnerapis` (Partner APIs, `chad-partnerapis`, status `at_risk`, routes through APIM)
- Idempotency guard: checks `filter_by(name="CHAD")` before seeding
- "TestApp1" and "ChAD AU" (user-created entries) are **never deleted**

### Outbound Connector UX — Universal Variables + Auth + Payload Templates
This is a significant upgrade from the previous "one URL field" design.

**Backend** (`apps/api/routes/applications.py`):
- Added `generic_http` to `_VALID_OUTBOUND_TYPES`
- Added `CONNECTOR_FIELD_SCHEMA` constant documenting per-type endpoint fields

**Frontend types** (`apps/web/src/api/client.ts`):
- New interfaces: `ConnectorVariable`, `ConnectorAuth`, `ConnectorConfig`
- `ConnectorAuth.type` values: `none | bearer | api_key | basic | oauth2`
- `OutboundConnector.config_json` is now typed `ConnectorConfig` (backwards-compat — also accepts legacy `webhook_url`)
- Connector type union now includes `'generic_http'`

**`AddOutboundModal`** (`apps/web/src/pages/ApplicationsPage.tsx`) completely rewritten with 5 sections:
1. **Type + Name** — supports Teams Webhook / ServiceNow / Email / PagerDuty / Generic HTTP
2. **Endpoint** — label/placeholder adapts per type; email shows host+port grid; ServiceNow adds `table` field; Generic HTTP adds method selector (POST/PUT/PATCH/GET)
3. **Authentication** — pill toggles for **None / Bearer Token / API Key / OAuth 2.0 / Basic Auth**
   - OAuth 2.0 exposes: Token URL, Client ID, Client Secret, Scopes (space-separated)
   - API Key exposes: key value + header name (default `X-API-Key`)
   - Basic Auth exposes: username + password
4. **Variables** — add/remove rows of `key → default_value`; default values can reference built-in Corvin vars (`{{rca_summary}}`, `{{service_name}}`, etc.); per-type defaults loaded automatically on type change
5. **Payload Template** — JSON textarea, full templating with `{{key}}` interpolation, "Reset to default" button per type

Module-level constants in `ApplicationsPage.tsx`:
- `CONNECTOR_DEFAULT_ENDPOINTS` — per-type default URL
- `CONNECTOR_DEFAULT_AUTH` — per-type default auth method (e.g. ServiceNow defaults to `oauth2`)
- `CONNECTOR_DEFAULT_VARS` — per-type pre-filled variable rows with sensible default values
- `CONNECTOR_DEFAULT_PAYLOADS` — full JSON template per connector type
- `AUTH_TYPE_OPTS` — auth picker options array

Connector cards in ConnectorsTab now show: auth type badge, variable count, endpoint URL (truncated).

---

## What Changed in V5.3 (2026-06-01)

### AI Intelligence Suite — 4 New Backend Modules

1. **Alert Correlation Engine** (`corvin/strategy/alert_correlation.py`)
   - Groups alerts by temporal proximity, topology affinity, and semantic similarity
   - Produces `CorrelationGroup` objects with root-cause candidates and suppression recommendations
   - Human-approval gate on all suppression actions

2. **Capacity Forecaster** (`corvin/strategy/capacity_forecaster.py`)
   - Linear regression over resource metrics (CPU, memory, disk) to predict exhaustion
   - LLM-generated narrative explaining forecast risk and scaling recommendations
   - Outputs `CapacityForecastReport` with per-resource forecasts + scaling actions
   - Human-approval gate on all scaling recommendations

3. **Conversational Runbook Builder** (`corvin/strategy/runbook_builder.py`)
   - Multi-turn chat sessions that iteratively draft runbooks from incident context
   - Session management (start → messages → draft → approve → save to KB)
   - Replaces one-shot runbook update with interactive refinement loop

4. **War Games / Chaos Simulation** (uses existing `chaos_engine.py` + new UI)
   - Dedicated War Games page aggregating chaos experiments, correlation, and forecast tools
   - Incident Replay tab (placeholder for future replay simulations)

### New API Routes (`apps/api/routes/ai_features.py`)

All under `/ai` prefix:
- `POST /ai/correlate-alerts` — run alert correlation engine
- `POST /ai/correlate-alerts/approve` — approve/reject suppression action
- `POST /ai/capacity-forecast` — run capacity forecast for a service
- `POST /ai/capacity-forecast/approve` — approve scaling recommendation
- `POST /ai/runbook-session/start` — begin runbook builder session
- `POST /ai/runbook-session/message` — send chat message in session
- `POST /ai/runbook-session/approve` — approve draft runbook
- `POST /ai/runbook-session/save` — persist approved runbook to knowledge base
- `GET /ai/war-games/scenarios` — list available war game scenarios

### New Frontend Components

- **`AlertCorrelationPanel.tsx`** — "Run Correlation" button, grouped alert display, approve/reject suppression
- **`CapacityForecastPanel.tsx`** — service input, risk badges, resource forecast cards, scaling approve
- **`RunbookBuilderChat.tsx`** — chat interface with session lifecycle (idle → drafting → approved → saved)
- **`WarRoomBanner.tsx`** — animated pulsing gradient banner for active incidents (pending approval)
- **`WarGamesPage.tsx`** — 4-tab page (Chaos Experiments, Alert Correlation, Capacity Forecast, Incident Replay)

### Frontend Wiring

- `NavBar.tsx`: Added "War Games" entry with ⚔ icon
- `App.tsx`: Added `/war-games` route
- `InvestigationDetailPage.tsx`:
  - War Room Banner displayed when `approval_status === 'pending'`
  - RunbookBuilderChat displayed post-execution (alongside existing RunbookUpdatePrompt)
- `client.ts`: 12 new TypeScript interfaces + 8 API fetch functions

### Other Backend Additions

- `corvin/connectors/git_repo.py` — Git repository connector for code-level context
- `corvin/toolsets/code_analysis.py` — Static code analysis toolset
- `corvin/investigation/code_enrichment.py` — Code-level enrichment during investigations
- `corvin/delivery/prediction_notification.py` — Delivery channel for predictive alert notifications
- `corvin/triggers/prediction_penalty.py` — Penalty scoring for predictive detection accuracy
- `corvin/triggers/validation_automation.py` — Policy-driven validation automation triggers
- Alembic migrations 0019–0021 (validation policies, predictive penalties, git config)

---

## What Changed in V5.4 (2026-06-05)

### AI Runbook Management — Full Lifecycle Feature

**Philosophy:** Runbooks are not documentation — they are live operational intelligence that Corvin injects into every investigation, automatically updates after every resolved incident, and surfaces proactively during predictive alerts. The V5.4 feature makes this lifecycle visible, self-improving, and engineer-friendly.

---

### 1. DB-Backed Runbook Library (seeded with 6 production runbooks)

Six runbooks seeded directly into `RunbookRow` for the CHAD application, covering all three services and two cross-service failure patterns:

| Title | Service | Key Keywords |
|---|---|---|
| Fund APIs — 503 Error Rate Spike | `fundapis` | 503, error_rate, backend_error, 5xx |
| Fund APIs — Heap Memory Pressure & OOM Recovery | `fundapis` | OOMKilled, memory, heap, oom |
| Fund SSO — Identity Cache Poisoning & 401 Spike | `Fundsso` | 401, jwt, sso, token, unauthorized |
| Partner APIs — HPA Controller Failure & Scale Lag | `partnerapis` | hpa, scale, autoscaler, ScalingDisabled |
| AKS — Pod CrashLoop & Eviction Response | *(cross-service)* | CrashLoopBackOff, eviction, ImagePullBackOff |
| APIM — Gateway Degradation & Backend Failover | *(cross-service)* | apim, gateway, 502, throttling, 429 |

Each runbook contains: severity header, quick assessment commands, diagnosis decision tree, step-by-step recovery procedure, escalation criteria, and post-incident checklist.

**Seeding is now part of `seed_demo.py`** — `RunbookRow` import added and idempotent `runbooks` block inserted before `db.commit()`.

---

### 2. Critical Bug Fix — Prompt Builder Was Ignoring DB Runbooks

**Before V5.4:** `prompt_builder.py` called both knowledge loader methods without `service_name`:
```python
# BUG (pre-V5.4)
self._loader.load_site_knowledge()                    # service_name=None → always disk fallback
self._loader.load_matching_runbooks(alert_text)       # service_name=None → DB tier skipped entirely
```
This meant **all DB-backed runbooks and site knowledge were silently ignored** for every investigation.

**Fix in V5.4** (`corvin/investigation/prompt_builder.py`, lines 90–96):
```python
# FIXED
self._loader.load_site_knowledge(service_name=request.service_name)
self._loader.load_matching_runbooks(alert_text, service_name=request.service_name)
```
DB runbooks are now correctly injected into every investigation prompt for matching services.

---

### 3. Predictive Alert → Runbook Enrichment

**Before V5.4:** Predictive alerts had no runbook connection. Engineers saw a predicted failure with no operational guidance.

**V5.4 adds:**
- New field `suggested_runbook_title: str | None` on `PredictiveAlert` (Pydantic model)
- After the alert deduplication/scoring loop in `PredictiveMonitor.refresh_alerts()`, each alert is enriched with the title of its first matching runbook:
  ```python
  # In corvin/triggers/predictive.py
  search_text = f"{alert.alert_type} {alert.title} {alert.summary}"
  matching = _loader.load_matching_runbooks(search_text, service_name=alert.service_name)
  if matching:
      alert.suggested_runbook_title = matching[0].split("\n")[0].lstrip("# ").strip()
  ```
- Non-fatal: wrapped in `try/except`, logged at DEBUG level

Engineers can now see *"Suggested runbook: Fund APIs — Heap Memory Pressure & OOM Recovery"* directly on the Predictive Analytics page, linked to the full procedure before an incident even fires.

---

### 4. Knowledge Scaffold Guide (UI)

Added to the **Knowledge Base tab** in the Applications page (`ApplicationsPage.tsx`):

- **`⚡ Scaffold with Copilot` button** — secondary style, placed next to "+ Add Entry"
- **`KnowledgeScaffoldModal`** component with 4-step guide:
  1. Open AI assistant (GitHub Copilot, Cursor, Claude Code, Windsurf)
  2. Open in project workspace
  3. Paste & run the scaffold prompt (full copyable code block with "⧉ Copy / ✓ Copied" state)
  4. Paste output into Add Entry
- The embedded **Corvin Architecture Scaffold Prompt** instructs the AI to reverse-engineer the codebase and output structured markdown sections: Service Inventory, Service Dependencies, API & APIM Routes, AKS Infrastructure, Azure Resources, Known Failure Modes, SLO Candidates
- Modal closes cleanly and can hand off directly to the Add Entry form

---

### 5. Version Table Updated

| Version | Status | Gate |
|---|---|---|
| V5.3 | ✅ Complete | AI Intelligence Suite shipped |
| V5.4 | ✅ Complete | AI Runbook Management: DB library seeded, prompt builder bug fixed, predictive enrichment wired, scaffold UI added |

---

## AI Runbook Management — Architecture Reference

This section documents the complete runbook lifecycle for any agent contributing to this feature area.

### The Self-Improving Loop

```
[1] Alert fires
      ↓
[2] InvestigationEngine.run()
      → PromptBuilder.build(request)
         → KnowledgeLoader.load_matching_runbooks(alert_text, service_name)
            ↓
         DB tier: query RunbookRow by service_name + keyword match
         Disk tier: match against catalog.json (fallback if DB empty)
            ↓
         Runbook injected as "## Relevant Runbook" in system prompt
      → RCAGenerator.generate(request, evidence, system_prompt)
         LLM sees runbook as primary investigation guide
      ↓
[3] Investigation result: root cause + fix strategy
      ↓
[4] Human approval gate (ApprovalStatus.approved required)
      ↓
[5] ExecutionService executes fix actions
      ↓
[6] RunbookUpdatePrompt shown to engineer (post-execution)
      → POST /investigations/{id}/update-runbook
         → LLM generates markdown step from RCA + executed actions
         → KnowledgeLoader.append_runbook_step(service_name, step_md)
            → Writes to knowledge/runbooks/<service_name>.md (disk)
            → Updates catalog.json via _ensure_catalog_entry()
         → KnowledgeLoader.append_learning(request_id, step_md)
      ↓
[7] Next incident for same service — richer runbook injected
    Corvin compounds its own intelligence with every incident resolved
```

### Two-Tier Knowledge Loading

| Tier | Source | Priority | Trigger |
|---|---|---|---|
| 1 (DB) | `RunbookRow` table — managed via Applications UI | Always first | service_name match or keyword overlap in alert text |
| 2 (Disk) | `knowledge/runbooks/catalog.json` + `.md` files | Fallback only | DB returns empty |

**DB-tier matching logic** (`KnowledgeLoader._load_db_runbooks()`):
- Resolves `service_name` → `application_id` via `ApplicationServiceRow` (also checks `k8s_app_label`)
- Service-specific runbooks (`row.service_name == service_name`): **always included**
- Cross-service runbooks (`row.service_name IS NULL`): **included if any keyword appears in normalised alert text**
- Returns list of markdown strings, up to `runbook_max_chars` (default 3000) per entry

**Disk-tier matching logic** (`KnowledgeLoader.load_matching_runbooks()`):
- Reads `knowledge/runbooks/catalog.json`
- Matches via `match_patterns`, `keywords`, or `keyword` fields (all normalized to lowercase)
- Resolves file paths relative to `knowledge_root` or project root

### Runbook Write-Back (Post-Incident)

Two write-back paths produce runbook content automatically:

**Path A — One-Shot Auto-Update** (`POST /investigations/{id}/update-runbook`):
- Gate: `approval_status == EXECUTED`
- LLM (GPT-4.1-mini) generates a structured markdown step from RCA root_cause + fix_strategy.actions
- Appends to `knowledge/runbooks/<service_name>.md` on disk
- Registers in `catalog.json` automatically via `_ensure_catalog_entry()`
- Also writes to `knowledge/learnings/<request_id>.md`

**Path B — Conversational Builder** (`RunbookBuilder` + `/ai/runbook-session/*`):
- Multi-turn GPT-5.1 chat session initialised from investigation context
- Engineer iterates: draft → refine → approve → save
- `POST /ai/runbook-session/save` calls `KnowledgeLoader.append_runbook_step()` — same write path as Path A
- Session persisted in `RunbookSessionRow` (messages, draft versions, approval state)

### DB Schema — Runbook Tables

```
RunbookRow (table: runbooks)
  id              UUID PK
  application_id  FK → applications.id  (scoped per application)
  service_name    TEXT nullable         (NULL = cross-service / keyword-only match)
  title           TEXT                  (display name + first line of content)
  keywords        JSONB []              (array of strings for alert-text matching)
  content         TEXT                  (full markdown — injected verbatim into prompt)
  is_active       BOOL default True
  display_order   INT  default 0
  created_at / updated_at

RunbookSessionRow (table: runbook_sessions)
  id                      UUID PK
  request_id              FK → investigation
  service_name / environment
  status                  TEXT  "drafting" | "approved" | "saved"
  messages_json           JSONB []  (full conversation history)
  current_draft_content   TEXT nullable
  current_draft_version   INT nullable
  approved_by             TEXT nullable
  created_at / updated_at
```

### API Surface — Runbook Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/applications/{app_id}/runbooks` | List all runbooks for an application |
| `POST` | `/applications/{app_id}/runbooks` | Create a new runbook entry |
| `PUT` | `/applications/{app_id}/runbooks/{id}` | Update a runbook entry |
| `DELETE` | `/applications/{app_id}/runbooks/{id}` | Delete a runbook entry |
| `POST` | `/investigations/{id}/update-runbook` | Auto-generate runbook step post-execution (Path A) |
| `POST` | `/ai/runbook-session/start` | Begin conversational runbook builder session (Path B) |
| `POST` | `/ai/runbook-session/message` | Send chat message (non-streaming) |
| `POST` | `/ai/runbook-session/chat/stream` | Send chat message (streaming SSE) |
| `POST` | `/ai/runbook-session/approve` | Mark draft approved |
| `POST` | `/ai/runbook-session/save` | Persist approved draft to knowledge base |

### Corvin Command Center — `get_runbook` Tool

The autonomous agent in the Command Center has a `get_runbook` tool that calls `KnowledgeLoader.load_matching_runbooks()` directly. This means:
- Operators can ask Corvin "what's the runbook for a 503 on fundapis?" and get the full procedure in the chat
- The tool now correctly uses DB-backed runbooks (post V5.4 bug fix)
- DB runbooks take precedence; disk runbooks are the fallback

### Predictive Alerts → Runbook Surface

`PredictiveAlert.suggested_runbook_title` (added V5.4) is populated during `PredictiveMonitor.refresh_alerts()`. The Predictive Analytics page should surface this field alongside each alert card as a "Suggested Runbook" link/badge, giving engineers the operational playbook before the incident actually fires.

Frontend wiring location: `apps/web/src/pages/PredictiveAnalyticsPage.tsx` — `HeroAlertSection` and alert card components.

---

## Runbook Matching (How It Works)

Runbook matching now operates across **two tiers** — DB-first, disk fallback. Both must be maintained:

**Tier 1 — DB RunbookRow** (primary — managed via Applications UI)
- Add via: Applications → [App] → Runbook Library → + Add Runbook
- No file system changes required
- Instantly active (no server restart)
- Service-specific entries always match for their service
- Cross-service entries match via keyword overlap with the alert text
- Seeded for demo via `seed_demo.py` `runbooks:` section

**Tier 2 — `catalog.json`** (disk fallback — required if DB is empty)
`knowledge/runbooks/catalog.json` is the index Corvin reads for disk-based runbooks:

```json
{
  "keyword": "aks-crashloop",
  "title": "AKS Pod CrashLoopBackOff Investigation",
  "file": "runbooks/aks-crashloop.md",
  "match_patterns": ["crashloop", "crashloopbackoff", "pod", "oomkilled", "restart", "crash"]
}
```

**YAML frontmatter** (disk runbooks only — secondary, future RAG use):
```yaml
---
keywords: [oom, heap, memory, java, gc]
---
```

**To add a new disk runbook — TWO steps required:**
1. Create the `.md` file in `knowledge/runbooks/` with `keywords:` frontmatter.
2. Add an entry to `knowledge/runbooks/catalog.json` with the correct `match_patterns`.

**If you skip step 2, the disk runbook will NEVER be injected into the LLM prompt.**
DB runbooks have no such requirement — they are registered and matched automatically.

---

## Strict Version Gate (DO NOT SKIP)

Never build a feature from a future version while the current version is incomplete.

| Version | Status | Gate |
| :--- | :--- | :--- |
| V1 | ✅ Complete | 155+ tests passing |
| V1.5 | ✅ Complete | All real Azure adapters connected and validated |
| V2 | ✅ Complete | 320/320 tests passing |
| V2.5 | ✅ Complete | 318/318 tests passing |
| V3 | ✅ Complete | 363/363 tests passing, full UI + post-mortem |
| V3+ | ✅ Complete | 381/381 tests passing (ThinkingPanel, Incident Memory, Morning Briefing, Live Evidence, Refactor) |
| V3.5 | ✅ Complete | Alert Simulator, Teams Adaptive Cards, Blast Radius Estimator, Corvin Score Gauge |
| V3.7 | ✅ Complete | Predictive Detections, SLA Countdown, Cross-Service Topology, Remediation Preview — all verified live in browser |
| V3.9 | ✅ Complete | ROI Dashboard, Voice TTS, 3AM Mode, Runbook Auto-Update, War Room — 16/16 tests passing |
| V4 | ⏭️ Skipped | Semantic Search / Vector RAG (deferred — requires pgvector on Azure Postgres) |
| V4.5 | ✅ Complete | DB-driven AKS onboarding — remove hardcoded topology, k8s_app_label, guided AKS connector form |
| V5.0 | ✅ Complete | Agentic AI P0: F1 AutonomousAgent, F4 CausalChain, F6 NL-to-KQL, F7 CommsDrafts |
| V5.1 | ✅ Complete | Agentic AI P1: F9 Multi-Agent, F10 Chaos Engine, F11 IDE Integration, F12 Voice Incident |
| V5.2 | ✅ Complete | UX Maturity: Plus Jakarta Sans font, CHAD-only seed, outbound connector builder (variables, payload templates, OAuth 2.0) |
| V5.3 | ✅ Complete | AI Intelligence Suite: Alert Correlation, Capacity Forecaster, Conversational Runbook Builder, War Games page, War Room Banner |
| V5.4 | ✅ Complete | AI Runbook Management: 6 production runbooks seeded, prompt builder bug fixed (service_name now passed), predictive alert runbook enrichment, scaffold UI guide |

---

## How to Start the Dev Server

```powershell
# Activate venv first — always
C:\venv\corvin\Scripts\Activate.ps1          # shared venv
# or, if using a local project venv:
# .\.venv\Scripts\Activate.ps1

# Install / sync dependencies
pip install -e ".[dev]"

# Start FastAPI (port 8000)
uvicorn apps.api.main:app --reload --port 8000

# Start the interactive CLI
python -m apps.cli.main
```

API docs available at: `http://localhost:8000/docs`

---

## How to Run Tests

```powershell
# Activate venv first
C:\venv\corvin\Scripts\Activate.ps1

pytest tests/ -v                         # Run all tests (437+ at V5.4)
pytest tests/slices/ -v                  # Run slice tests only
pytest -k "test_approval" -v             # Run a specific test by name
pytest tests/ -v --tb=short              # Short traceback on failures
```

**All existing tests must remain GREEN after every change.**
If a change breaks an existing test, fix the test OR fix the code — never skip or delete the test.

---

## How to Run Alembic Migrations

```powershell
# Apply all pending migrations to the database (currently 0001 → 0016)
alembic upgrade head

# Create a new migration (after modifying SQLAlchemy models)
alembic revision --autogenerate -m "add approval_status column"

# Check current migration state
alembic current
```

**Rule:** Any change to `corvin/core/contracts.py` that affects persisted fields
requires a matching Alembic migration. Do not skip this step.

---

## Project Structure (Agent Mental Map)

```
corvin/
  core/           # Contracts (Pydantic models), config loader — touch carefully
  evidence/       # Adapters: log_analytics, aks, container_logs, elastic, azure_activity
  enrich/         # EnrichmentService — orchestrates all adapters
  strategy/       # RCAGenerator, FixStrategyGenerator, SystemPromptBuilder
                  #   + causal_chain.py — CausalChainGenerator (DAG from RCA)
                  #   + comms_draft.py — CommsDraftGenerator (audience-targeted comms)
                  #   + nl_to_kql.py — NLToKQLService (natural language → KQL w/ guardrails)
                  #   + autonomous_agent.py — AutonomousAgent (16-tool function-calling loop)
                  #   + multi_agent.py — MultiAgentOrchestrator (SelectorGroupChat pattern)
                  #   + chaos_engine.py — ChaosExperimentGenerator (post-RCA resilience tests)
                  #   + ide_integration.py — IDEIntegrationService (VS Code context + deploy safety)
                  #   + voice_incident.py — VoiceIncidentService (Azure Speech STT → structured report)
                  #   + alert_correlation.py — AlertCorrelationEngine (temporal/topology/similarity grouping)
                  #   + capacity_forecaster.py — CapacityForecaster (linear regression + LLM narrative)
                  #   + runbook_builder.py — RunbookBuilder (multi-turn conversational sessions)
  storage/        # DB session (db.py), SQLAlchemy models (models.py)
  execution/      # ExecutionService, remediation preview — requires ApprovalStatus.approved
  connectors/     # Pluggable data-source connectors: azure_monitor, elastic, byoa, crypto, registry, git_repo
  investigation/  # Investigation engine + code_enrichment.py (code-level context)
  delivery/       # Delivery channels: Teams, webhooks, prediction_notification.py
  triggers/       # Alert triggers: predictive.py, prediction_penalty.py, validation_automation.py
  slo/            # SLO snapshot computation (snapshot.py)
  validations/    # Validation runner (runner.py)
  toolsets/       # Agent tool definitions: code_analysis.py (static analysis toolset)
  cli/            # Config migration helpers (migrate_config.py)

apps/
  api/            # FastAPI entry (main.py) + routes/: applications, slo, validations, corvin_agent, ai_features, …
  cli/            # Interactive REPL CLI (main.py)
  teams/          # Teams bot (bot.py, router.py, manifest/)
  web/            # React 18 + Vite + TypeScript frontend
                  #   pages: DashboardPage, InvestigationsPage, InvestigationDetailPage,
                  #          ApplicationsPage, SloMonitoringPage, ValidationsPage,
                  #          PredictiveAnalyticsPage, CorvinCommandPage, WarGamesPage
                  #   components: AlertCorrelationPanel, CapacityForecastPanel,
                  #              RunbookBuilderChat, WarRoomBanner, NavBar, BlastRadiusCard, …
                  #   public/corvin-logo.svg — Corvin product logo (served at /corvin-logo.svg)

alembic/          # Alembic migration scripts (0001 → 0024+)
config/           # YAML config per integration and environment
knowledge/
  site.md         # Real infra facts injected into every LLM prompt — keep accurate
  runbooks/       # Markdown files with keywords: frontmatter, matched to alerts
tests/
  slices/         # One test file per slice
  adapters/       # Adapter-specific unit tests
  contracts/      # Contract/schema validation tests
  orchestration/  # End-to-end orchestration tests
```

---

## How Tests Are Written (Pattern — Follow This Exactly)

Tests use **Fake adapter classes** (not `unittest.mock.patch`) for unit tests.
Look at `tests/slices/test_slice2_enrichment_service.py` as the canonical example.

```python
# Pattern: subclass the real adapter and override only what you need
class FakeLogAnalytics(LogAnalyticsAdapter):
    def get_apim_logs(self, service_name: str, ...) -> list[dict]:
        return [{"apim_event": "timeout", "service": service_name}]

# Pattern: use a helper to build test requests
def _make_request() -> InvestigationRequest:
    return InvestigationRequest(
        trigger_source=TriggerSource.MANUAL_CLI,
        service_name="order-service",
        environment="dev",
        description="test investigation",
    )
```

**Unit tests:** Use Fake adapters. No real Azure calls. No `.env` needed.  
**Integration tests:** May hit real Azure endpoints. Require `.env` to be populated.  
**Never delete or disable an existing test.** If it fails after your change, fix it.

---

## Key Conventions (Follow These Exactly)

### 1. Adapters are always resilient
Every adapter method must return an empty list/dict on failure — never raise.
Use `logger.warning(...)` and `return []`. The `EnrichmentService` handles
partial evidence gracefully.

### 2. LLM output is always json_object mode
Never use `json_schema` strict mode with the Azure OpenAI endpoint.
Always instruct the model to return JSON matching the target Pydantic schema
in the system prompt text itself (not via the API `response_format` schema field).

### 3. All fix actions require human approval (V2 onwards)
No `ExecutionService` method may be called without an `ApprovalStatus.approved`
state in Postgres. The gate is enforced at the API route level, not inside the service.

### 4. Environment variables use CORVIN_ prefix for DB
- `CORVIN_DB_HOST`, `CORVIN_DB_USER`, `CORVIN_DB_PASSWORD`, `CORVIN_DB_NAME`
- All other vars follow their service's naming (e.g. `AZURE_CLIENT_ID`, `ELASTIC_HOST`)
- See `.env.example` for the complete list — do NOT invent new variable names.

### 5. Config files use ${VAR_NAME} expansion
All `config/integrations/*.yaml` files use `${ENV_VAR}` placeholders.
The `_expand()` helper in each adapter resolves them at runtime via `os.environ`.

### 6. Dynamic Context Windows
`InvestigationRequest.lookback_minutes` controls the evidence look-back window:
- Manual triggers (CLI/Teams/API): default `60` minutes
- Automated Azure Monitor alerts: extracted from `firedDateTime`, capped at `15` minutes
- Per-application/environment overrides stored in `ApplicationEnvironmentRow.lookback_minutes`
- Do not hardcode `60` in adapter calls — always use `request.lookback_minutes`.

---

## What NOT to Do

- ❌ Do not add Elastic as a hard dependency — it is optional and org-SSO-blocked.
- ❌ Do not call `ExecutionService` without checking `ApprovalStatus.approved`.
- ❌ Do not modify `corvin/core/contracts.py` without a matching Alembic migration.
- ❌ Do not use `json_schema` strict mode with LiteLLM + Azure OpenAI.
- ❌ Do not mock adapters using `unittest.mock.patch` — use Fake subclasses instead.
- ❌ Do not invent new environment variable names — always check `.env.example` first.
- ❌ Do not add new env variable names without updating `.env.example` and `setup/04_env_file.md`.

**Phase 1 — Productization-specific rules:**
- ❌ Do not add any MetLife, CHAD, fundapis, fundsso, or partnerapis references to any file.
- ❌ Do not hardcode GBP, en-GB, or en-GB-RyanNeural — use the configuration resolution hierarchy.
- ❌ Do not write business metrics (users/pod, revenue/user, SLA targets) as hardcoded constants — they belong in ApplicationEnvironmentRow or SloConfigRow.
- ❌ Do not commit binary assets (logos, fonts, images) to the repository root or public/ without a runtime loading mechanism.
- ❌ Do not add customer-specific runbooks to knowledge/runbooks/ — they belong in the database (RunbookRow) scoped by application_id.
- ❌ Do not start authentication, RBAC, multi-tenancy, or billing work — those are Phase 3–5.
- ❌ Do not use MetLife employee email addresses in test fixtures — use sre@example.com.

---

## Runbook Matching (How It Works)

Runbook matching uses **two mechanisms that MUST both be updated** when adding a new runbook:

**Mechanism 1 — `catalog.json`** (primary matcher used by `SystemPromptBuilder`)
`knowledge/runbooks/catalog.json` is the index Corvin actually reads at runtime.
When adding a new runbook, you MUST add an entry here:

```json
{
  "keyword": "apim-5xx",
  "title": "APIM 5xx Spike Investigation",
  "file": "runbooks/apim-5xx.md",
  "match_patterns": ["apim", "5xx", "gateway", "apimanagement", "api management"]
}
```

**Mechanism 2 — YAML frontmatter** (secondary, for future RAG use)
Each `.md` file in `knowledge/runbooks/` should also start with:

```yaml
---
keywords: [oom, heap, memory, java, gc]
---
```

**To add a new runbook — TWO steps required:**
1. Create the `.md` file in `knowledge/runbooks/` with `keywords:` frontmatter.
2. Add an entry to `knowledge/runbooks/catalog.json` with the correct `match_patterns`.

**If you skip step 2, the runbook will NEVER be injected into the LLM prompt.**

---

## Phase Sequence & Current Focus

All V1–V5.4 hackathon features are complete. The platform is now on the productization and enterprise hardening track.

| Phase | Name | Status |
|-------|------|--------|
| Phase 0 | Knowledge & Governance | Complete |
| **Phase 1** | **Productization & Genericization** | **Active** |
| Phase 2 | Architecture Modernization | Planned |
| Phase 3 | Enterprise Foundation | Planned |
| Phase 4 | Multi-Tenant Foundation | Planned |
| Phase 5 | SaaS Scale | Planned |
| Phase 6 | Product Expansion | Planned |

**Before writing any code:**
1. Read `PROJECT_STATUS.md` — current phase, active milestones, known blockers
2. Read `docs/PRODUCTIZATION_BACKLOG.md` — prioritized Phase 1 work items
3. Read `docs/TECH_DEBT.md` — know what debt exists before adding to it
4. Read `docs/ROADMAP.md` — full phase sequence

**Phase 1 focus areas (Sprint 1–3 complete):**
- ✅ Brand & asset genericization — MetLife logo removed; `GET /config/branding` API; Corvin logo SVG
- ✅ Knowledge base genericization — CHAD runbooks relocated; generic catalog (apim-5xx, aks-crashloop)
- ✅ Demo data genericization — Acme Retail topology in seed_data.yaml and test fixtures
- ✅ Configuration externalization — currency, locale, voice, SLA targets, blast radius (per ApplicationEnvironmentRow)
- ✅ Connector onboarding hardening — connection test (V5.4), evidence preview, toolset profiles
- ✅ Prompt registry — 11 prompts migrated to `config/prompts/*.v1.yaml`; `PromptRegistry` class in `corvin/core/prompt_registry.py`
- ✅ Developer experience — `.pre-commit-config.yaml`; startup env var validation; full-stack docker-compose
- ✅ Documentation genericization — AGENTS.md, catalog examples updated to generic entries

**For context on what CHAD is:** CHAD was the original customer development application (MetLife Australia digital channels platform). All CHAD-specific content is being removed from the product in Phase 1. The demo application is now "Acme Retail Platform". See `docs/DEMO_SETUP.md` (to be created in Phase 1).

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
**Now building:** Further refinement / evaluation / next feature iteration.

Read the active version scope BEFORE writing any code:
- `docs/copilot-context/versions/hackathon-roadmap.md` ← historical reference

## Enterprise Refinement Track

The active productization work now lives under:
- `docs/copilot-context/versions/enterprise-refinement/README.md`
- `docs/copilot-context/versions/enterprise-refinement/plan.md`
- `docs/copilot-context/versions/enterprise-refinement/ev1_connector_identity/`

Current slice:
- EV1 — Connector Onboarding And Identity Model

What EV1 decides:
- where connector config lives
- how credentials are resolved at runtime
- which identity model is default in Azure
- how RBAC should be shaped around the connector model
- how onboarding is exposed through the admin surface

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

pytest tests/ -v                         # Run all 155+ tests
pytest tests/slices/ -v                  # Run slice tests only
pytest -k "test_approval" -v             # Run a specific test by name
pytest tests/ -v --tb=short              # Short traceback on failures
```

**All 155+ existing tests must remain GREEN after every change.**
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
                  #   public/metlife-logo.svg — MetLife wordmark (served at /metlife-logo.svg)

alembic/          # Alembic migration scripts (0001 → 0021)
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

### 6. Dynamic Context Windows (To be implemented in V2 Slice 1)
`InvestigationRequest` does NOT yet have a `lookback_minutes` field.  
This field must be added as part of V2 Slice 1.  
Once added, the rule is:
- Manual triggers (CLI/Teams/API): default `60` minutes
- Automated Azure Monitor alerts: extract `firedDateTime`, compute delta, cap at `15` minutes
- Never hardcode `60` in adapter calls after Slice 1 is merged.

---

## What NOT to Do

- ❌ Do not add Elastic as a hard dependency — it is optional and org-SSO-blocked.
- ❌ Do not call `ExecutionService` without checking `ApprovalStatus.approved`.
- ❌ Do not modify `corvin/core/contracts.py` without a matching Alembic migration.
- ❌ Do not use `json_schema` strict mode with LiteLLM + Azure OpenAI.
- ❌ Do not start V2.5 features (memory, briefings, confidence meter) until V2 exit criteria are met.
- ❌ Do not mock adapters using `unittest.mock.patch` — use Fake subclasses instead.
- ❌ Do not invent new environment variable names — always check `.env.example` first.
- ❌ Do not add new env variable names without updating `.env.example` and `setup/04_env_file.md`.

---

## Runbook Matching (How It Works)

Runbook matching uses **two mechanisms that MUST both be updated** when adding a new runbook:

**Mechanism 1 — `catalog.json`** (primary matcher used by `SystemPromptBuilder`)
`knowledge/runbooks/catalog.json` is the index Corvin actually reads at runtime.
When adding a new runbook, you MUST add an entry here:

```json
{
  "keyword": "chad-known-errors",
  "title": "CHAD Known Application Errors",
  "file": "runbooks/chad-known-errors.md",
  "match_patterns": ["exception", "error", "stacktrace", "hikari", "cosmos"]
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

## V2 Starting Point — Slice 1: Approval State Model

**Files to create/modify:**

1. `corvin/core/contracts.py`
   - Add `ApprovalStatus` enum: `pending | approved | rejected | executed`
   - Add `lookback_minutes: int = 60` field to `InvestigationRequest`
   - Add `approval_status: ApprovalStatus` field to `InvestigationResult`

2. `corvin/storage/models.py` (SQLAlchemy)
   - Add `approval_status` column (String, default `"pending"`)

3. `alembic/versions/` — new revision
   - `alembic revision --autogenerate -m "add approval_status"`
   - Verify with `alembic upgrade head`

4. `tests/slices/test_slice_v2_s1_approval_state.py`
   - Test that `ApprovalStatus` enum has all 4 values
   - Test that `InvestigationRequest` accepts `lookback_minutes`
   - Test that `InvestigationResult` persists and retrieves `approval_status` correctly

**Do not move to Slice 2 until Slice 1 tests are green and `alembic upgrade head` succeeds.**

---

## V2 Required Environment Variables (Teams Bot — Slices 3-5)

When building Teams bot functionality, these env vars are needed.
Add them to `.env.example` when creating the Teams bot slice:

```env
# Teams Bot (V2 Slice 5)
TEAMS_APP_ID=<Azure Bot Framework App ID>
TEAMS_APP_PASSWORD=<Azure Bot Framework App Password>
TEAMS_WEBHOOK_URL=<already in .env.example — outbound webhook>
```

# AGENTS.md — Corvin AI Agent Skills

This file is read by any AI agent (Claude, Copilot, Gemini, Cursor, etc.)
when working in this repository. It provides the mental model, rules, and
conventions needed to contribute correctly without breaking things.

**Read this entire file before writing a single line of code.**

---

## What Is This Project?

**Corvin** is an Azure-native SRE Co-Pilot. It monitors Kubernetes applications
running on AKS, queries Azure Log Analytics for evidence, and uses an LLM
(Azure AI Foundry GPT-4.1) to produce structured Root Cause Analysis (RCA)
and fix strategies. An SRE team then approves and executes fixes via Microsoft Teams.

---

## Current Version

**V3.9 complete. All enterprise-polish features verified (2026-05-13).**  
**Now building: V4** — Semantic Search / Vector RAG using pgvector on Azure Postgres.

Read the active version scope BEFORE writing any code:
- `docs/copilot-context/versions/hackathon-roadmap.md` ← **primary reference for V3.9 → V4**

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
| V3.95 | ✅ Complete | Ask Corvin Copilot Chat, GitOps PR UI — Frontend fully implemented |
| V4 | ✅ Complete | P1/P2/P3 Classification, Progressive Disclosure UI |
| V4.5 (Hackathon) | 🔒 Locked | **Killer Features:** AI Chaos Monkey (Auto-inject & heal), Root Cause Debate Mode (Multi-hypothesis) |
| V4.6 (Hackathon) | 🔒 Locked | **Killer Features:** Time-Travel Incident Replay (Visual slider to rewind system state) |
| V4.7 (Hackathon) | 🔒 Locked | **Killer Features:** "Git Blame" Code-Level Root Cause (Correlate infra alerts to exact GitHub commits) |
| V4.8 (Hackathon) | 🔒 Locked | **Killer Features:** Cost-Aware Remediation (FinOps - attaching live price tags to fix strategies) |
| V5 | 🔒 Locked | Semantic Search / Vector RAG (requires pgvector on Azure Postgres) |

---

## How to Start the Dev Server

```powershell
# Activate venv first — always
.\.venv\Scripts\Activate.ps1

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
.\.venv\Scripts\Activate.ps1

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
# Apply all pending migrations to the database
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

Only directories that CURRENTLY EXIST are listed here.
Do not assume V2 directories exist until they are explicitly created.

```
corvin/
  core/           # Contracts (Pydantic models), config loader — touch carefully
  evidence/       # Adapters: log_analytics, aks, container_logs, elastic, azure_activity
  enrich/         # EnrichmentService — orchestrates all adapters
  strategy/       # RCAGenerator, FixStrategyGenerator, SystemPromptBuilder
  storage/        # DB session (db.py), SQLAlchemy models (models.py)

apps/
  api/            # FastAPI routes (main.py, routers/)
  cli/            # Interactive REPL CLI (main.py)
  web/            # React frontend (Vite + TypeScript)

alembic/          # Alembic migration scripts
config/           # YAML config per integration and environment
knowledge/
  site.md         # Real infra facts injected into every LLM prompt — keep accurate
  runbooks/       # Markdown files with keywords: frontmatter, matched to alerts
tests/
  slices/         # One test file per V1 slice (test_slice1 through test_slice10)
  adapters/       # Adapter-specific unit tests
  contracts/      # Contract/schema validation tests
  orchestration/  # End-to-end orchestration tests
```

**V2 directories not yet created:**
- `corvin/execution/` — will be created in V2 Slice 4
- `apps/teams/` — will be created in V2 Slice 5

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
- ❌ Do not assume `corvin/execution/` or `apps/teams/` exist — they are V2 directories to be created.

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

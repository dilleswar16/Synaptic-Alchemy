# Corvin — AI-Native Incident Investigation Platform

Corvin is an Azure-native SRE co-pilot that automates the investigation, root-cause analysis, and remediation of cloud incidents. When an alert fires — from Azure Monitor, AKS, Elasticsearch, or manually — Corvin collects evidence from all connected sources, generates a structured Root Cause Analysis using an LLM, proposes ranked fix actions, and delivers results to your team via Teams, email, or the web dashboard. Human SREs approve and execute fixes through the same interface.

First-place winner, MetLife Hackathon 2026. Now evolving into a production enterprise platform.

---

## Core Workflow

```
Alert fires (Azure Monitor / Predictive / Manual / Teams / CLI)
    ↓
Trigger Normalization — InvestigationRequest
    ↓
Evidence Collection — Azure Log Analytics, AKS, Elasticsearch, APIM, Container Logs
    ↓
Code Enrichment — Git repository context injected automatically
    ↓
LLM Root Cause Analysis — Structured RCAOutput with confidence rating
    ↓
[Optional] Debate Mode — 3 competing hypotheses, SRE picks winner
    ↓
Fix Strategy Generation — Ranked actions with risk levels
    ↓
Human Approval Gate — pending → approved | rejected | acknowledged
    ↓
Execution — AKS: restart pod | rollback deployment | scale deployment
    ↓
Post-Mortem Generation — Blameless postmortem PDF + markdown
    ↓
Runbook Update — LLM-generated resolution step appended to knowledge base
```

---

## Delivery Surfaces

| Surface | Description |
|---------|-------------|
| **Web Dashboard** | React 18 SPA — investigations, SLO monitoring, topology, predictive analytics, War Games, Corvin Command Center |
| **Teams Bot** | ChatOps — receive RCA cards, approve/reject fix actions inline |
| **REST API** | Full control plane at `http://localhost:8000/docs` |
| **CLI** | Interactive Typer REPL for operator workflows |

---

## Quick Start

### Prerequisites

- Python 3.13+
- Node 20+
- PostgreSQL 16 (or use SQLite for local dev — set `DB_BACKEND=sqlite` in `.env`)
- Azure credentials (see [setup/](setup/))

### 1. Backend

```powershell
# Install dependencies
pip install -e ".[dev]"

# Copy and populate environment variables
cp .env.example .env
# Edit .env — see setup/04_env_file.md for all required values

# Apply database migrations
alembic upgrade head

# Seed demo data (optional)
$env:CORVIN_DEMO_MODE = "true"

# Start the API server
uvicorn apps.api.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 2. Frontend

```powershell
cd apps/web
npm install
npm run dev
```

Web app: `http://localhost:5173`

### 3. Run Tests

```powershell
pytest tests/ -v --tb=short
```

---

## Repository Layout

```
corvin/              # Core platform (evidence, investigation engine, AI strategy layer)
  core/              # Pydantic contracts + config loader — single source of truth
  evidence/          # Data adapters: Log Analytics, AKS, Elastic, APIM, Container Logs
  strategy/          # RCA, Fix Strategy, Post-Mortem, Chat, Runbook, Chaos, Agent tools
  investigation/     # Investigation engine + streaming + topology
  execution/         # ExecutionService — AKS actions, gated by approval status
  connectors/        # Pluggable connector registry + credential management
  storage/           # SQLAlchemy ORM models + repository pattern
  delivery/          # Outbound: Teams, Email, ADO, SharePoint
  triggers/          # Azure alerts, predictive monitor, validation automation
  slo/               # SLO snapshot background job
  toolsets/          # Agent tool definitions

apps/
  api/               # FastAPI entry point + all route handlers
  cli/               # Interactive CLI (Typer)
  teams/             # Teams bot (BotBuilder)
  web/               # React 18 + Vite + TypeScript frontend

config/              # YAML policy and integration configs (env-var expanded at runtime)
alembic/             # Database migrations
knowledge/           # Site knowledge + runbook library (disk tier, DB tier is primary)
tests/               # Slice tests, adapter tests, contract tests, orchestration tests
setup/               # Step-by-step setup guides for each integration
docs/                # Architecture, roadmap, technical debt, and other project docs
```

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, module map, data flow, design decisions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Code conventions, testing patterns, contribution standards |
| [AGENTS.md](AGENTS.md) | AI agent guidance — mental model, rules, version state |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Product roadmap — completed versions and enterprise build sequence |
| [docs/TECH_DEBT.md](docs/TECH_DEBT.md) | Prioritized technical debt register |
| [docs/ENTERPRISE_READINESS.md](docs/ENTERPRISE_READINESS.md) | Enterprise maturity assessment and target architecture |
| [docs/SAAS_READINESS.md](docs/SAAS_READINESS.md) | SaaS readiness assessment and multi-tenant migration plan |
| [setup/README.md](setup/README.md) | Setup index — all integration guides |

---

## Current Status

**Version:** V5.4 — AI Runbook Management (complete)

**Active work:** Enterprise Refinement Track — EV1 Connector Onboarding & Identity Model

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full build history and active enterprise sequence.

---

## Technology Stack

**Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, LiteLLM, Pydantic 2  
**Frontend:** React 18, TypeScript, Vite 5, TailwindCSS 4, React Query, Recharts, XYFlow  
**AI:** LiteLLM (Azure OpenAI / OpenAI), pgvector (semantic RAG)  
**Infrastructure:** PostgreSQL 16, Docker Compose, Azure App Service, Azure Static Web Apps  
**Integrations:** Azure Monitor, AKS, Elasticsearch, Azure DevOps, Teams, SharePoint, SMTP  

---

## License

Internal platform. Not licensed for external distribution.

# Corvin — Architecture Reference

**Version:** V5.4  
**Last Updated:** 2026-06-10  
**Status:** Authoritative — this document supersedes all previous architecture docs.

Related archived docs: `docs/archive/architecture_review_v3.md`, `docs/archive/CORVIN_COMMAND_CENTER_v395.md`

---

## System Overview

Corvin is a layered, Azure-native incident investigation control plane. It is not a monitoring tool — it sits above your monitoring stack and automates the human reasoning work: collecting evidence, correlating signals, generating root cause hypotheses, and proposing remediation.

The system is designed so that **the LLM never operates without structured evidence** and **no automated action executes without human approval**.

---

## Architecture Tiers

```
┌──────────────────────────────────────────────────────────────────────┐
│  Delivery Surfaces                                                    │
│  React SPA  ──  Teams Bot  ──  CLI (Typer)  ──  REST API            │
└─────────────────────────────┬────────────────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼────────────────────────────────────────┐
│  FastAPI Control Plane                                                │
│  /investigations  /corvin  /applications  /slo  /triggers  /ai  ...  │
└──────────────┬───────────────────────────────┬────────────────────────┘
               │                               │
┌──────────────▼──────────────┐   ┌────────────▼──────────────────────┐
│  Investigation Engine        │   │  Corvin Command Center             │
│  Enrich → RCA → Fix          │   │  Multi-session agentic chat        │
│  Human approval gate         │   │  15 live tools, SSE streaming      │
└──────────────┬──────────────┘   └────────────┬──────────────────────┘
               │                               │
┌──────────────▼──────────────────────────────▼────────────────────────┐
│  AI Strategy Layer (LiteLLM)                                          │
│  RCAGenerator · FixStrategyGenerator · PostMortemService              │
│  AlertCorrelationEngine · CapacityForecaster · RunbookBuilder         │
│  CausalChainGenerator · NLToKQLService · CommsDraftGenerator          │
│  AutonomousAgent · MultiAgentOrchestrator · ChaosExperimentGenerator  │
└──────────────┬────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  Evidence Plane                                                       │
│  LogAnalyticsAdapter · AKSAdapter · ElasticAdapter                   │
│  ContainerLogsAdapter · AzureActivityAdapter · APIMAnalyticsAdapter  │
│  CodeEnrichment (Git repository context)                              │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  Storage Layer                                                        │
│  PostgreSQL (primary) · SQLite (dev/test only)                        │
│  pgvector (semantic RAG) · AES-256-GCM credential store              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Investigation Pipeline

The investigation engine (`corvin/investigation/engine.py`) owns stage transitions for a single investigation. It is the only caller of the enrichment service, RCA generator, and fix strategy generator — routes never call these directly.

```
InvestigationRequest (trigger_source, service_name, environment, description)
    │
    ▼  EnrichmentService.enrich()
EvidenceBundle (elastic_logs, log_analytics_apim, aks_context, container_metrics, ...)
    │
    ▼  enrich_with_code_context()
EvidenceBundle + code_context (Git repository source files for stack traces)
    │
    ▼  PromptBuilder.build(request)
system_prompt (runbooks injected from DB tier → disk tier fallback)
    │
    ▼  RCAGenerator.generate(request, evidence, system_prompt)
RCAOutput (root_cause, contributing_factors, confidence, evidence_references)
    │
    ▼ [Optional] HypothesisService.generate_hypotheses()
list[RCAHypothesis] — SRE selects winner; FixStrategyGenerator reruns
    │
    ▼  FixStrategyGenerator.generate(request, rca)
FixStrategyOutput (actions[], risk_level, requires_approval)
    │
    ▼  InvestigationResult persisted → Teams / Email / ADO delivery
```

---

## Module Map

### `corvin/core/`
The foundation. Everything else imports from here; nothing here imports from other modules.

| File | Purpose |
|------|---------|
| `contracts.py` | All Pydantic domain models — single source of truth. Any change here requires an Alembic migration. |
| `config_loader.py` | YAML config loading with `${ENV_VAR}` expansion |
| `knowledge_loader.py` | Two-tier runbook loader: DB RunbookRow first, disk catalog fallback |
| `priority.py` | Incident priority classification (P1/P2/P3) from environment + blast radius |

### `corvin/evidence/`
Adapters that collect evidence from external systems. All adapters must return empty list/dict on failure — never raise.

| Adapter | Data Source |
|---------|------------|
| `log_analytics_adapter.py` | Azure Log Analytics — APIM request logs, KQL queries |
| `aks_adapter.py` | AKS Kubernetes API — pod status, events, deployments |
| `elastic_adapter.py` | Elasticsearch — application logs and metrics |
| `container_logs_adapter.py` | Azure Container Insights — resource metrics, pod inventory |
| `azure_activity_adapter.py` | Azure Activity Log — infrastructure changes |
| `apim_analytics_adapter.py` | APIM gateway analytics — request rates, error breakdown |

### `corvin/strategy/`
All AI generation and analysis modules.

| Module | Purpose |
|--------|---------|
| `rca_generator.py` | LLM-based root cause analysis (streaming + non-streaming) |
| `fix_strategy_generator.py` | Ranked fix actions with risk levels |
| `postmortem_service.py` | Blameless post-mortem document generation |
| `chat_service.py` | Investigation-scoped copilot chat |
| `agent_service.py` | Corvin Command Center agentic loop |
| `agent_tools.py` | 15 tool definitions for the Command Center agent |
| `runbook_builder.py` | Multi-turn conversational runbook builder |
| `alert_correlation.py` | Temporal + topology alert grouping and suppression |
| `capacity_forecaster.py` | Linear regression + LLM narrative for resource exhaustion |
| `causal_chain.py` | DAG-based causal chain from RCA output |
| `comms_draft.py` | Audience-targeted communications (executive, technical, customer) |
| `nl_to_kql.py` | Natural language to KQL with guardrails |
| `autonomous_agent.py` | Autonomous 16-tool function-calling investigation loop |
| `multi_agent.py` | Multi-agent orchestrator (SelectorGroupChat pattern) |
| `chaos_engine.py` | LLM-generated chaos experiment definitions |
| `hypothesis_service.py` | Root Cause Debate Mode — N competing hypotheses |
| `blast_radius.py` | Affected service + user + revenue estimation |
| `similarity_network.py` | pgvector-based semantic similarity across past incidents |
| `roi.py` | MTTR savings and engineering cost calculations |
| `sla.py` | SLA countdown and breach prediction |

### `corvin/connectors/`
Pluggable connector registry — credentials resolved at runtime, not hardcoded.

| File | Purpose |
|------|---------|
| `registry.py` | Connector factory — resolves type → adapter class |
| `config_resolver.py` | Per-application connector config lookup (DB → env fallback) |
| `crypto.py` | AES-256-GCM encryption for DB-stored credentials |
| `secret_ref.py` | Azure Key Vault reference resolver |
| `azure_monitor.py` | Azure Monitor connector |
| `aks.py` | AKS connector |
| `elastic.py` | Elasticsearch connector |
| `git_repo.py` | Git repository connector (code context enrichment) |
| `byoa.py` | Bring Your Own Azure — custom connector pattern |

### `corvin/storage/`

| File | Purpose |
|------|---------|
| `models.py` | All SQLAlchemy ORM models — 28 tables |
| `db.py` | Session factory, dual-backend support (PostgreSQL / SQLite) |
| `repository.py` | `InvestigationRepository` — data access layer |

### `corvin/delivery/`
All outbound notification and document delivery.

| Module | Delivers To |
|--------|------------|
| `teams_adapter.py` | Microsoft Teams (adaptive cards) |
| `email_adapter.py` | SMTP email (RCA PDF attachment) |
| `azure_devops_adapter.py` | ADO work items |
| `ado_wiki_adapter.py` | ADO Wiki pages |
| `sharepoint_adapter.py` | SharePoint document library |
| `rca_notification.py` | Orchestrates RCA delivery across enabled channels |
| `outbound_connectors.py` | DB-configured outbound connector dispatch |

### `apps/api/routes/`

| Route | Prefix | Key Endpoints |
|-------|--------|---------------|
| `investigations.py` | `/investigations` | Full CRUD, approve/reject/execute, stream, heatmap, topology |
| `corvin_agent.py` | `/corvin` | Command Center sessions and streaming chat |
| `applications.py` | `/applications` | Application panel, services, connectors, SLOs |
| `ai_features.py` | `/ai` | Alert correlation, capacity forecast, runbook sessions |
| `slo.py` | `/slo` | SLO snapshot history and live status |
| `validations.py` | `/validations` | Synthetic validation runs and automation policies |
| `chaos.py` | `/chaos` | Chaos experiment lifecycle |
| `triggers.py` | `/triggers` | Azure alert webhook, alert simulation |

---

## Database Schema (28 tables)

### Investigation Core
- `investigation_requests` — one row per investigation
- `rca_outputs` — RCA result, FK to investigation_requests
- `fix_strategy_outputs` — fix actions, FK to investigation_requests
- `evidence_bundles` — all collected evidence, FK to investigation_requests
- `post_mortems` — generated postmortem documents

### AI Conversation
- `corvin_sessions` — Command Center chat sessions
- `corvin_messages` — individual turns (role, content, thinking, tool_calls, tool_results)
- `chat_messages` — investigation-scoped copilot turns
- `runbook_sessions` — conversational runbook builder sessions

### Application Registry
- `applications` — top-level application container
- `application_services` — named services within an application
- `log_sources` — configured inbound connectors
- `outbound_connectors` — delivery destinations
- `notification_contacts` — people/channels for alert delivery
- `application_environments` — per-application environment definitions
- `slo_configs` — SLO/SLI configuration per service
- `slo_snapshots` — time-series SLO measurements

### Knowledge
- `knowledge_base` — DB-backed site knowledge entries
- `runbooks` — DB-backed runbook entries (DB tier primary, disk fallback)
- `simulator_presets` — alert simulation scenarios
- `playwright_scripts` / `playwright_runs` — synthetic test execution

### Operations
- `predictive_alerts` — predicted incidents before they fire
- `predictive_penalties` — accuracy feedback for the predictive loop
- `validation_definitions` / `validation_runs` — health check definitions
- `chaos_runs` — chaos experiment execution records
- `approval_decisions` — correlation suppression and scaling approvals
- `validation_automation_policies` — policy-driven auto-trigger rules

---

## Key Design Decisions

### 1. Contracts as single source of truth
All domain types are Pydantic models in `corvin/core/contracts.py`. The ORM models are thin wrappers. Any contract change requires a matching Alembic migration.

### 2. Evidence-gated RCA
`RCAGenerator.generate()` refuses to call the LLM if `EnrichmentService` returns no evidence. This prevents hallucinated root causes. Controlled by `require_evidence_before_rca` in `config/policies/investigation.yaml`.

### 3. Approval gate is API-enforced, not UI-enforced
`POST /investigations/{id}/execute` returns HTTP 409 if `approval_status != approved`. The gate is also enforced inside `ExecutionService`. No execution is possible through any surface without an approved state in Postgres.

### 4. LiteLLM as unified LLM gateway
All LLM calls go through LiteLLM. Model IDs, API keys, and endpoints are in `config/models/llm.yaml` and environment variables — never hardcoded in service classes.

### 5. Two-tier knowledge loading
Runbooks are loaded DB-first (`RunbookRow` table, managed via Applications UI), then disk fallback (`knowledge/runbooks/catalog.json`). DB runbooks take effect immediately with no server restart.

### 6. Adapter resilience
Every evidence adapter method must return an empty list or dict on failure. Partial evidence is better than no investigation. `EnrichmentService` handles any combination of adapter failures gracefully.

### 7. Config-driven behavior
Business rules (SLA thresholds, blast radius constants, confidence gates, currency, voice name) live in `config/policies/*.yaml`. Operators tune behavior without touching code.

---

## Corvin Command Center

The Command Center (`/corvin`) is an independent, full-page ChatGPT-style agentic interface, separate from the investigation-scoped floating chat widget.

**Architecture:**
- Backend: `corvin/strategy/agent_service.py` → `CorvinAgentService.stream_chat_simple()`
- Tool definitions: `corvin/strategy/agent_tools.py` → 15 tools in OpenAI function format
- Routes: `apps/api/routes/corvin_agent.py` → `/corvin/sessions/...`
- Persistence: `corvin_sessions` + `corvin_messages` tables (full history, reasoning, tool_calls)

**Agentic Loop:**
```
User message → Build messages (system prompt + session history)
→ LLM call with tool_choice="auto"
→ If tool_calls: execute each tool, emit SSE, append results, re-call LLM (max 6 rounds)
→ Final text answer streamed token-by-token
→ SSE [DONE] signal
```

**SSE event types:** `thinking` · `tool_call` · `tool_result` · `text` · `error`

**15 live tools:** platform_stats, recent_incidents, investigation_detail, predictive_alerts, service_score, roi, service_topology, blast_radius, postmortem, similar_incidents, site_knowledge, runbook, run_kql (Azure), aks_health (Azure), elastic_query (Azure)

---

## Background Jobs

Two background tasks start with the application lifespan in `apps/api/main.py`:

| Task | Module | Default Interval | Purpose |
|------|--------|-----------------|---------|
| Predictive Monitor | `corvin/triggers/predictive.py` | 300s (disabled by default) | Scans evidence for pre-incident signals |
| SLO Snapshot | `corvin/slo/snapshot.py` | 3600s | Samples SLO compliance for all configured services |

Both tasks start as `asyncio.create_task()` per worker — see `docs/TECH_DEBT.md` (TD-H7) for the multi-worker duplication risk.

---

## Version History

| Version | Theme | Status |
|---------|-------|--------|
| V1 | Trigger → Evidence → RCA → Fix Strategy | Complete |
| V1.5 | Real Azure cloud adapters wired | Complete |
| V2 | Teams ChatOps, Human-in-Loop Execution, SSE Streaming | Complete |
| V2.5 | Incident Memory, Morning Briefing, Confidence Meter | Complete |
| V3 | Premium React UI, Post-Mortem, Corvin Score | Complete |
| V3.5–V3.9 | Alert Simulator, Predictive Detection, SLA, ROI, Voice TTS, War Room | Complete |
| V4.5 | DB-driven AKS onboarding, filterable topology | Complete |
| V5.0 | Autonomous Agent, Causal Chain, NL→KQL, Comms Draft | Complete |
| V5.1 | Multi-Agent, Chaos Engine, IDE Integration, Voice Incident | Complete |
| V5.2 | UX Maturity: Plus Jakarta Sans, CHAD seed, Outbound Connector Builder | Complete |
| V5.3 | AI Intelligence Suite: Alert Correlation, Capacity Forecaster, War Games | Complete |
| V5.4 | AI Runbook Management: DB library, prompt builder fix, predictive enrichment | Complete |
| EV1 | Enterprise: Connector Onboarding & Identity Model | **Active** |

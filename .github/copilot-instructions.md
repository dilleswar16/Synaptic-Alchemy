# Corvin Workspace Instructions

This workspace defines Corvin, an Azure-native investigation platform for a personal project. Treat this as a fresh product build, not a direct fork of Vishwakarma.

## Product Direction

- Build the control plane in Python.
- Build the web app in React with Vite.
- Use Postgres for persistence.
- Target Azure alerts, AKS, Elastic, Azure Log Analytics, REST API, CLI, web app, and Teams.
- The monitored applications may be Java Spring Boot, but the investigation platform itself is Python.

## Workflow Contract

The target workflow is:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy -> Human Approval -> Execute Fix -> Verify -> Learn

For V1, stop at RCA plus Fix Strategy. Do not implement autonomous execution in V1.
For V1.5, wire all adapters to real Azure cloud services and validate end-to-end with no mocks.
For V2, implement Two-Way ChatOps targeting Teams, Human-in-the-Loop Execution (Approve & Execute via AKSAdapter), and Streaming RCA via SSE.
For V2.5, implement AI intelligence features: Incident Memory, Morning Briefing (Jarvis Mode), and Confidence Meter.
For V3, implement the Premium React UI overhaul, Blameless Post-Mortem auto-generator, and Corvin Score health dashboard.
For V3.5, implement the hackathon demo core: Alert Simulator, Teams Adaptive Cards with inline approve, Blast Radius Estimator, Corvin Score Gauge.
For V3.7, implement intelligence layer: Predictive Detection, SLA Countdown, Cross-Service Dependency Visualizer, Remediation Preview.
For V3.9, implement enterprise polish: Voice Morning Briefing, ROI Dashboard, 3AM Mode, Runbook Auto-Update, War Room Channel, Confidence Routing.
For V4, implement Semantic Search / Vector RAG using pgvector on Azure Postgres.
For V5.0, implement Agentic AI P0: AutonomousAgent (16-tool function-calling loop), CausalChainGenerator (DAG from RCA), NLToKQLService (natural language to KQL with guardrails), CommsDraftGenerator (audience-targeted comms).
For V5.1, implement Agentic AI P1: MultiAgentOrchestrator (SelectorGroupChat pattern), ChaosExperimentGenerator (post-RCA resilience tests), IDEIntegrationService (VS Code context + deploy safety), VoiceIncidentService (Azure Speech STT → structured report).
For V5.2, implement UX Maturity: Plus Jakarta Sans font (replacing DM Sans, base 15.5px), CHAD-only demo seed, full outbound connector builder (variables, auth types, payload templates, OAuth 2.0).

## Current State (V5.2 complete)

### Design System — Font
- **Font:** Plus Jakarta Sans (Google Fonts, weights 200–800 + italic 400)
- Base `font-size: 15.5px` on `html`, `letter-spacing: -0.01em`
- `--font-display` and `--font-body` CSS vars in `apps/web/src/index.css`
- JetBrains Mono unchanged for `--font-mono`

### Application Onboarding — Tabs
`ApplicationsPage` has 4 tabs: Services | Connectors | Notifications | SLO

Connectors tab is split:
- **Inbound connectors** — webhook/API inbound (existing)
- **Outbound connectors** — destinations Corvin pushes alerts to (new)

Supported outbound connector types: `teams_webhook`, `servicenow`, `email`, `pagerduty`, `generic_http`

### Outbound Connector `config_json` Schema
```typescript
interface ConnectorConfig {
  endpoint?: string
  endpoint_fields?: {
    table?: string        // ServiceNow table name
    port?: string         // SMTP port (email)
    from?: string         // sender address (email)
    http_method?: string  // GET/POST/PUT/PATCH (generic_http)
  }
  auth?: {
    type: 'none' | 'bearer' | 'api_key' | 'basic' | 'oauth2'
    bearer_token?: string
    api_key?: string
    api_key_header?: string   // default: 'X-API-Key'
    username?: string
    password?: string
    token_url?: string        // oauth2
    client_id?: string        // oauth2
    client_secret?: string    // oauth2
    scopes?: string           // oauth2, space-separated
  }
  variables?: Array<{ key: string; default_value: string }>
  payload_template?: string   // JSON string with {{key}} interpolation
  webhook_url?: string        // legacy — kept for backward compat
}
```

Built-in interpolation variables for `payload_template` and `default_value`:
`{{service_name}}`, `{{rca_summary}}`, `{{confidence}}`, `{{environment}}`, `{{request_id}}`

### Demo Seed
- `apps/api/seed_demo.py` seeds a single "CHAD" app with 3 services: `fundapis`, `fundsso`, `partnerapis`
- Idempotent: checks `filter_by(name="CHAD")` before inserting

## Current State

**Version:** V5.4 complete. All hackathon feature versions (V1–V5.4) are done.  
**Active track:** Enterprise Refinement — EV1 Connector Onboarding & Identity Model.  
**Next:** EV2 Trust Foundation (Authentication, RBAC, Audit trail).

## Delivery Rules

- The hackathon build sequence (V1 → V5.4) is complete. Do not revisit it.
- All new work follows the Enterprise Refinement sequence: EV1 → EV2 → EV3 → EV4 → EV5.
- Within each EV slice, build testable vertical slices instead of broad scaffolding.
- See `docs/ROADMAP.md` for the full enterprise build sequence.
- The `progress.md` file is deprecated — roadmap and status live in `docs/ROADMAP.md` and `AGENTS.md`.

## Architecture Rules

- Keep triggers, evidence sources, investigation engine, approval flow, execution flow, and delivery surfaces as separate modules.
- Use adapter-style boundaries for integrations.
- Keep configuration externalized and replaceable.
- Do not hardcode environment URLs, tool endpoints, or secrets inside core logic.

## Configuration Rules

- Place replaceable settings in dedicated folders and files by concern.
- Separate model config, integration config, tool config, policy config, and environment overrides.
- Prefer references and placeholders for secrets.

## Context Usage

- Use `AGENTS.md` as the primary resumption file (version state, current focus, conventions).
- Use `ARCHITECTURE.md` for system architecture and module map.
- Use `CONTRIBUTING.md` for code conventions and testing patterns.
- Use `docs/ROADMAP.md` for build sequence and enterprise plan.
- Use `docs/TECH_DEBT.md` before any refactor (know what debt exists).
- Use `docs/ENTERPRISE_READINESS.md` for enterprise gap details.
- Use `docs/copilot-context/shared/` for deep product context.
- Use `docs/copilot-context/versions/enterprise-refinement/` for active EV slice specs.
- Use `docs/copilot-context/config-blueprints/` for configuration layout decisions.

## Technology Constraints

- Azure, not AWS.
- Elasticsearch is the primary store for application logs and AKS metrics.
- Azure Log Analytics is the primary source for APIM evidence.
- Azure Monitor alerts are the primary automation trigger source.
- Authentication is **required** — all routes must be protected via OIDC/JWT (EV2). This is the highest-priority enterprise gap.
- LiteLLM is the unified LLM gateway — never call Azure OpenAI or OpenAI directly.
- PostgreSQL is the production database — SQLite is for local dev and testing only.

## Enterprise Architecture Rules

- Authentication must be added before any external customer deployment (TD-C1).
- `approved_by` identity must come from JWT claims, never from request parameters (TD-C2).
- No hardcoded customer-specific values (currency, locale, org names) in code or config (TD-M5).
- All automated actions require human approval — the gate is API-enforced, not UI-enforced.
- See `docs/TECH_DEBT.md` for the full debt register with remediation guidance.
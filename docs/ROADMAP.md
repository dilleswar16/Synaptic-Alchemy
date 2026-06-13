# Corvin — Product Roadmap

**Last Updated:** 2026-06-12 (Phase 2-lite complete)  
**Status:** Authoritative — consolidates `progress.md`, `productization-plan.md`, `hackathon-roadmap.md`, prior EV1–EV5 plan  
**Current Phase:** Phase 2 — Architecture Modernization (lite pass delivered; remainder deferred by decision)

---

## Completed Feature Versions (V1 — V5.4)

All hackathon and post-hackathon feature versions are complete and stable. Do not revisit.

| Version | Theme | Status |
|---------|-------|--------|
| V1 | Trigger → Evidence → RCA → Fix Strategy | Complete |
| V1.5 | Real Azure cloud adapters wired and validated | Complete |
| V2 | Teams ChatOps, Human-in-Loop Execution, SSE Streaming | Complete |
| V2.5 | Incident Memory, Morning Briefing, Confidence Meter | Complete |
| V3 | Premium React UI, Post-Mortem, Corvin Score | Complete |
| V3.5 | Alert Simulator, Teams Adaptive Cards, Blast Radius, Score Gauge | Complete |
| V3.7 | Predictive Detection, SLA Countdown, Dependency Topology, Remediation Preview | Complete |
| V3.9 | Voice TTS, ROI Dashboard, 3AM Mode, Runbook Auto-Update, War Room, Confidence Routing | Complete |
| V4 | Semantic Search / Vector RAG | Deferred — requires pgvector on Azure PostgreSQL |
| V4.1 | Priority Classification, Progressive Disclosure UI | Complete |
| V4.5 | DB-driven AKS onboarding, filterable live topology | Complete |
| V5.0 | Agentic AI P0: Autonomous Agent, Causal Chain, NL→KQL, Comms Draft | Complete |
| V5.1 | Agentic AI P1: Multi-Agent, Chaos Engine, IDE Integration, Voice Incident | Complete |
| V5.2 | UX Maturity: Plus Jakarta Sans, CHAD demo seed, Outbound Connector Builder | Complete |
| V5.3 | AI Intelligence Suite: Alert Correlation, Capacity Forecaster, War Games, War Room Banner | Complete |
| V5.4 | AI Runbook Management: 6 production runbooks, prompt builder bug fix, predictive enrichment, scaffold UI | Complete |

---

## Phase 0 — Knowledge & Governance

**Status: Complete**

Established the governance and documentation foundation required before systematic engineering work. Delivered:

- Canonical architecture, roadmap, tech debt, enterprise, and SaaS readiness documents
- Technical debt register with Critical/High/Medium/Low classification
- Governance gap report across 15 domains
- AGENTS.md and copilot instructions updated to V5.4 state
- Archive strategy executed (partial — originals need deletion, tracked in PB-029)

**Reference:** `docs/TECH_DEBT.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/ENTERPRISE_READINESS.md`, `docs/SAAS_READINESS.md`

---

## Phase 1 — Productization & Genericization

**Status: Active**  
**Entry Score:** 28% productized (core engine is generic; assets, config, knowledge base are not)  
**Exit Criteria:** A new customer can deploy Corvin and onboard their applications, services, runbooks, and branding through configuration only — no source-code modifications required.

### What This Phase Is NOT

Phase 1 does not include authentication, RBAC, SSO, SCIM, billing, or multi-tenancy. Those are Phase 3–5. The goal here is to strip all MetLife/CHAD specificity and make the platform configuration-driven.

### Milestone Map

| Milestone | Description | Backlog Items | Status |
|-----------|-------------|---------------|--------|
| P1.A | Audit complete, backlog defined | — | **Done** |
| P1.A2 | CHAD classification + template library | PB-031, PB-032 | **Done** |
| P1.B | Brand & asset genericization | PB-001, PB-017, PB-019 | **Done** — 2026-06-11 |
| P1.C | Knowledge base genericization | PB-002, PB-003, PB-007, PB-008 | **Done** |
| P1.D | Demo data & test fixture genericization | PB-005, PB-006, PB-016 | **Done** — 2026-06-11 |
| P1.E | Configuration externalization | PB-009, PB-010, PB-011, PB-012 | **Done** — 2026-06-11 |
| P1.F | Connector onboarding hardening | PB-013, PB-014, PB-015 | **Done** — 2026-06-11 |
| P1.G | Prompt registry | PB-021 | **Done** — 2026-06-11 |
| P1.H | Documentation genericization | PB-022, PB-025 | **In Progress** — PB-022 done; PB-025 remaining |
| P1.I | Developer experience improvements | PB-020, PB-023, PB-024 | **Done** — 2026-06-11 |

### Sprint 1 — Complete (2026-06-10 / 2026-06-11)

All Sprint 1 P0 items delivered. Platform no longer contains MetLife branding, CHAD service names, or hardcoded Azure identifiers in the demo/test/asset layers.

**Completed:** PB-004, PB-006, PB-002, PB-003, PB-032, PB-005, PB-017, PB-001

### Sprint 2 — Complete (2026-06-11)

All Sprint 2 configuration and connector items delivered. TD-H3 confirmed not blocking (0013 was already a proper merge migration, single head at 0027).

**Completed:** TD-H3 (no code change needed), PB-009, PB-012, PB-013 (confirmed V5.4), PB-014, PB-010, PB-011, PB-015  
**New Alembic migrations:** 0025 (locale/currency/voice), 0026 (blast radius metrics), 0027 (toolset profile)

### Sprint 3 — Complete (2026-06-11)

All Sprint 3 items delivered. Phase 1 productization is complete (one P3 polish item remaining).

**Completed:** PB-016 (no-op), PB-021, PB-019, PB-020, PB-022, PB-023, PB-024  
**New files:** `corvin/core/prompt_registry.py`, `config/prompts/*.v1.yaml` (11 files), `config/prompts/overrides/`, `.pre-commit-config.yaml`  
**Test count after Sprint 3:** 83 pass across core test suites

### Phase 1 — Effectively Complete

Phase 1 exit criteria met: a new customer can deploy Corvin and onboard their applications through configuration only — no source-code modifications required. Only P3 polish item remaining: PB-025 (DEMO_SETUP.md documentation).

**Reference:** `docs/PRODUCTIZATION_ASSESSMENT.md`, `docs/PRODUCTIZATION_BACKLOG.md`, `docs/PROMPT_ARCHITECTURE.md`

---

## Phase 2 — Architecture Modernization

**Status: Active — "Phase 2-lite" pass complete (2026-06-12)**  
**Prerequisites:** Phase 1 complete.  
**Exit Criteria:** Platform is horizontally scalable, observable, and operationally maintainable.

### Phase 2-lite — Complete (2026-06-12)

Scoped low-risk pass agreed with the owner. Big-ticket items deferred (see below).

| Item | Tech Debt Ref | Status |
|------|---------------|--------|
| `get_session()` fix | TD-H1 | **Done** — also fixed silently broken demo seeding (`next()` on a context manager raised TypeError) |
| Structured JSON logging | — | **Done** — `corvin/core/logging_config.py` + `request_context.py`; `request_id` on every line; `X-Request-ID` header via `RequestContextMiddleware` |
| API versioning (`/v1/` prefix) | TD-M3 | **Done** — `ApiVersionMiddleware` (pure ASGI); root paths kept for backward compat; `X-API-Version: 1` |
| RFC 7807 error responses | TD-M9 | **Done** — `apps/api/errors.py`; `detail` string preserved for existing clients; error code enum still open |
| CORS / multi-worker guards | TD-H6, TD-H7 | **Done (mitigation)** — loud startup warnings for wildcard CORS and >1 worker |
| Test suite isolation | TD-M14 | **Done** — `tests/conftest.py`: email kill-switch, throwaway SQLite DB, no disk learnings writes |
| Drift repair | TD-M12, TD-M13 | **Done** — 34 stale tests updated to current contracts; circular import (engine→connectors) fixed |

### Deferred (owner decision 2026-06-12 — do not start without sign-off)

| Item | Tech Debt Ref | Decision |
|------|---------------|----------|
| Async investigation pipeline | TD-H2 | Deferred — synchronous acceptable at current scale; revisit before concurrent-load deployments |
| Background task leader election | TD-H7 | Deferred — pairs with TD-H2 worker design; run single API worker meanwhile (startup warns) |
| Rate limiting | TD-M4 | Not planned in code — delegated to APIM gateway; backend network access must be restricted to APIM |
| Circuit breakers on adapters | — | Deferred — adapters already degrade gracefully via try/except fallbacks |
| CORS hardening (full) | TD-H6 | Deferred — startup warning shipped; enforce allowlist before non-local deployment |

### Remaining Phase 2 scope (not yet scheduled)

| Item | Tech Debt Ref | Description |
|------|---------------|-------------|
| OpenTelemetry instrumentation | — | Trace IDs on all LLM calls, DB queries, adapter calls → Azure Monitor (builds on structured logging) |
| Business logic extraction | TD-M1, TD-M2 | `AnalyticsService`, `TopologyService`; route handlers < 30 lines |
| Readiness probe | — | `GET /health/ready` checks DB connectivity + critical dependencies |
| Error code enum | TD-M9 follow-up | Stable machine-readable codes in problem+json `type` field |

**Reference:** `docs/TECH_DEBT.md` (High and Medium sections)

---

## Phase 3 — Enterprise Foundation

**Status: Planned**  
**Prerequisites:** Phase 2 complete.  
**Exit Criteria:** Platform is safe for external customer deployment. All routes protected. Identity is verified. Audit trail is tamper-resistant.

### Scope

1. **Authentication (TD-C1)** — OIDC/JWT middleware via Azure Entra ID. All 30+ routes require valid token.
2. **Authorization / RBAC** — Roles: `sre`, `viewer`, `admin`, `executive`. Route-level `Depends()` guards. Application membership model.
3. **Audit trail** — `audit_events` table, append-only. Identity from JWT claims. Route to Azure Event Hub for WORM compliance.
4. **Identity in approvals (TD-C2)** — `approved_by` derived from JWT `sub` claim. Never from request parameters.
5. **Secret management** — Azure Key Vault integration. All credentials as KV references, not raw env vars.
6. **Webhook security** — HMAC validation on `/triggers/azure-alert`.
7. **Data retention** — Background purge job: investigations 1yr, evidence 90d, chat 30d.
8. **GDPR right to erasure** — `DELETE /admin/data` cascading purge.
9. **Infrastructure-as-code** — Bicep or Terraform for all Azure resources.
10. **`SECURITY.md`** — Responsible disclosure policy and contact.

**Reference:** `docs/ENTERPRISE_READINESS.md`

---

## Phase 4 — Multi-Tenant Foundation

**Status: Planned**  
**Prerequisites:** Phase 3 complete (authentication must exist before tenant isolation is meaningful).  
**Exit Criteria:** Multiple organizations can use one Corvin deployment with full data isolation.

### Scope

1. `tenants` table + tenant configuration API (`GET/PATCH /admin/tenants/{id}`)
2. `tenant_id UUID NOT NULL` added to all 28 data tables
3. PostgreSQL Row Level Security policies (`app.tenant_id` session variable)
4. Per-tenant LLM provider and model selection (BYOK)
5. Per-tenant encryption key derivation (Azure Key Vault + tenant KID)
6. Tenant onboarding API
7. `tests/tenancy/` — isolation test suite: assert cross-tenant queries return 0 results

**Reference:** `docs/SAAS_READINESS.md` — Phases A–D

---

## Phase 5 — SaaS Scale

**Status: Planned**  
**Prerequisites:** Phase 4 complete.  
**Exit Criteria:** Commercial multi-tenant operations are possible.

### Scope

1. Tenant admin portal (user management, connector management, billing overview)
2. Usage metering (LLM tokens + investigation count per tenant per billing period)
3. Billing integration (Stripe or Azure Marketplace)
4. Feature entitlement flags per subscription tier (`trial | starter | professional | enterprise`)
5. Per-tenant branding (logo, primary color, custom domain)
6. Tenant data export API (GDPR)
7. SCIM user provisioning

**Reference:** `docs/SAAS_READINESS.md` — Phase E

---

## Phase 6 — Product Expansion

**Status: Planned**  
**Prerequisites:** Phase 5 complete.

### Scope (candidate items — not committed)

| Item | Description |
|------|-------------|
| pgvector Semantic RAG | Vector similarity search on past incidents; requires pgvector on Azure PostgreSQL |
| On-call schedule management | PagerDuty-equivalent scheduling, escalation chains |
| Error budget deployment gates | CI/CD integration to block releases on budget exhaustion |
| VS Code extension | IDE-native incident context during active debugging |
| Azure Marketplace listing | One-click enterprise deployment |
| Mobile PWA | Push notifications for on-call engineers |
| Cross-tenant benchmarking | Anonymized MTTR comparisons across tenants |
| AI governance dashboard | Prompt version tracking, eval scores, cost per investigation |

---

## Deferred / Backlog Items

Items identified as valuable but not yet sequenced into a phase:

| Item | Context | Likely Phase |
|------|---------|-------------|
| Progressive rollout / canary analysis | Complement to `rollback_deployment()` | Phase 3–4 |
| SLO per-application alert window | `alert_suppression_window_minutes` configurable per service | Phase 1 |
| Application health score (Corvin Score) | Configurable weights and thresholds | Phase 2 |
| ADRs for major architectural decisions | No documented rationale currently exists | Phase 0 remaining |
| AI prompt evaluation framework | Regression testing for RCA quality | Phase 3 |

---

## Document Reference Map

| Topic | Document |
|-------|---------|
| Current status and active initiatives | [PROJECT_STATUS.md](../PROJECT_STATUS.md) |
| Productization work | [docs/PRODUCTIZATION_BACKLOG.md](PRODUCTIZATION_BACKLOG.md) |
| Productization audit | [docs/PRODUCTIZATION_ASSESSMENT.md](PRODUCTIZATION_ASSESSMENT.md) |
| Prompt architecture | [docs/PROMPT_ARCHITECTURE.md](PROMPT_ARCHITECTURE.md) |
| Technical debt | [docs/TECH_DEBT.md](TECH_DEBT.md) |
| Enterprise gaps | [docs/ENTERPRISE_READINESS.md](ENTERPRISE_READINESS.md) |
| SaaS strategy | [docs/SAAS_READINESS.md](SAAS_READINESS.md) |
| System architecture | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Code conventions | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Agent context | [AGENTS.md](../AGENTS.md) |

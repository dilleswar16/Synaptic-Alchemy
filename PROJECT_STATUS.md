# Corvin — Project Status

**Last Updated:** 2026-06-10  
**Current Phase:** Phase 1 — Productization & Genericization  
**Product Version:** V5.4 (feature-complete hackathon build)  
**Roadmap Authority:** [docs/ROADMAP.md](docs/ROADMAP.md)

This document is the persistent status tracker. Update it when any phase milestone, initiative, or blocker changes.

---

## Phase Summary

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| Phase 0 | Knowledge & Governance | Complete | Canonical docs created, debt registered, governance gaps identified |
| **Phase 1** | **Productization & Genericization** | **Active** | Audit complete; backlog defined; implementation not yet started |
| Phase 2 | Architecture Modernization | Planned | Async pipeline, OpenTelemetry, circuit breakers, API versioning |
| Phase 3 | Enterprise Foundation | Planned | Authentication (OIDC), RBAC, audit trail, secret management |
| Phase 4 | Multi-Tenant Foundation | Planned | `tenant_id`, RLS policies, per-tenant config/LLM/encryption |
| Phase 5 | SaaS Scale | Planned | Billing, tenant admin, usage metering, white-labeling |
| Phase 6 | Product Expansion | Planned | pgvector RAG, VS Code extension, Azure Marketplace |

---

## Current Phase — Phase 1 Detail

### Goal
Transform Corvin from a MetLife/CHAD-specific hackathon solution into a reusable product platform. After Phase 1, a different customer should be able to adopt Corvin through configuration only — no source-code changes.

### Phase 1 Productization Score (entry state)
**28% complete** — core investigation engine is generic; all surrounding assets are not.

### Phase 1 Milestones

| Milestone | Description | Status | Target |
|-----------|-------------|--------|--------|
| P1.A | Audit complete, backlog defined | **Done** | 2026-06-10 |
| P1.A2 | CHAD classification + template library created (PB-031, PB-032) | **Done** | 2026-06-10 |
| P1.B | Brand & asset genericization (PB-001, PB-017, PB-019) | Planned | — |
| P1.C | Knowledge base genericization (PB-002, PB-003, PB-007, PB-008) | Planned | — |
| P1.D | Demo data & test fixtures genericization (PB-005, PB-006, PB-016) | Planned | — |
| P1.E | Configuration externalization (PB-009 through PB-012) | Planned | — |
| P1.F | Connector onboarding hardening (PB-013, PB-014, PB-015) | Planned | — |
| P1.G | Prompt registry implementation (PB-021) | Planned | — |
| P1.H | Documentation genericization (PB-022, PB-025) | Planned | — |
| P1.I | Developer experience (PB-020, PB-023, PB-024) | Planned | — |

### Active Backlog Item
CONDITIONAL GO — Execution Readiness Review complete. Six corrections applied to backlog. Sprint 1 is cleared for implementation. See `docs/EXECUTION_READINESS_REVIEW.md`.

### Sprint 1 Execution Order (confirmed safe to begin)
1. **PB-004** — Remove Azure URL from `.env.example` (1 line, zero risk)
2. **PB-006** — Replace MetLife emails in test fixtures
3. **PB-002 + PB-003 + PB-032** — ATOMIC commit: relocate CHAD runbooks, rebuild catalog.json, finalize `knowledge/examples/chad/`
4. **PB-005 + test co-change** — ATOMIC commit: rename seed data + update `test_slice_ev1_connectors.py` assertions
5. **PB-017 + PB-001** — SAME PR: branding API endpoint + MetLife logo removal

### CHAD Classification Decision (2026-06-10)
CHAD assets fall into three categories: Customer Contamination (remove), Reference Example (relocate to `knowledge/examples/chad/`), Reusable Template (extracted to `knowledge/templates/`). No CHAD content is deleted — it is relocated or generalized. See `docs/CHAD_ASSET_CLASSIFICATION.md`.

### Known Blockers
- **TD-H3** (duplicate 0012_* Alembic migrations) blocks PB-010, PB-011, PB-015. Must be resolved before Sprint 2.
- PB-001 cannot merge without PB-017 in the same PR.
- PB-005 requires co-change with `test_slice_ev1_connectors.py`.

---

## Phase 0 — What Was Completed

Phase 0 was the governance and documentation consolidation effort (June 2026). It delivered:

**New canonical documents:**
- [README.md](README.md) — project entry point, quick start
- [ARCHITECTURE.md](ARCHITECTURE.md) — system architecture, module map, DB schema
- [CONTRIBUTING.md](CONTRIBUTING.md) — code conventions, testing patterns, PR standards
- [docs/ROADMAP.md](docs/ROADMAP.md) — full product roadmap
- [docs/TECH_DEBT.md](docs/TECH_DEBT.md) — technical debt register (Critical/High/Medium/Low)
- [docs/ENTERPRISE_READINESS.md](docs/ENTERPRISE_READINESS.md) — domain-by-domain enterprise gap analysis
- [docs/SAAS_READINESS.md](docs/SAAS_READINESS.md) — SaaS maturity assessment, migration strategy
- [docs/PRODUCTIZATION_ASSESSMENT.md](docs/PRODUCTIZATION_ASSESSMENT.md) — productization audit and strategy
- [docs/PRODUCTIZATION_BACKLOG.md](docs/PRODUCTIZATION_BACKLOG.md) — 30-item productization backlog
- [docs/PROMPT_ARCHITECTURE.md](docs/PROMPT_ARCHITECTURE.md) — prompt registry and versioning design
- [docs/archive/ARCHIVE_INDEX.md](docs/archive/ARCHIVE_INDEX.md) — index of archived documents

**Updated files:**
- [AGENTS.md](AGENTS.md) — pruned V2 build instructions, added enterprise and productization state
- [.github/copilot-instructions.md](.github/copilot-instructions.md) — updated to V5.4 enterprise focus

**Known Phase 0 cleanup remaining:**
- Original archived files still exist in root (`BUNDLE_MANIFEST.md`, `CORVIN_COMMAND_CENTER.md`, `architecture_review.md`, `implementation_plan.md`, `presenter-script.md`, `progress.md`) — tracked as PB-029
- TD-C3, TD-C4 documented but not yet remediated — tracked as PB-004, PB-030

---

## Platform Version State

### V5.4 — Complete (Current)

All hackathon and post-hackathon feature versions (V1 through V5.4) are complete and stable. Do not revisit.

**Key V5.4 capabilities:**
- Full investigation pipeline: Trigger → Enrich → RCA → Fix Strategy → Approve → Execute → PostMortem → Runbook Update
- AI Runbook Management (build, version, generate, apply)
- Corvin Command Center (ChatGPT-style agentic interface, 15 tools, SSE streaming)
- Multi-agent orchestration, chaos engine, causal chain, NL→KQL
- Teams ChatOps (approve/reject via adaptive cards)
- Predictive monitoring, SLO tracking, DORA dashboard
- ROI calculator, blast radius estimator, voice morning briefing
- Alert simulator, chaos experiments, war room channel
- 437+ tests

**Known V5.4 technical debt:** See [docs/TECH_DEBT.md](docs/TECH_DEBT.md) for full register.

---

## Critical Items (Unresolved)

These items are flagged Critical in the tech debt register. None are resolved.

| ID | Issue | Status | Notes |
|----|-------|--------|-------|
| TD-C1 | No authentication on any API endpoint | Unresolved | Phase 3 (Enterprise Foundation) |
| TD-C2 | `approved_by` accepted as unvalidated query string | Unresolved | Phase 3 |
| TD-C3 | Azure portal URL with tenant ID in `.env.example` | Unresolved | PB-004 — first sprint of Phase 1 |
| TD-C4 | Database files committed to repository | Unresolved | PB-030 — Phase 1 |

---

## Decision Log

Decisions that shape the current strategy. Record here so future agents and engineers don't relitigate.

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-10 | Phase 1 (Productization) before Phase 3 (Enterprise Foundation) | Authentication, RBAC, billing add no value if the platform is still CHAD-specific. Genericize first, then harden. |
| 2026-06-10 | Shared schema + RLS as SaaS multi-tenancy strategy | Best for 100–10,000 tenants. Schema-per-tenant rejected due to migration complexity. See `docs/SAAS_READINESS.md`. |
| 2026-06-10 | Demo topology → "Acme Retail Platform" (not CHAD) | CHAD represents MetLife IP. Generic demo must not imply customer relationship. |
| 2026-06-10 | Disk runbooks → generic only; customer runbooks → DB only | Disk files ship in container image; must be product-level content. Customer runbooks managed via Runbook Management UI. |
| 2026-06-10 | Prompt registry in `config/prompts/` YAML files | Prompts are configuration, not code. Enables versioning, customer override, and evaluation. |

---

## Document Ownership

| Document | Owner | Review Cadence |
|----------|-------|----------------|
| PROJECT_STATUS.md | Engineering Lead | Weekly during active phases |
| docs/ROADMAP.md | Product Lead + Engineering Lead | After each phase milestone |
| docs/PRODUCTIZATION_BACKLOG.md | Engineering Lead | Weekly during Phase 1 |
| docs/TECH_DEBT.md | Engineering Lead | Monthly |
| ARCHITECTURE.md | Principal Engineer | After each EV milestone |
| AGENTS.md | Engineering Lead | After each phase starts |
| docs/ENTERPRISE_READINESS.md | Security Architect | Quarterly |
| docs/SAAS_READINESS.md | SaaS Architect | Quarterly |

---

## For AI Agents Resuming Work

If you are an AI agent resuming work on Corvin, start here:

1. **Read this file** — understand current phase and status
2. **Read [AGENTS.md](AGENTS.md)** — active focus, conventions, what NOT to do
3. **Read [docs/ROADMAP.md](docs/ROADMAP.md)** — full phase sequence and current milestones
4. **Read [docs/PRODUCTIZATION_BACKLOG.md](docs/PRODUCTIZATION_BACKLOG.md)** — prioritized work items for Phase 1
5. **Read [docs/TECH_DEBT.md](docs/TECH_DEBT.md)** — known debt before modifying any existing code

**Do not** start authentication, multi-tenancy, billing, or SCIM work. Those are Phase 3–5.  
**Do** focus on the P0 and P1 items in `docs/PRODUCTIZATION_BACKLOG.md`.

The next action item is: **PB-001** (remove MetLife logo) → **PB-002** (remove CHAD runbooks) → **PB-003** (rebuild catalog.json) → **PB-004** (remove Azure tenant URL from .env.example).

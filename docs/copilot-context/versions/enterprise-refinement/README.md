# Corvin Enterprise Refinement

## Purpose

This folder is for the productization track that turns Corvin from a strong hackathon build into a sellable enterprise product.

The focus here is not more surface area for demos. The focus is:
- stable connector onboarding
- identity and access model
- tenant boundaries
- trust, audit, and operational control
- a clean admin-panel experience for customer setup

## Working Principle

Each refinement version should have its own folder so we can keep:
- the plan
- the implementation notes
- the architecture explanation
- the gap analysis
- the decision record
- the acceptance criteria

This keeps the work explainable and auditable instead of scattered across unrelated docs.

## Proposed Version Map

### EV1 — Connector Onboarding And Identity Model
This is the first and most important slice.

Goal:
- make connector configuration DB-backed
- make connector selection happen through the Application Panel
- define how credentials are resolved at runtime
- decide the default production identity pattern for Azure
- separate local dev, same-tenant Azure, and cross-tenant access
- cover all connector families already present in the workspace so the foundation does not need to be revisited later
- keep local development flexible while making Azure production deterministic

Why first:
- this is the decision point for the rest of the architecture
- it defines how customers onboard
- it defines how runtime integrations are loaded
- it influences RBAC and tenant boundaries

### EV2 — Trust Foundation
Goal:
- authentication
- authorization / RBAC
- audit trail
- tenant and workspace isolation
- secret handling and credential hardening

Why second:
- once identity and connector flow are fixed, the trust model can be locked around them

### EV3 — Incident Governance
Goal:
- severity model
- incident role model
- on-call and escalation mapping
- approval policy rules
- error-budget enforcement gate

### EV4 — Alert Quality And Change Correlation
Goal:
- suppression windows
- deduplication
- flapping detection
- change correlation
- recent changes panel in investigations

### EV5 — Safe Remediation
Goal:
- canary and progressive rollout support
- deterministic rollback policy
- post-execution validation gates
- approval-aware execution guards

### EV6 — Service Catalog And Ownership
Goal:
- service ownership model
- team/service mapping
- dependency graph as a first-class product concept
- connector and SLO scoping per application

### EV7 — Operational Reporting
Goal:
- toil tracking
- incident duration metrics
- manual-step reduction
- SLO trend reporting
- capacity and risk summaries
- audit-friendly exports

### EV8 — Platform Hardening
Goal:
- connector consistency between local and Azure
- test coverage for connectors, SLOs, validations, and AI flows
- remove demo-only paths from sellable flows
- deterministic configuration migration

## Doc Layout Per Version Folder

Each EV folder should eventually contain:
- `README.md` — what the version is trying to achieve
- `plan.md` — build order and rationale
- `implementation.md` — what was built and how it works
- `architecture.md` — design decisions and tradeoffs
- `gaps.md` — what remains open after the slice
- `acceptance.md` — how we know the slice is done

## Current Priority

Start with EV1.

That slice should answer:
- where connector config lives
- how credentials are stored
- which identity pattern each deployment mode uses
- how admin onboarding works in the UI
- how the runtime picks a connector at startup or request time
- which auth mode is active in local bootstrap versus Azure production

## Working Assumption For EV1

- same-tenant Azure should default to managed identity or workload identity
- local dev should continue to support env-based fallback and Azure CLI login
- service principal should be an explicit exception path, not the default assumption
- connector onboarding should cover every connector family already present in the repository

## Notes

- Env vars should remain available for local bootstrap and fallback.
- DB-backed connector config should be the primary customer-facing path.
- Managed identity should be the default Azure production path when Corvin runs inside a tenant.
- Cross-tenant access should be explicit, not implicit.
- The connector registry should be the only place that turns configuration into a live client.

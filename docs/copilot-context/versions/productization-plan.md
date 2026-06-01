# Corvin Productization Plan

## Purpose

This plan defines the technical build order for turning Corvin from a strong hackathon platform into a product that can be sold outside the current workspace.

This document only records the prioritized sequence. Detailed gap analysis and open decisions remain in:
- [docs/gaps.md](../../gaps.md)
- [docs/copilot-context/shared/12_open_decisions_and_assumptions.md](../shared/12_open_decisions_and_assumptions.md)

## Build Order

### 1. Connector Onboarding And Identity Model
Make connector configuration DB-backed, selectable, and safe across deployment modes.

- Application Panel as the source of truth for apps, services, and connectors
- Persist connector definitions in Postgres instead of relying on env-only wiring
- Keep env vars for local bootstrap and fallback, not as the primary customer config surface
- Resolve connector credentials at runtime through a registry layer
- Default same-tenant Azure deployments to managed identity or workload identity
- Support cross-tenant access only through an explicit onboarding path
- Separate read-only evidence identities from write/execution identities where possible
- Add connection test, active/inactive state, and last-tested metadata to every connector
- Make the UI the admin surface for adding, editing, testing, and disabling connectors

### 2. Trust Foundation
Build the minimum enterprise trust layer around the connector model before expanding features.

- Authentication
- Authorization / RBAC
- Audit trail for investigate, approve, execute, and config changes
- Tenant and workspace boundaries
- Secret handling and credential storage hardening

### 3. Incident Governance
Make Corvin behave like a controlled incident platform, not just an analyst.

- Severity classification
- Incident role model
- On-call and escalation mapping
- Approval policy rules
- Error-budget enforcement gate

### 4. Alert Quality And Change Correlation
Reduce noise before it reaches the investigation engine.

- Deduplication and suppression windows
- Flapping detection
- Alert quality scoring
- First-class deployment/change correlation
- Recent changes panel in investigations

### 5. Safe Remediation
Make execution safe enough for production use.

- Canary or progressive rollout support
- Deterministic rollback policy
- Post-execution validation gates
- Approval-aware execution guards
- Clear success / failure / rollback outcomes

### 6. Service Catalog And Ownership
Make the monitored system understandable across teams.

- Service ownership model
- Team / service mapping
- Dependency graph as a product primitive
- Connector and SLO scoping per application

### 7. Operational Reporting
Add the metrics leadership and operators will actually ask for.

- Toil tracking
- Incident duration and manual-step metrics
- SLO trend reporting
- Capacity and risk summaries
- Compliance export and audit-friendly reports

### 8. Platform Hardening
Stabilize the product before broad sale or pilot rollout.

- Local and remote connector consistency
- Test coverage around connectors, SLOs, validations, and AI flows
- Fix noisy or demo-only paths that should not ship broadly
- Make configuration migration deterministic and repeatable

## Recommended Sequence For The Next Iteration

1. Connector onboarding, DB-backed registry, and identity model
2. Authentication, RBAC, audit trail, tenant model
3. Error-budget enforcement and incident role model
4. Alert suppression, deduplication, and change correlation
5. Canary rollout and post-execution validation
6. Service catalog ownership and reporting
7. Product hardening and test stabilization

## Connector Architecture Notes

- Env-backed credentials should remain available for local development and bootstrap.
- DB-backed connectors should be the primary runtime source for customer-managed configuration.
- Managed identity should be the default Azure production path when Corvin is deployed inside a tenant.
- Cross-tenant access should be an explicit exception path with least-privilege permissions.
- The connector registry should be the only place that decides how a configured source becomes a live client.
- UI flow should be: application → service → connector → credentials → test → activate.
- The connector model should inform RBAC decisions, not follow them.
- Trust foundation should lock down the approved connector flow once the identity model is chosen.

## Notes

- The current feature set is strong enough for internal demos.
- The current missing pieces are mostly trust, governance, and operational control.
- Selling externally without those layers would be risky even if the feature list looks impressive.

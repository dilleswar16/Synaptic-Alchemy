# EV1 — Connector Onboarding And Identity Model

## Goal

Define the connector onboarding architecture first, because it decides how Corvin should authenticate, store connector details, and load runtime integrations.

## What This Slice Must Solve

- Application Panel is the source of truth for apps, services, and connectors
- connector config is stored in Postgres
- credentials are resolved through a registry layer at runtime
- local dev remains env-friendly
- Azure production uses managed identity or workload identity where possible
- cross-tenant access is handled as an explicit exception path
- the UI becomes the admin surface for onboarding and testing connectors

## Key Questions This Slice Must Answer

- What stays in `.env` and what moves to the database?
- Which connectors are read-only and which can execute actions?
- Which credential modes are allowed for each connector type?
- How does the registry choose between env, Key Vault, db-encrypted, and Azure identity?
- What is the default auth model for same-tenant Azure deployments?
- What is the onboarding flow for cross-tenant access?
- What minimum RBAC roles are required for each integration?

## Expected Outputs

- architecture decision record
- implementation plan
- database model updates
- API contract updates
- UI onboarding flow updates
- migration path from env-driven config to DB-driven config
- acceptance criteria for local dev, same-tenant Azure, and cross-tenant Azure

## Testing Direction

The EV1 test strategy should be slice-based, not end-to-end only.

See [test-slices.md](test-slices.md) for the planned regression coverage.

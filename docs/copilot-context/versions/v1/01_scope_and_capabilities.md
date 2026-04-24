# Corvin V1 Scope And Capabilities

## V1 Goal

V1 delivers a usable investigation product that can:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy

V1 does not execute fixes.

## V1 Required Surfaces

- REST API
- CLI
- web app
- Teams
- Azure alert ingestion

## V1 Required Evidence Sources

- Azure alert payloads
- Elastic logs
- Elastic application and AKS metrics
- Azure Log Analytics for APIM
- AKS context collection
- Azure Activity Log or equivalent change context when practical

## V1 Required Capabilities

1. Normalize Azure-triggered and manual requests into a shared investigation contract.
2. Enrich incidents with deterministic evidence before the main reasoning loop.
3. Run a controllable investigation engine.
4. Produce a structured RCA.
5. Produce a structured fix strategy.
6. Persist incidents, RCA outputs, and fix strategies in Postgres.
7. Expose those results through CLI, API, web app, and Teams.

## V1 Explicit Exclusions

- autonomous remediation,
- approval-gated execution,
- rollback execution,
- verification after execution,
- mandatory authentication,
- broad cross-incident automation beyond the initial scope.

## V1 Product Standard

V1 should already feel like a product, not a demo. That means:

- stable contracts,
- reusable configs,
- clear module boundaries,
- testable slices,
- usable operator surfaces.
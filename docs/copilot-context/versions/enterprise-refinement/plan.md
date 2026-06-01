# Enterprise Refinement Program Plan

## Program Goal

Turn Corvin into a sellable enterprise product by building the connector, identity, trust, and operational control layers in a deliberate sequence.

## Version Order

- EV1 — Connector Onboarding And Identity Model
- EV2 — Trust Foundation
- EV3 — Incident Governance
- EV4 — Alert Quality And Change Correlation
- EV5 — Safe Remediation
- EV6 — Service Catalog And Ownership
- EV7 — Operational Reporting
- EV8 — Platform Hardening

## EV1 First

EV1 must come first because it defines the runtime configuration model.

If the connector and identity model is not decided first, every later version inherits ambiguous assumptions about:
- how credentials are stored
- how Azure auth is resolved
- where config lives
- how customer onboarding works
- what the admin panel should own

## How To Work The Program

1. Write the EV1 plan and architecture first.
2. Capture implementation notes as the slice lands.
3. Record gaps immediately after each version.
4. Add acceptance criteria before considering the version done.
5. Keep the docs explainable for future agents and human reviewers.
6. Write slice-level test plans before implementation so regressions are caught early.

## Current Active Slice

EV1 is the active slice.

It should decide:
- connector scope
- identity strategy
- runtime registry behavior
- UI onboarding flow
- migration from env-driven config

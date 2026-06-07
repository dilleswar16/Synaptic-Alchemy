# EV1 — Connector Onboarding And Identity Model

## Objective

Build the connector and identity foundation that makes Corvin configurable through the UI and deployable in a real enterprise setting.

This version is the decision layer for:
- where connector config lives
- how credentials are resolved
- which identity pattern each deployment mode uses
- how onboarding works for same-tenant and cross-tenant users
- what the connector registry is allowed to create at runtime

## Why This Comes First

Connector onboarding is not just a form. It defines the product's runtime trust boundary.

If Corvin cannot safely answer "which connector should I use, how do I authenticate, and where does that config come from?" then every later feature is built on unstable assumptions.

This EV must therefore lock down the following before anything else:
- DB-backed connector storage
- runtime connector resolution
- managed identity as the preferred Azure production path
- a safe fallback model for local dev
- a clear exception path for cross-tenant access

## Build Sequence

### 1. Define the connector data model

- Persist connector metadata in Postgres
- Capture source type, display name, active state, test status, and last-tested time
- Persist credential mode separately from connector config
- Support the following credential modes:
  - `env_var`
  - `kv_reference`
  - `db_encrypted`

Connector families in EV1 should cover the full set that already exists in the workspace so we do not need to revisit the foundation later:
- Azure Monitor / Log Analytics
- Azure Activity
- Elastic
- AKS / Kubernetes evidence
- BYOA / generic HTTP
- outbound delivery connectors already present in the Application Panel

### 2. Define the runtime resolver

- Create a single registry layer that turns DB rows into live connector clients
- Resolve credentials only inside the registry
- Keep adapter construction out of UI code and out of route handlers
- Make the registry the only place allowed to instantiate live integration clients

### 3. Define deployment identity behavior

- Local dev continues to support env-based auth
- Same-tenant Azure deployment defaults to managed identity or workload identity
- Cross-tenant access remains an explicit exception path
- Avoid mixing all deployment modes into one ambiguous auth path
- Add an explicit auth-mode switch or precedence rule so local bootstrap stays easy but Azure production can be strict

### 4. Expose onboarding in the Application Panel

- Let the user create or update applications
- Let the user add services beneath the application
- Let the user add connectors beneath the service/application scope
- Let the user test connectors after configuration
- Store the chosen config in the DB once it is validated

### 5. Support migration from env-based config

- Provide a migration path from the current config files into the DB model
- Do not remove env support immediately
- Treat env as bootstrap/fallback, not the main customer-facing setup path
- Preserve behavior so the existing flows continue to work while the new DB-backed path is introduced

### 6. Lock down the runtime contract

- Evidence collection should read the selected connector config from the DB-backed model
- SLO snapshotting should use the same connector registry
- Validation and automation flows should consume the same identity model
- No hidden second config path should appear in the core services

## Key Design Decisions To Finalize In EV1

### Connector scope

Decide which connector families are in scope for EV1:
- all current connector families already present in the workspace
- future connectors can still be deferred, but no existing family should be omitted from the foundation

### Identity scope

Decide which identity patterns are officially supported in EV1:
- local developer login
- managed identity / workload identity
- service principal / app registration for exceptions only
- Key Vault as a secret source
- explicit auth-mode selection or precedence rules so the deployment mode is deterministic

### Runtime loading scope

Decide whether startup should:
- load all active connectors eagerly
- load connectors lazily on demand
- preload only the default application connector set

The recommended direction is to load lazily through the registry and only validate eagerly where startup health requires it.

## Risks To Watch

- confusing env-based bootstrap with customer-facing config
- leaking customer secrets into unrelated config files
- allowing multiple identity patterns without a clear precedence rule
- making the UI look complete while the backend still depends on hardcoded wiring
- failing local dev because production-only identity assumptions were introduced too early
- shipping a connector foundation that does not include one of the connector families already in the repo

## EV1 Exit Criteria

EV1 is done when:
- connector definitions live in Postgres
- the UI can create and test connectors
- the registry can resolve connector credentials cleanly
- same-tenant Azure deployments have a clear managed identity path
- cross-tenant access is documented and explicit
- env files are no longer the primary customer setup path
- the system has one obvious connector onboarding flow
- the connector families that already exist in the workspace are covered by the onboarding model
- local bootstrap remains simple without weakening the Azure production path

## Deliverables

- `README.md` — EV1 scope and purpose
- `plan.md` — build sequence and rationale
- `architecture.md` — connector and identity architecture
- `implementation.md` — what was changed and how it works
- `gaps.md` — remaining issues after EV1
- `acceptance.md` — how to verify EV1 is complete

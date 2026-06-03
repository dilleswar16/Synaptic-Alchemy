# EV1 — Test Slices

## Testing Goal

Each slice should be independently testable so we do not end up with a large hidden integration failure later.

EV1 should be treated as a product foundation slice, so tests must cover:
- DB persistence
- credential resolution
- registry behavior
- UI onboarding flows
- identity behavior by deployment mode
- migration from env-based config to DB-based config

## Test Slice Order

### Slice 1 — Connector Model Persistence

Verify that connector definitions can be created, stored, updated, and disabled in Postgres.

Tests should cover:
- application creation
- service creation
- connector creation
- connector update
- active/inactive toggling
- last-tested status persistence
- all connector families that already exist in the workspace can be represented by the model

### Slice 2 — Credential Resolution

Verify that the registry can resolve credentials from all allowed modes.

Tests should cover:
- `env_var` resolution
- `kv_reference` resolution
- `db_encrypted` resolution
- missing credential handling
- invalid reference handling
- explicit auth-mode precedence in local vs Azure deployment modes

### Slice 3 — Runtime Connector Instantiation

Verify that the registry turns DB rows into live connector objects correctly.

Tests should cover:
- source type to class mapping
- unknown connector type handling
- config JSON passed through correctly
- connector construction failure behavior

### Slice 4 — Identity Mode Behavior

Verify that the system behaves correctly by deployment mode.

Tests should cover:
- local dev uses flexible auth fallback
- same-tenant Azure prefers managed identity or workload identity
- cross-tenant mode is explicit and documented
- identity precedence is deterministic
- service principal path only activates when explicitly selected

### Slice 5 — Connector Test Endpoint

Verify that the UI-triggered connector test path works.

Tests should cover:
- successful connection test
- failed connection test
- test status update
- test timestamp update
- user-facing error message propagation

### Slice 6 — Migration Path

Verify that existing env-based config can be migrated into the DB model.

Tests should cover:
- bootstrap from config files
- idempotency of migration
- no duplicate connector rows
- fallback behavior if some config values are missing
- preservation of existing behavior while introducing the DB-backed path

### Slice 7 — UI Onboarding Flow

Verify that the Application Panel supports the onboarding flow end to end.

Tests should cover:
- create application
- add service
- add connector
- edit connector
- test connector
- disable connector
- reload application detail state correctly
- visible auth mode / credential mode for the selected connector

## Regression Risks To Watch

- connector config stored in DB but runtime still reading env
- managed identity working in Azure but local dev breaking
- UI showing a saved connector that the registry cannot actually instantiate
- cross-tenant access being silently treated like same-tenant
- migration creating duplicate or partially wired connectors

## Minimum Acceptance For Test Coverage

EV1 should not be considered stable unless every slice above has at least one isolated test or validation check.

In addition, every connector family already present in the workspace should have at least one path covered by the test plan, even if the family shares the same registry pattern.

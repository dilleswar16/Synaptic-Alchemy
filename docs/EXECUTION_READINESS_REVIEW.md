# Corvin — Execution Readiness Review

**Date:** 2026-06-10  
**Phase:** Pre-Implementation Gate — Phase 1 Productization  
**Status:** CONDITIONAL GO — see required corrections before sprint begins

---

## Executive Summary

The productization strategy is technically sound. The approach will not require future redesign. However, **six corrections are required before implementation begins** — two of them are significant enough to change the sprint execution order.

The most important finding: **PB-007 and PB-008 are already complete** — `RunbookRow` and `KnowledgeBaseRow` both already have `application_id` in the schema. Additionally, **`demoAlerts.ts` is already parameterized** — PB-016 was written against incorrect assumptions.

---

## Review Area 1 — P0/P1 Backlog Validation

---

### PB-001 — Delete MetLife Logo

**Breaking Change Risk: Low**  
No code references the logo file at runtime. The frontend renders it via `<img src>` tag. Removing it causes a broken image, not a crash.

**Migration Risk: None**  
File deletion. No DB migration. No schema change.

**Rollback Strategy**  
`git checkout HEAD -- apps/web/public/metlife-logo.svg`. Zero risk.

**Testing Strategy**  
No tests reference the logo. Visual regression check needed on the frontend nav/header.

**Future Phase Compatibility**  
PB-017 (branding API) introduces `GET /config/branding`. Once that exists, the frontend should load the logo URL from the API. PB-001 without PB-017 leaves the frontend with no logo at all.

**⚠️ Sequencing Constraint:** PB-017 must be implemented first, or PB-001 and PB-017 must ship in the same PR. Do not delete the logo without having the branding API available to provide a replacement.

**Verdict: Safe — with sequencing constraint**

---

### PB-002 — Relocate CHAD Runbooks

**Breaking Change Risk: Medium**  
`catalog.json` currently contains file path references like `"file": "runbooks/chad-api-spec.md"`. After `git mv`, those paths become broken. Any investigation that triggers the catalog matcher between PB-002 completion and PB-003 completion will fail to load the runbook (the file won't be found at the path in catalog.json). The fallback behavior in `knowledge_loader.py` gracefully handles missing files — the runbook simply isn't injected rather than throwing an exception.

**Migration Risk: None**  
No DB migration. Disk files only.

**Rollback Strategy**  
`git mv knowledge/examples/chad/runbooks/* knowledge/runbooks/` + restore catalog.json from git. Clean and reversible.

**Testing Strategy**  
`tests/slices/test_slice5_knowledge_injection.py` creates a temp directory with its own catalog.json for testing — it does not use the real `knowledge/runbooks/catalog.json`. No test breakage expected from moving files. Verify by running this test suite after execution.

`tests/slices/test_slice_v39_enterprise_polish.py` also creates its own temp catalog. Unaffected.

**⚠️ Atomic Dependency:** PB-002 and PB-003 MUST execute in the same commit. The window where catalog.json has broken file references must be zero.

**Future Phase Compatibility**  
`KnowledgeLoader` loads DB runbooks first, disk second. Phase 4 multi-tenancy adds `tenant_id` to RunbookRow — generic disk runbooks are unaffected by this.

**Verdict: Safe — must be atomic with PB-003**

---

### PB-003 — Rebuild catalog.json

**Breaking Change Risk: Low**  
The two generic entries (`aks-crashloop`, `apim-5xx`) are kept. CHAD entries are removed. Any investigation that previously matched CHAD keywords will no longer receive CHAD runbooks — this is the desired behavior.

**Migration Risk: None**

**Rollback Strategy**  
`git checkout HEAD -- knowledge/runbooks/catalog.json`. The CHAD entries still exist in `knowledge/examples/chad/catalog_chad.json` for reference.

**Testing Strategy**  
`test_slice5_knowledge_injection.py` uses a temp catalog — will not be affected. Run the slice test after rebuilding to confirm the matcher still works on the generic entries.

**Future Phase Compatibility**  
Safe. When Phase 4 adds tenant-scoped DB runbooks as the primary path, `catalog.json` becomes a fallback for generic/starter content only. The current architecture supports this without changes.

**Verdict: Safe — must be atomic with PB-002**

---

### PB-004 — Remove Azure Tenant URL from .env.example

**Breaking Change Risk: None**  
Documentation file only. No code reads `.env.example` at runtime.

**Migration Risk: None**

**Rollback Strategy**  
`git checkout HEAD -- .env.example`. No consequences.

**Testing Strategy**  
No tests reference `.env.example`.

**Future Phase Compatibility**  
N/A — documentation cleanup.

**Verdict: Safe — lowest risk item in the backlog, do this first**

---

### PB-005 — Rename CHAD Services in seed_data.yaml

**Breaking Change Risk: HIGH**

`apps/api/seed_demo.py` is called from `test_slice_ev1_connectors.py` (line 20: `from apps.api.seed_demo import ensure_demo_data`). That test has these hardcoded assertions that will fail after renaming:

```python
assert set(services) == {"fundapis", "fundsso", "partnerapis"}          # WILL FAIL
assert services["fundapis"].k8s_app_label == "chad-fundapis"            # WILL FAIL
```

`tests/adapters/test_ado_wiki_adapter.py` uses `service="fundsso"` as a default argument (line 31). This is a fixture default, not a seed dependency — it will continue working after rename. No change needed.

`tests/slices/test_slice_v2_5_features.py` uses `service="partnerapis"` as a test value (line 94). This is a locally constructed test object, not seeded data. Will continue working.

`tests/slices/test_slice_apim_analytics_errors.py` uses `"fundapis"` as an APIM filter value. Local test object. Will continue working.

**Migration Risk: Medium**  
`seed_demo.py` idempotency guard is `filter_by(name="CHAD")`. After rename, the guard checks for `"Acme Retail"`. Developer databases seeded with CHAD will not be re-seeded automatically — existing CHAD rows remain. Developers must either drop and recreate the DB or run `seed_demo.py --reset`. Document this clearly in the PR.

**Rollback Strategy**  
`git checkout HEAD -- config/demo/seed_data.yaml` + `git checkout HEAD` on the test files that were updated alongside. Clean rollback.

**Testing Strategy**  
`test_slice_ev1_connectors.py` MUST be updated in the same commit as seed_data.yaml. Update:
- `assert set(services) == {"fundapis", "fundsso", "partnerapis"}` → `{"checkout-api", "auth-service", "partner-api"}`
- `assert services["fundapis"].k8s_app_label == "chad-fundapis"` → use the new service names
- `CHAD_LOG_ANALYTICS_WORKSPACE_ID` env var reference (line 144) — review if still needed after rename

**Future Phase Compatibility**  
Safe and required. Phase 4 multi-tenant seed will need to produce tenant-scoped demo data — the Acme Retail topology is a better starting point than CHAD.

**⚠️ Mandatory co-change:** `test_slice_ev1_connectors.py` must be updated in the same commit. This is a breaking change if separated.

**Verdict: Safe — mandatory co-change with test fixtures**

---

### PB-006 — Replace MetLife Emails in Tests

**Breaking Change Risk: Low**  
Test assertions change, but the logic being tested is unchanged. The email addresses are test fixture values, not production configuration.

**Migration Risk: None**

**Rollback Strategy**  
`git checkout HEAD` on the test files.

**Testing Strategy**  
Run the affected test files after change. Assertions should pass with the new values.

**Future Phase Compatibility**  
Safe. Phase 3 (auth) will introduce real identity in tests — using generic `sre@example.com` is the correct foundation.

**Verdict: Safe**

---

### PB-007 — Add application_id to RunbookRow

**⚠️ ALREADY COMPLETE — backlog item is invalid**

`RunbookRow` in `corvin/storage/models.py` already has:
```python
application_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("applications.id"), nullable=False, index=True
)
```

The column exists, is NOT NULL, and is already indexed. No migration needed.

**Semantic note:** The original plan proposed `nullable=True` where NULL = generic runbook. The current schema uses NOT NULL — generic runbooks stay on disk (catalog.json), application-specific runbooks go in DB. This is the correct architecture for the current single-tenant design. The null-for-generic model would be needed in Phase 4, not Phase 1.

**Action required:** Mark PB-007 as Completed in the backlog. Remove from sprint planning.

**Verdict: Already Complete**

---

### PB-008 — Add application_id to KnowledgeBaseRow

**⚠️ ALREADY COMPLETE — backlog item is invalid**

`KnowledgeBaseRow` already has:
```python
application_id: Mapped[str] = mapped_column(
    String(36), ForeignKey("applications.id"), nullable=False, index=True
)
```

Same analysis as PB-007.

**Action required:** Mark PB-008 as Completed in the backlog.

**Verdict: Already Complete**

---

### PB-009 — Rename GBP-Specific Config Keys

**Breaking Change Risk: Medium**

`tests/slices/test_slice_v35_features.py` contains:
- Line 60: `"blast_radius_currency": "GBP"` — in the test's policy dict. This will still work because we're keeping the key name `blast_radius_currency` (only renaming `engineer_hourly_rate_gbp` → `engineer_hourly_rate`).
- Line 119: `assert result.currency == "GBP"` — This test creates a policy dict with `"blast_radius_currency": "GBP"`, so after the rename the test still passes IF the assertion reads `result.currency` which comes from the policy value, not hardcoded in code.

Actually the test constructs its own policy dict with `"blast_radius_currency": "GBP"` — so as long as the code still reads that key, the assertion will still pass. The test does not use the global config file.

**Only `engineer_hourly_rate_gbp` → `engineer_hourly_rate` is a real key rename.** Tests may reference this key directly. Search confirms `test_slice_v35_features.py` doesn't reference `engineer_hourly_rate_gbp` directly — it uses `blast_radius_currency` and `roi_currency`.

**Migration Risk: Low**  
Config file change + code change in `roi.py:38`. Existing deployments with the old key name will fall back to the hardcoded default (120). This is acceptable behavior during transition.

**Rollback Strategy**  
Revert `config/policies/investigation.yaml` and `corvin/strategy/roi.py`. Clean.

**Testing Strategy**  
Run `test_slice_v35_features.py` and any ROI-related tests after change.

**Future Phase Compatibility**  
Required for Phase 4 where `engineer_hourly_rate` lives in per-tenant config, not a global policy file.

**Verdict: Safe — lower risk than originally assessed**

---

### PB-010 — Externalize Currency/Locale/Voice to Application Config

**Breaking Change Risk: Medium**  
Requires Alembic migration to add columns to `ApplicationEnvironmentRow`.

**⚠️ Migration Blocker:** The Alembic migration directory has three conflicting `0012_*` files (TD-H3). Alembic cannot deterministically determine the migration head when there are version conflicts. Any new migration added before resolving TD-H3 may fail to apply cleanly on a fresh database.

**Migration Risk: High** (due to TD-H3, not due to the change itself)

**Rollback Strategy**  
Alembic `downgrade` to remove the new columns. Clean if migration applies correctly.

**Testing Strategy**  
Tests creating `ApplicationEnvironmentRow` need to handle new nullable columns. Existing tests will continue to work since columns are nullable (NULL = use global policy).

**Future Phase Compatibility**  
Required for Phase 4 per-tenant locale/currency. The column design here directly feeds into Phase 4's tenant config.

**⚠️ Prerequisite:** TD-H3 (fix duplicate 0012_* migrations) must be resolved before any new migrations are added. This is a separate task that should be done before the PB-010/011/015 sprint.

**Verdict: Conditional — requires TD-H3 resolution first**

---

### PB-011 — Externalize Blast Radius Metrics

Same analysis as PB-010. Requires Alembic migration. TD-H3 must be resolved first.

**Verdict: Conditional — requires TD-H3 resolution first**

---

### PB-012 — Externalize SLA Targets

**Breaking Change Risk: Low**  
`SloConfigRow` already stores per-application SLA targets. The change is to read from `SloConfigRow` instead of global policy. No schema change needed.

**Migration Risk: None**  
Code change only in the SLA evaluation logic.

**Verdict: Safe — no migration required**

---

### PB-013 — Add Connection Test Endpoint

**Breaking Change Risk: None**  
New endpoint. Existing endpoints unchanged.

**Migration Risk: None**  
No schema change.

**Testing Strategy**  
New test needed in `tests/slices/` following existing slice test patterns. Each adapter needs a `test_connection()` method — this should be added as an abstract method to the base adapter interface.

**Future Phase Compatibility**  
Safe. Phase 3 adds auth to all routes — this endpoint will be protected like all others.

**Verdict: Safe**

---

### PB-014 — Add Evidence Preview Endpoint

**Breaking Change Risk: None**  
New endpoint.

**Future Phase Compatibility**  
Safe. In Phase 4, the endpoint will scope evidence queries to the authenticated tenant's connectors.

**Verdict: Safe**

---

### PB-015 — Add Per-Application Toolset Profile

**Breaking Change Risk: Medium**  
Requires Alembic migration to add `toolset_profile JSONB` to `ApplicationRow`.

Same TD-H3 blocker applies.

**Verdict: Conditional — requires TD-H3 resolution first**

---

### PB-016 — Remove demoAlerts.ts from Frontend Bundle

**⚠️ BACKLOG ITEM BASED ON INCORRECT ASSUMPTIONS — NEEDS REASSESSMENT**

`apps/web/src/data/demoAlerts.ts` is **already fully parameterized**. Review of the actual file shows:
- Service names are injected at runtime (not hardcoded)
- Falls back to `service-a`, `service-b`, `service-c` if <3 services provided
- No CHAD references, no MetLife references
- The file is already product-ready

**The original concern was that demo data is hardcoded in the frontend.** This was true of the scenario structure, but the file already reads service names dynamically from the component's props/context.

**Action required:** Investigate what `demoAlerts.ts` actually exports and how it's used before deciding whether to remove it. It may already meet the productization goal. If the scenario *descriptions* (not service names) are hardcoded, a targeted edit is more appropriate than file removal.

**Verdict: Reassess — do not remove before verifying current behavior**

---

### PB-017 — Implement Branding API

**Breaking Change Risk: None**  
New endpoint. No existing behavior changed.

**Migration Risk: None**  
Reads from env vars — no DB required for Phase 1.

**⚠️ Sequencing:** Must be implemented before PB-001 (logo deletion). Ship them together.

**Verdict: Safe — must precede PB-001**

---

## Review Area 2 — Template & Knowledge Architecture Validation

### `knowledge/templates/`

**Is this the correct location?**  
Yes, with a caveat. Templates are co-located with the runbooks they document, which aids discoverability. The location does not conflict with the `KnowledgeLoader` — that class only reads `knowledge/runbooks/catalog.json` and whatever it references. `knowledge/templates/` is invisible to all runtime code.

**Risk:** A future developer might accidentally add a template to `catalog.json`, causing template content to be injected into LLM prompts. Mitigation: `knowledge/templates/README.md` explicitly states "templates are for human reference; do not register them in catalog.json."

**Phase 4 compatibility:** In Phase 4, the runbook system becomes tenant-scoped and API-driven. Templates should eventually be served via `GET /templates/runbooks` so the UI can guide customers during onboarding. The current disk layout is a sensible interim — it doesn't prevent migration to API-served templates later.

**Decision: Keep at current location**

---

### `knowledge/examples/chad/`

**Is this the correct location?**  
Yes. Examples are not documentation (they don't belong in `docs/`) and not active knowledge (they don't belong in `knowledge/runbooks/`). The `examples/` subdirectory under `knowledge/` is semantically correct — it's example knowledge content.

**Risk:** None from a code perspective. The loader ignores this directory.

**Phase 4 compatibility:** In Phase 4, customer-specific runbooks live in the DB scoped by `tenant_id`. The examples directory becomes a starter kit library. `knowledge/examples/chad/` could eventually be accessible via `GET /admin/starter-kits/chad` — the file structure supports this.

**Decision: Keep at current location**

---

### Does the overall knowledge architecture support future requirements?

| Requirement | Support | Notes |
|-------------|---------|-------|
| New customer onboarding | Partial | Templates exist; no UI wizard yet (Phase 1 backlog) |
| New application onboarding | Yes | ApplicationRow + RunbookRow design supports this |
| New environment onboarding | Yes | ApplicationEnvironmentRow |
| New connector onboarding | Partial | LogSourceRow exists; no connection test yet (PB-013) |
| Multi-tenancy (Phase 4) | Yes — designed for it | RunbookRow has application_id; adding tenant_id is additive |
| White-labeling (Phase 5) | Partially | Branding API (PB-017) is the foundation |

No redesign required for Phase 2–5 compatibility.

---

## Review Area 3 — Existing Code Compatibility

**Can the repository function today without modification?**

**Yes — with one observation.**

The new directories `knowledge/templates/` and `knowledge/examples/chad/` are inert from a code perspective. Nothing loads from them. Their presence does not affect any runtime behavior.

The `knowledge/runbooks/catalog.json` still has its full CHAD entry set. CHAD runbooks are still on disk. The system functions identically to before the planning work.

**Hardcoded path dependencies identified:**

| Code Location | Path Assumption | Impact |
|--------------|----------------|--------|
| `corvin/core/knowledge_loader.py:110` | `knowledge/runbooks/catalog.json` | Hardcoded — if catalog.json is moved, loader breaks. Do not move catalog.json. |
| `corvin/core/knowledge_loader.py:296` | `knowledge/runbooks/<service_name>.md` | Auto-generated runbook filenames — only affects `append_runbook_step()` output. |
| `apps/api/seed_demo.py:35` | `config/demo/seed_data.yaml` | Hardcoded path. Do not rename seed_data.yaml without updating this line. |
| `tests/slices/test_slice5_knowledge_injection.py:92` | `"runbooks_path": "knowledge/runbooks"` | Test config — only affects test execution. |

**No code modifications are needed before implementation begins.** The repository can run in its current state. Modifications happen during implementation.

---

## Review Area 4 — Knowledge System Design Validation

The architecture as designed is correct. The following confirms it supports all required scenarios:

**Onboarding a new customer:**
1. Customer installs Corvin, sets env vars
2. Creates Application via UI
3. Uploads runbooks via Runbook Management — stored in `RunbookRow` with `application_id`
4. `KnowledgeLoader` returns these runbooks for all investigations on that application
5. Generic disk runbooks (`aks-crashloop.md`, `apim-5xx.md`) also inject when keywords match
6. No code changes required ✓

**Onboarding a new application (within existing customer):**
Same as above — create ApplicationRow, upload runbooks, done ✓

**Future multi-tenancy (Phase 4):**
`RunbookRow.application_id` already provides application scoping. Adding `tenant_id` is additive — `WHERE tenant_id = $1 AND application_id = $2`. The `KnowledgeLoader` query method will need a `tenant_id` parameter added, but its structure supports this without redesign ✓

**One design gap to note:**  
The disk-based generic runbooks (`aks-crashloop.md`, `apim-5xx.md`) are globally injected for all customers in all tenants. In Phase 4, a tenant may not want generic runbooks injected. The correct solution (for Phase 4) is to seed these generic runbooks as `RunbookRow` entries with `application_id = NULL` and `tenant_id = NULL` — a "product-level" runbook tier. This requires the nullable application_id change originally planned for PB-007, but deferred to Phase 4 when multi-tenancy is implemented.

For Phase 1 (single tenant), the current architecture is correct as-is.

---

## Review Area 5 — Backlog Quality Challenge

**PB-001** — Safe. Proceed.

**PB-002** — Revised direction (move, not delete) is correct. The atomicity constraint with PB-003 is critical. Proceed with constraint.

**PB-003** — Correct. Proceed.

**PB-004** — Correct. Do first. This should have been done before the previous planning sessions.

**PB-005** — Correct direction (rename, not rewrite). High risk from test coupling. Conditional proceed — mandatory test co-change.

**PB-006** — Correct. Proceed.

**PB-007** — ⚠️ **INVALID** — column already exists. Mark as Complete. Remove from sprint.

**PB-008** — ⚠️ **INVALID** — column already exists. Mark as Complete. Remove from sprint.

**PB-009** — Correct. Lower risk than classified. Proceed.

**PB-010** — ⚠️ **BLOCKED** by TD-H3 (duplicate 0012_* migrations). Do not implement until TD-H3 is resolved.

**PB-011** — ⚠️ **BLOCKED** by TD-H3. Do not implement until TD-H3 is resolved.

**PB-012** — Correct. No migration needed. Proceed early.

**PB-013** — Correct. Proceed when P0 items are done.

**PB-014** — Correct. Proceed.

**PB-015** — ⚠️ **BLOCKED** by TD-H3. Do not implement until TD-H3 is resolved.

**PB-016** — ⚠️ **REASSESS** — `demoAlerts.ts` is already parameterized. Verify before removing.

**PB-017** — Correct. Must precede PB-001.

**PB-021** (Prompt registry) — Correct direction. The architecture design is sound. The `config/prompts/` YAML approach does not conflict with any existing code. However, there is a subtlety: the prompt registry should be a **read-once-at-startup** singleton, not a per-request file read. Confirm the `PromptRegistry` design in `docs/PROMPT_ARCHITECTURE.md` uses `@lru_cache` or equivalent.

**PB-031** — Complete (template library created). Mark as done.

**PB-032** — In progress (README created, files not moved). Depends on PB-002 completion.

---

## Required Corrections Before Sprint Begins

These corrections must be made to the planning documents before implementation starts:

### Correction 1 — Mark PB-007 and PB-008 as Complete

`RunbookRow.application_id` and `KnowledgeBaseRow.application_id` already exist in the schema as NOT NULL columns. Update `docs/PRODUCTIZATION_BACKLOG.md` to mark both as `Completed — already implemented in V5.4 schema`.

### Correction 2 — Revise PB-016 Scope

`apps/web/src/data/demoAlerts.ts` is already parameterized. PB-016 should be revised from "remove the file" to "verify behavior and update if scenario descriptions are CHAD-specific". Lower priority and smaller scope than currently described.

### Correction 3 — Add TD-H3 as a Sprint Prerequisite

Add a new item to the sprint plan: **Fix TD-H3 (duplicate 0012_* Alembic migrations)** before any sprint that includes PB-010, PB-011, or PB-015. This is not itself a productization item, but it gates three P1 items that require new migrations.

### Correction 4 — Enforce PB-002 + PB-003 Atomic Execution

Document in the backlog that PB-002 and PB-003 must be in the same git commit. The window between file moves and catalog.json rebuild must be zero.

### Correction 5 — Enforce PB-017 → PB-001 Ordering

Document in the backlog that PB-001 (delete logo) cannot merge without PB-017 (branding API) in the same PR. Otherwise, the frontend header will render no logo.

### Correction 6 — Enforce PB-005 Test Co-Change

Document in the backlog that `test_slice_ev1_connectors.py` must be updated in the same commit as `config/demo/seed_data.yaml`. The test currently asserts specific CHAD service names that will fail after rename.

---

## Final Recommendation

### CONDITIONAL GO

The productization strategy is architecturally sound and will not require redesign in Phase 2–5. The knowledge system design is correct. The template library is in the right place. The domain model already supports the plan.

Implementation can begin immediately after these corrections are applied to the planning documents (30 minutes of doc updates).

---

## Recommended Sprint 1 Execution Order

Execute in this exact sequence to minimize risk:

**Commit 1 — Zero-risk quick wins** (no code changes, no tests affected)
1. PB-004: Remove Azure tenant URL from `.env.example` (1 line)
2. PB-006: Replace MetLife emails in test fixtures (4 lines across 2 test files)

**Commit 2 — Knowledge base cleanup (atomic)**
3. PB-002: `git mv knowledge/runbooks/chad-*.md knowledge/examples/chad/runbooks/`
4. PB-003: Rebuild `knowledge/runbooks/catalog.json` (2 entries: aks-crashloop + apim-5xx only)
5. PB-032: Finalize `knowledge/examples/chad/` — copy `config/demo/seed_data.yaml` to `knowledge/examples/chad/seed_data_chad.yaml`, create `knowledge/examples/chad/catalog_chad.json`

_(These three are one atomic operation — commit them together)_

**Commit 3 — Demo data rename + test co-change**
6. PB-005: Rename CHAD → Acme Retail in `config/demo/seed_data.yaml` (~15 substitutions)
7. Update `test_slice_ev1_connectors.py` assertions to match new service names

_(These two are one atomic operation — commit them together)_

**Commit 4 — Brand & frontend**
8. PB-017: Add `GET /config/branding` endpoint (reads env vars, returns branding config)
9. PB-001: Delete `apps/web/public/metlife-logo.svg`
10. Update frontend to load logo from branding API

_(Ship as one PR — logo removal is safe only with the API present)_

**Defer to Sprint 2 (after TD-H3 fix)**
- Fix TD-H3 (renumber conflicting 0012_* Alembic migrations)
- PB-010: Externalize currency/locale/voice (requires migration)
- PB-011: Externalize blast radius metrics (requires migration)
- PB-015: Per-application toolset profile (requires migration)

**Sprint 2 can also include (no migration required)**
- PB-012: Externalize SLA targets
- PB-009: Rename GBP config keys
- PB-013: Connection test endpoint
- PB-014: Evidence preview endpoint

---

## Corrections to Backlog Required Now

| Item | Current Status | Correct Status | Action |
|------|---------------|----------------|--------|
| PB-007 | Planned | Completed — schema already has application_id | Update backlog |
| PB-008 | Planned | Completed — schema already has application_id | Update backlog |
| PB-016 | Planned | Needs investigation | Revise scope before implementing |
| PB-010, PB-011, PB-015 | Planned | Blocked — TD-H3 | Add prerequisite note |
| PB-001 | Planned | Conditional — requires PB-017 first | Add ordering constraint |
| PB-005 | Planned | Conditional — requires test co-change | Add co-change requirement |
| PB-002/003 | Planned | Atomic | Add atomicity constraint |

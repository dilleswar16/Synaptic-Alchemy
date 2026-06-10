# Corvin — Productization Backlog

**Last Updated:** 2026-06-10  
**Phase:** Phase 1 — Productization & Genericization  
**Owner:** Engineering Lead  
**Review Cadence:** Weekly during Phase 1

This backlog tracks every change required to make Corvin deployable by a different customer without source-code modifications. Items are ordered by priority within each tier.

---

## Priority Key

| Priority | Definition |
|----------|-----------|
| **P0** | Hard blocker — platform cannot be deployed for a second customer with this present |
| **P1** | High value — required for customer confidence and clean demo/evaluation |
| **P2** | Configuration quality — required for the platform to be fully self-service |
| **P3** | Polish — improves experience but does not block adoption |

## Effort Key

| Effort | Definition |
|--------|-----------|
| **XS** | < 2 hours |
| **S** | Half-day |
| **M** | 1–2 days |
| **L** | 3–5 days |
| **XL** | 1–2 weeks |

## Status Key

`Planned` → `Ready` → `In Progress` → `Completed` / `Deferred` / `Blocked`

---

## P0 — Hard Blockers

### PB-001 — Remove MetLife logo from frontend public assets

**⚠️ Ordering constraint: PB-017 (branding API) must be implemented in the same PR or before this item. Removing the logo without a replacement causes the frontend header to render no logo at all.**

| Field | Value |
|-------|-------|
| **ID** | PB-001 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | `apps/web/public/metlife-logo.svg` |
| **Impact** | Every customer deployment displays MetLife branding. Trademark risk. Blocks any customer demo. |
| **Recommended Solution** | Delete the file. Replace with a generic Corvin logo placeholder. Implement `GET /config/branding` API (see PB-017) to make the logo configurable at runtime. |
| **Dependencies** | PB-017 (branding API) should be done in the same sprint |
| **Migration** | Archive the SVG to `docs/archive/customer-examples/chad/` |

---

### PB-002 — Relocate CHAD runbooks and extract template library

**Revised 2026-06-10** — See `docs/CHAD_ASSET_CLASSIFICATION.md`. Original "delete" decision replaced with "move + extract". CHAD runbooks contain valuable structural patterns that benefit all customers.

| Field | Value |
|-------|-------|
| **ID** | PB-002 |
| **Priority** | P0 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `knowledge/runbooks/chad-*.md` |
| **Impact** | CHAD runbook content is injected into LLM prompts whenever keyword matching fires. A different customer gets MetLife-specific debugging steps. |
| **Recommended Solution** | **Do not delete — relocate and extract.** (1) Move all `chad-*.md` files to `knowledge/examples/chad/runbooks/`. (2) Templates already created in `knowledge/templates/runbooks/` from this content. (3) Update catalog.json to remove CHAD entries (PB-003). |
| **Sub-tasks** | PB-002a: `git mv knowledge/runbooks/chad-*.md knowledge/examples/chad/runbooks/` · PB-002b: Template library already created (`knowledge/templates/`) · PB-002c: Create `knowledge/examples/chad/catalog_chad.json` from CHAD catalog entries |
| **Dependencies** | PB-003 (catalog.json rebuild) must follow |
| **Migration** | No DB migration — disk runbooks only |

---

### PB-003 — Rebuild knowledge/runbooks/catalog.json with only generic entries

| Field | Value |
|-------|-------|
| **ID** | PB-003 |
| **Priority** | P0 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `knowledge/runbooks/catalog.json` |
| **Impact** | Current catalog.json has 200+ lines of CHAD-specific keywords. Any alert text matching CHAD service names, error codes, or Java class names triggers CHAD runbook injection. |
| **Recommended Solution** | Rebuild catalog.json with two entries only: AKS crashloop and APIM 5xx runbooks, with generic keyword sets (e.g., `CrashLoopBackOff`, `OOMKilled`, `5xx`, `timeout`). All other runbooks should be loaded from the DB (`RunbookRow`) with application scoping. |
| **Dependencies** | PB-002 must complete first |
| **Migration** | None required |

---

### PB-004 — Remove Azure subscription tenant ID from .env.example

| Field | Value |
|-------|-------|
| **ID** | PB-004 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | `.env.example:78` |
| **Impact** | TD-C3 — exposes live Azure tenant ID `457bc2c0-610b-4bf1-b615-b8621ee51c31` in version-controlled file. Reconnaissance attack surface. |
| **Recommended Solution** | Remove the URL. Replace with `TEAMS_TENANT_ID=<your-azure-tenant-id>`. |
| **Dependencies** | None |
| **Migration** | None required |

---

### PB-005 — Rename CHAD service names in seed_data.yaml (preserve all content)

**Revised 2026-06-10** — See `docs/CHAD_ASSET_CLASSIFICATION.md`. Original "replace content" decision changed to "rename only". All 6 embedded runbooks and all 8 simulator presets describe universal failure patterns — only the service names are CHAD-specific. Total change: ~15 string substitutions.

| Field | Value |
|-------|-------|
| **ID** | PB-005 |
| **Priority** | P0 |
| **Effort** | XS (was M) |
| **Status** | Planned |
| **Location** | `config/demo/seed_data.yaml` |
| **Impact** | Demo shows MetLife application topology. `fundapis`, `fundsso`, `partnerapis` are CHAD service names. Application name "CHAD" and team "CHAD Engineering" are customer-specific. |
| **Recommended Solution** | String rename only: `CHAD` → `Acme Retail`, `CHAD Engineering` → `Acme SRE Team`, `fundapis` → `checkout-api`, `fundsso` → `auth-service`, `partnerapis` → `partner-api`. All 6 runbooks and 8 simulator presets retain their content — only service name references change. |
| **Dependencies** | None |
| **Migration** | Copy original to `knowledge/examples/chad/seed_data_chad.yaml` before renaming. |

---

### PB-006 — Replace MetLife email addresses in test fixtures

| Field | Value |
|-------|-------|
| **ID** | PB-006 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | `tests/slices/test_slice_v399_chaos_sync.py:77–133`, `tests/slices/test_slice_ev1_connectors.py:399–406` |
| **Impact** | Tests assert specific MetLife email addresses and Azure DevOps org names as expected values. Any engineer cloning the repo sees live employee email addresses. Compliance risk. |
| **Recommended Solution** | Replace `dilleswar...@metlife.com` → `sre@example.com`. Replace `MetLife-Global` → `acme-org`. Replace `Australia IT_AMS` → `platform-team`. |
| **Dependencies** | None |
| **Migration** | None — test behavior unchanged |

---

### PB-007 — Add application_id scope to RunbookRow

**Completed — 2026-06-10 (Execution Readiness Review finding)**

| Field | Value |
|-------|-------|
| **ID** | PB-007 |
| **Priority** | P0 |
| **Effort** | 0 |
| **Status** | Completed — already implemented in V5.4 schema |
| **Finding** | `RunbookRow.application_id` already exists as `nullable=False` with FK to `applications.id`. No migration or code change needed. The current design (NOT NULL) correctly scopes DB runbooks per application; generic runbooks stay on disk via catalog.json. The nullable approach proposed in this item is deferred to Phase 4 (multi-tenancy) if product-level global runbooks are needed in the DB. |

---

### PB-008 — Add application_id scope to KnowledgeBaseRow

**Completed — 2026-06-10 (Execution Readiness Review finding)**

| Field | Value |
|-------|-------|
| **ID** | PB-008 |
| **Priority** | P0 |
| **Effort** | 0 |
| **Status** | Completed — already implemented in V5.4 schema |
| **Finding** | `KnowledgeBaseRow.application_id` already exists as `nullable=False` with FK to `applications.id`. Same analysis as PB-007. No action needed. |

---

## P1 — High Value

### PB-009 — Rename GBP-specific config keys to currency-neutral names

| Field | Value |
|-------|-------|
| **ID** | PB-009 |
| **Priority** | P1 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `config/policies/investigation.yaml`, `corvin/strategy/roi.py:38`, `corvin/strategy/blast_radius.py` |
| **Impact** | Config key `engineer_hourly_rate_gbp` encodes a currency assumption in the key name itself. Reading this key with a non-GBP rate produces a correctly-calculated number with an incorrectly-named key. |
| **Recommended Solution** | Rename `engineer_hourly_rate_gbp` → `engineer_hourly_rate`. Add `engineer_rate_currency: USD` alongside it. Update all code references. Tests asserting `currency == "GBP"` must be updated to read the configured value. |
| **Dependencies** | None |
| **Migration** | Both old and new key names work during transition if code reads new name with old name as fallback |

---

### PB-010 — Externalize currency, locale, and voice to application-level config

**⚠️ Blocked by TD-H3 — requires Alembic migration; three conflicting 0012_* files must be resolved first.**

| Field | Value |
|-------|-------|
| **ID** | PB-010 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `config/policies/investigation.yaml:33,46,52`, `corvin/storage/models.py` (`ApplicationEnvironmentRow`) |
| **Impact** | Currency (GBP), locale (en-GB), and voice (en-GB-RyanNeural) are global. A US customer gets GBP ROI figures and a UK English voice briefing. |
| **Recommended Solution** | Add fields to `ApplicationEnvironmentRow`: `currency_code CHAR(3)`, `locale VARCHAR(20)`, `tts_voice_name VARCHAR(100)`. Resolution order: application config → global policy → hardcoded default. |
| **Dependencies** | PB-009 |
| **Migration** | Alembic migration for new columns. Existing rows get NULL (falls back to policy value). |

---

### PB-011 — Externalize blast radius business metrics to application-level config

**⚠️ Blocked by TD-H3 — requires Alembic migration; three conflicting 0012_* files must be resolved first.**

| Field | Value |
|-------|-------|
| **ID** | PB-011 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `config/policies/investigation.yaml:29,31`, `corvin/strategy/blast_radius.py:78,87` |
| **Impact** | `blast_radius_users_per_replica: 400` is MetLife insurance platform load. `blast_radius_revenue_per_user_per_min: 0.003 GBP` is MetLife revenue model. A retail customer has 10,000 users/pod; a B2B SaaS has $50/user/min. Blast radius calculations are meaningless without per-application figures. |
| **Recommended Solution** | Add to `ApplicationEnvironmentRow`: `blast_radius_users_per_replica INT`, `blast_radius_revenue_per_user_per_min DECIMAL(12,6)`. Update `blast_radius.py` to resolve from application config. |
| **Dependencies** | PB-010 |
| **Migration** | Alembic migration. UI: add fields to Application Environment settings panel. |

---

### PB-012 — Externalize SLA targets and MTTR baseline to per-application config

| Field | Value |
|-------|-------|
| **ID** | PB-012 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `config/policies/investigation.yaml:75–78`, `corvin/storage/models.py` (`SloConfigRow`) |
| **Impact** | `sla_target_percent: 99.9`, amber/red windows, and `baseline_mttr_minutes: 45` are MetLife targets. A startup accepting 99.5% SLA gets incorrect compliance calculations. |
| **Recommended Solution** | `SloConfigRow` already stores SLA targets per application. Remove the global policy values or make them the seed defaults. `baseline_mttr_minutes` moves to `ApplicationEnvironmentRow`. |
| **Dependencies** | PB-011 |
| **Migration** | No schema changes — `SloConfigRow` already has target fields. Remove global fallback or document as "initial default only". |

---

### PB-013 — Add connection test endpoint for connectors

| Field | Value |
|-------|-------|
| **ID** | PB-013 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `apps/api/routes/applications.py`, each adapter in `corvin/connectors/` |
| **Impact** | A new customer has no way to verify their LogAnalytics workspace ID and credentials are correct before the first incident. They discover the connector is broken during a real investigation. |
| **Recommended Solution** | Add `POST /applications/{app_id}/services/{svc_id}/connectors/{connector_id}/test`. Each adapter gets a `test_connection()` method that runs a minimal query (last 1 minute, limit 1 result). Returns `{success: bool, latency_ms: int, error: str \| null}`. |
| **Dependencies** | None |
| **Migration** | New route and method — no schema changes |

---

### PB-014 — Add evidence preview endpoint for connectors

| Field | Value |
|-------|-------|
| **ID** | PB-014 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `apps/api/routes/applications.py` |
| **Impact** | A new customer cannot verify that the right log data is being collected without triggering a full investigation. |
| **Recommended Solution** | Add `GET /applications/{app_id}/services/{svc_id}/evidence/preview?lookback_minutes=60`. Runs evidence collection adapters with a short lookback, returns a sample of collected evidence (first 5 items per adapter, truncated at 500 chars each). |
| **Dependencies** | PB-013 |
| **Migration** | New route — no schema changes |

---

### PB-015 — Add per-application toolset profile

**⚠️ Blocked by TD-H3 — requires Alembic migration; three conflicting 0012_* files must be resolved first.**

| Field | Value |
|-------|-------|
| **ID** | PB-015 |
| **Priority** | P1 |
| **Effort** | L |
| **Status** | Blocked — prerequisite: fix TD-H3 (duplicate Alembic 0012_* migrations) |
| **Location** | `config/tools/toolsets.yaml`, `corvin/storage/models.py` (`ApplicationRow`) |
| **Impact** | `toolsets.yaml` enables/disables adapters globally. A pure-cloud customer using only LogAnalytics still sees AKS connector options. A pure-Kubernetes customer still sees APIM options. This creates confusion in the UI. |
| **Recommended Solution** | Add `toolset_profile JSONB` to `ApplicationRow`. Schema: `{enabled: ["elasticsearch", "log_analytics"], disabled: ["aks"]}`. Resolution: global toolsets.yaml merged with application profile (application overrides global). |
| **Dependencies** | TD-H3 fix (migration numbering), PB-010 |
| **Migration** | Alembic migration — new nullable JSONB column. UI: add adapter selection panel to Application settings. |

---

### PB-016 — Verify and scope demoAlerts.ts productization

**Reassessed 2026-06-10** — `apps/web/src/data/demoAlerts.ts` was found to be already fully parameterized (service names injected at runtime from component props; generic fallback to `service-a/b/c`). The original "remove and replace with API" recommendation was based on an incorrect assumption. Scope is now "verify and targeted fix only."

| Field | Value |
|-------|-------|
| **ID** | PB-016 |
| **Priority** | P1 |
| **Effort** | XS (was M) |
| **Status** | Needs investigation before implementing |
| **Location** | `apps/web/src/data/demoAlerts.ts` |
| **Revised Scope** | (1) Read the file and confirm service names are runtime-injected. (2) Check if scenario *descriptions* contain CHAD/MetLife-specific language. (3) If descriptions are generic: no action needed. (4) If descriptions reference CHAD: targeted text edit only — do not remove the file or replace the loading mechanism. |
| **Dependencies** | Verify before PB-005 (the rename may make descriptions inconsistent) |
| **Migration** | Likely none |

---

### PB-017 — Implement GET /config/branding API and dynamic logo loading

| Field | Value |
|-------|-------|
| **ID** | PB-017 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Location** | `apps/api/routes/` (new file), `apps/web/src/` (App.tsx or layout component) |
| **Impact** | No runtime branding configuration. Logo, product name, and colors are static. A customer cannot brand the platform without redeployment. |
| **Recommended Solution** | `GET /config/branding` returns `{product_name, logo_url, primary_color, favicon_url}`. Reads from env vars (`CORVIN_PRODUCT_NAME`, `CORVIN_LOGO_URL`, `CORVIN_PRIMARY_COLOR`). Frontend reads this on startup; applies primary color to CSS custom property `--brand-primary`; renders logo from URL. Default logo: Corvin wordmark SVG (to be designed). |
| **Dependencies** | PB-001 (remove MetLife logo first) |
| **Migration** | New API route. New env vars (all optional with sane defaults). Frontend layout change. |

---

## P2 — Configuration Quality

### PB-018 — Create customer onboarding guide

| Field | Value |
|-------|-------|
| **ID** | PB-018 |
| **Priority** | P2 |
| **Effort** | L |
| **Status** | Planned |
| **Location** | `docs/ONBOARDING_GUIDE.md` (new file) |
| **Impact** | No document exists explaining how a new customer deploys and configures Corvin. Every new customer adoption requires hand-holding. |
| **Recommended Solution** | Create `docs/ONBOARDING_GUIDE.md` covering: prerequisites, deployment options (Docker Compose, Azure App Service), environment variable reference, first application registration, connector configuration, running first investigation, customizing runbooks, configuring alerts. |
| **Dependencies** | PB-001 through PB-017 should be complete |
| **Migration** | None |

---

### PB-019 — Create generic Corvin logo and default branding

| Field | Value |
|-------|-------|
| **ID** | PB-019 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `apps/web/public/` |
| **Impact** | After removing the MetLife logo (PB-001), there is no Corvin-branded logo. The frontend shows a broken image or no logo. |
| **Recommended Solution** | Create a minimal Corvin wordmark SVG (`corvin-logo.svg`). Ship as the default. When `CORVIN_LOGO_URL` is set, override. |
| **Dependencies** | PB-001, PB-017 |
| **Migration** | None |

---

### PB-020 — Add pre-commit hooks to prevent future customer data commits

| Field | Value |
|-------|-------|
| **ID** | PB-020 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `.pre-commit-config.yaml` (new file) |
| **Impact** | The MetLife logo, CHAD seed data, and Azure tenant ID all entered the repo without detection. No tooling prevents recurrence. |
| **Recommended Solution** | Add `.pre-commit-config.yaml` with: `detect-secrets` (no API keys), `check-added-large-files` (no binary assets > 1MB), custom pattern check for `metlife`, `@metlife.com`, `CHAD`, `fundapis`. Add pre-commit to CI. |
| **Dependencies** | None |
| **Migration** | None |

---

### PB-021 — Implement prompt registry (migrate prompts from Python to YAML)

| Field | Value |
|-------|-------|
| **ID** | PB-021 |
| **Priority** | P2 |
| **Effort** | L |
| **Status** | Planned |
| **Location** | `config/prompts/` (new directory), all generator files in `corvin/strategy/` and `corvin/investigation/` |
| **Impact** | Prompt content is embedded in Python code. Cannot version, compare, or override prompts without code changes. See `docs/PROMPT_ARCHITECTURE.md`. |
| **Recommended Solution** | Create `config/prompts/` directory. Migrate each system prompt to a versioned YAML file. Generators load prompts from registry at startup. Supports customer override via `config/prompts/overrides/`. |
| **Dependencies** | None |
| **Migration** | Each YAML prompt has a `version` field. Generator reads prompt version from config, loads the corresponding YAML. Backward compatible. |

---

### PB-022 — Update documentation: CHAD = worked example, not core product

**Revised 2026-06-10** — See `docs/CHAD_ASSET_CLASSIFICATION.md`. CHAD references in documentation should be relabeled as a "worked example", not removed. AGENTS.md already updated to explain CHAD's history.

| Field | Value |
|-------|-------|
| **ID** | PB-022 |
| **Priority** | P2 |
| **Effort** | S (was M) |
| **Status** | Planned |
| **Location** | `docs/copilot-context/shared/`, `.github/copilot-instructions.md` |
| **Impact** | Context documents in `docs/copilot-context/shared/` still describe CHAD as "the application" without labeling it as an example. |
| **Recommended Solution** | (1) Update any remaining docs that treat CHAD as the current application to reference Acme Retail instead. (2) AGENTS.md already updated — no change needed. (3) `knowledge/examples/chad/README.md` already created — CHAD is now properly labeled as a worked example. (4) Create `docs/DEMO_SETUP.md` explaining the Acme Retail demo topology. |
| **Dependencies** | PB-005 (rename seed data first) |
| **Migration** | Documentation only |

---

### PB-023 — Add environment variable validation on startup

| Field | Value |
|-------|-------|
| **ID** | PB-023 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `apps/api/main.py` |
| **Impact** | Missing required environment variables cause obscure runtime errors (e.g., LLM authentication fails mid-investigation). New customers don't know which env vars are required until something breaks. |
| **Recommended Solution** | Add startup validation that checks required env vars are set and non-empty. Log clear error messages for missing vars. Differentiate required (must be set) from optional (have safe defaults). |
| **Dependencies** | None |
| **Migration** | Additive — no breaking changes |

---

### PB-024 — Add docker-compose.yml API and frontend services

| Field | Value |
|-------|-------|
| **ID** | PB-024 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `docker-compose.yml` |
| **Impact** | `docker-compose.yml` only includes the PostgreSQL service. A new customer cannot run the full stack with `docker compose up`. They must figure out the API and frontend startup commands independently. |
| **Recommended Solution** | Add `api` service (Python/uvicorn) and `web` service (Vite dev or nginx) to docker-compose.yml. Add a `docker-compose.prod.yml` override with production settings. |
| **Dependencies** | PB-005 (generic seed data for API container startup) |
| **Migration** | Additive — existing postgres service unchanged |

---

## P3 — Polish

### PB-025 — Create DEMO_SETUP.md — explain the demo application

| Field | Value |
|-------|-------|
| **ID** | PB-025 |
| **Priority** | P3 |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `docs/DEMO_SETUP.md` (new file) |
| **Impact** | New team members and evaluators see "CHAD" references throughout the docs and code with no explanation of what CHAD is or was. |
| **Recommended Solution** | Create `docs/DEMO_SETUP.md`. Explain: CHAD was the original development customer (MetLife Australia digital channels platform). The platform has been genericized. The current demo uses Acme Retail. How to seed, how to run a demo investigation, how to reset. |
| **Dependencies** | PB-005 |
| **Migration** | None |

---

### PB-026 — Remove requirements.txt (TD-L2)

| Field | Value |
|-------|-------|
| **ID** | PB-026 |
| **Priority** | P3 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | `requirements.txt` |
| **Impact** | TD-L2 — duplicate dependency specification alongside `pyproject.toml`. Dependency version drift risk. |
| **Recommended Solution** | Delete `requirements.txt`. Update any CI steps that reference it to use `pip install -e ".[dev]"`. |
| **Dependencies** | Verify CI pipelines don't depend on requirements.txt |
| **Migration** | None |

---

### PB-027 — Move startup_test.py and lifespan_test.py to tests/ (TD-L5)

| Field | Value |
|-------|-------|
| **ID** | PB-027 |
| **Priority** | P3 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | `startup_test.py`, `lifespan_test.py` in repo root |
| **Impact** | TD-L5 — test files outside `tests/` directory are not discovered by default pytest invocation. False confidence. |
| **Recommended Solution** | Move both files to `tests/`. Update pytest `testpaths` in `pyproject.toml` if needed. |
| **Dependencies** | None |
| **Migration** | None |

---

### PB-028 — Add LICENSE file

| Field | Value |
|-------|-------|
| **ID** | PB-028 |
| **Priority** | P3 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | Repo root |
| **Impact** | No `LICENSE` file. Legal ambiguity for any contributor or enterprise evaluator. |
| **Recommended Solution** | Create `LICENSE` file. Choose license type appropriate to the product commercialization strategy (proprietary for commercial, or open-source with contributor agreement). Requires legal sign-off. |
| **Dependencies** | Legal review |
| **Migration** | None |

---

### PB-029 — Complete archival of original files left in root (from previous session)

| Field | Value |
|-------|-------|
| **ID** | PB-029 |
| **Priority** | P3 |
| **Effort** | XS |
| **Status** | Planned |
| **Location** | Repo root: `BUNDLE_MANIFEST.md`, `CORVIN_COMMAND_CENTER.md`, `architecture_review.md`, `implementation_plan.md`, `presenter-script.md`, `progress.md` |
| **Impact** | Archive copies exist in `docs/archive/` but originals were never deleted. Twin documents create confusion. AI agents reading the root find stale content. |
| **Recommended Solution** | Delete the root originals. Verify `docs/archive/ARCHIVE_INDEX.md` has entries for each. |
| **Dependencies** | Confirm archive copies are complete |
| **Migration** | None |

---

### PB-030 — Remove database files from repository root (TD-C4)

| Field | Value |
|-------|-------|
| **ID** | PB-030 |
| **Priority** | P3 (was P0 in tech debt — downgraded here as it doesn't block productization, but security priority remains high) |
| **Effort** | S |
| **Status** | Planned |
| **Location** | `corvin.db`, `corvin.db.backup-20260531-140805`, `corvin_local.db`, `apps/web/corvin.db` |
| **Impact** | TD-C4 — investigation data in version control. Security and data governance violation. |
| **Recommended Solution** | Remove with `git filter-repo`. Add `*.db`, `*.db.backup*` to `.gitignore`. Verify no data remains in git history. |
| **Dependencies** | None |
| **Migration** | `git filter-repo --path corvin.db --invert-paths` for each file |

---

### PB-031 — Create knowledge/templates/ runbook template library

*Added 2026-06-10 following CHAD asset classification review.*

| Field | Value |
|-------|-------|
| **ID** | PB-031 |
| **Priority** | P1 |
| **Effort** | Done |
| **Status** | Completed 2026-06-10 |
| **Location** | `knowledge/templates/` |
| **Value** | Every new customer needs runbooks for their services. Without templates, they write from scratch or don't write at all. Templates reduce onboarding time from days to hours. |
| **What was created** | `knowledge/templates/README.md` · `runbooks/service-topology.md` · `runbooks/service-inventory.md` · `runbooks/service-dependencies.md` · `runbooks/service-api-spec.md` · `runbooks/service-known-errors.md` · `runbooks/service-security-context.md` · `apim/apim-error-reference.md` · `apim/apim-policy-summary.md` |
| **Dependencies** | PB-002 (CHAD originals must be moved to examples/ to complete the relocation) |

---

### PB-032 — Create knowledge/examples/chad/ worked example directory

*Added 2026-06-10 following CHAD asset classification review.*

| Field | Value |
|-------|-------|
| **ID** | PB-032 |
| **Priority** | P1 |
| **Effort** | Partial — README done, files not yet moved |
| **Status** | In Progress |
| **Location** | `knowledge/examples/chad/` |
| **Value** | New engineers and customers can see exactly what a fully-configured Corvin deployment looks like. Removes ambiguity about CHAD — it's explicitly labeled as a worked example, not part of the product. |
| **Remaining work** | Execute PB-002a: `git mv knowledge/runbooks/chad-*.md knowledge/examples/chad/runbooks/` · Copy `config/demo/seed_data.yaml` to `knowledge/examples/chad/seed_data_chad.yaml` before PB-005 rename · Create `knowledge/examples/chad/catalog_chad.json` from current CHAD catalog entries |
| **Dependencies** | PB-002a (file moves) |

---

## Backlog Summary

| Priority | Count | Total Effort |
|----------|-------|--------------|
| P0 — Hard Blockers | 8 items | ~5–6 days |
| P1 — High Value | 9 items | ~8–10 days |
| P2 — Configuration Quality | 7 items | ~5–7 days |
| P3 — Polish | 6 items | ~2–3 days |
| **Total** | **30 items** | **~20–26 days** |

---

## Completion Tracker

Track item completions here as Phase 1 progresses:

| Date | Item | Completed By |
|------|------|--------------|
| — | — | — |

---

## See Also

- [docs/PRODUCTIZATION_ASSESSMENT.md](PRODUCTIZATION_ASSESSMENT.md) — full audit report and strategy
- [docs/PROMPT_ARCHITECTURE.md](PROMPT_ARCHITECTURE.md) — prompt registry design (PB-021)
- [docs/TECH_DEBT.md](TECH_DEBT.md) — items that overlap with productization work
- [docs/ROADMAP.md](ROADMAP.md) — Phase 1 in the full product roadmap

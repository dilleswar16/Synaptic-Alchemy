# Corvin — Productization Backlog

**Last Updated:** 2026-06-11  
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

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-001 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Completed |
| **Resolution** | `apps/web/public/metlife-logo.svg` removed (`git rm`). Replaced by `corvin-logo.svg` (generic Corvin placeholder SVG). `NavBar.tsx` updated to load logo URL from `GET /config/branding` API with `/corvin-logo.svg` as the default fallback. `Footer.tsx` updated: `© MetLife. Internal use only.` → `© Corvin SRE Co-Pilot`. `ThemeContext.tsx` comment cleaned up. Implemented atomically with PB-017. |

---

### PB-002 — Relocate CHAD runbooks and extract template library

**Completed 2026-06-10**

| Field | Value |
|-------|-------|
| **ID** | PB-002 |
| **Priority** | P0 |
| **Effort** | M |
| **Status** | Completed |
| **Location** | `knowledge/runbooks/chad-*.md` → `knowledge/examples/chad/runbooks/` |
| **Resolution** | `git mv` executed for all 6 CHAD runbooks (`chad-api-spec.md`, `chad-dependencies.md`, `chad-known-errors.md`, `chad-security-context.md`, `chad-service-inventory.md`, `chad-service-topology.md`). Also removed the stale `fundapis` catalog entry (file never existed on disk). Template library already exists at `knowledge/templates/`. Atomic with PB-003 and PB-032. |

---

### PB-003 — Rebuild knowledge/runbooks/catalog.json with only generic entries

**Completed 2026-06-10**

| Field | Value |
|-------|-------|
| **ID** | PB-003 |
| **Priority** | P0 |
| **Effort** | S |
| **Status** | Completed |
| **Location** | `knowledge/runbooks/catalog.json` |
| **Resolution** | Rebuilt with exactly 2 entries: `apim-5xx` (keywords: apim, 5xx, gateway, apimanagement) and `aks-crashloop` (keywords: crashloop, pod, oomkilled, restart, crash). All CHAD entries and the stale `fundapis` entry removed. CHAD entries preserved in `knowledge/examples/chad/catalog_chad.json`. Atomic with PB-002 and PB-032. |

---

### PB-004 — Remove Azure subscription tenant ID from .env.example

**Completed 2026-06-10**

| Field | Value |
|-------|-------|
| **ID** | PB-004 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Completed |
| **Location** | `.env.example:78` |
| **Impact** | TD-C3 — exposes live Azure tenant ID `457bc2c0-610b-4bf1-b615-b8621ee51c31` in version-controlled file. Reconnaissance attack surface. |
| **Resolution** | Removed stray URL `https://portal.azure.com/457bc2c0-610b-4bf1-b615-b8621ee51c31` from `.env.example`. The `AZURE_TENANT_ID=placeholder` entry at line 32 already documents the correct env var pattern. |

---

### PB-005 — Rename CHAD service names in seed_data.yaml (preserve all content)

**Completed 2026-06-10**

| Field | Value |
|-------|-------|
| **ID** | PB-005 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Completed |
| **Location** | `config/demo/seed_data.yaml` |
| **Resolution** | Renamed all CHAD service identifiers throughout `config/demo/seed_data.yaml`: application `CHAD` → `Acme Retail`, team `CHAD Engineering` → `Acme SRE Team`, `fundapis` → `checkout-api`, `fundsso` → `auth-service`, `partnerapis` → `partner-api`, k8s labels `chad-*` → `acme-*`, namespace `chad` → `acme-retail`. All 6 embedded runbooks and 9 simulator presets updated to use new service names. Runbook content preserved — only service name references changed. Original CHAD seed data preserved as `knowledge/examples/chad/seed_data_chad.yaml` (PB-032). Mandatory co-change applied: `test_demo_seed_reconciles_missing_chad_services_and_slos` renamed and updated to match new service topology. 28 tests pass. Developer note: existing databases seeded with CHAD topology must be reset (drop + re-seed or `seed_demo.py --reset`). |

---

### PB-006 — Replace MetLife email addresses in test fixtures

**Completed 2026-06-10**

| Field | Value |
|-------|-------|
| **ID** | PB-006 |
| **Priority** | P0 |
| **Effort** | XS |
| **Status** | Completed |
| **Location** | `tests/slices/test_slice_v399_chaos_sync.py:74–133`, `tests/slices/test_slice_ev1_connectors.py:399–406` |
| **Resolution** | Replaced all MetLife employee emails and org names with generic `@example.com` equivalents. `dilleswar...@metlife.com` → `sre@example.com`, `chaitanyakumar...@metlife.com` → `devops@example.com`, `priya.kinker@metlife.com` → `lead@example.com`, `MetLife-Global` → `acme-org`, `Australia IT_AMS` → `platform-team`, `my.metlife.com` → `my.acme.com`. All 28 tests pass. **Sprint 1/2 review (2026-06-11) found 4 additional missed contaminations and fixed them:** (1) `corvin/delivery/email_adapter.py:265` — `MetLife · Australia` in email HTML footer → `Corvin SRE Co-Pilot`; (2) `apps/api/routes/chaos.py:93-99` — `"chad"` hardcoded as fallback k8s namespace/label → `"default"` / `service_name`; (3) `apps/web/src/components/CapacityForecastPanel.tsx:341` — `<option value="chad">` in namespace dropdown → `acme-retail`; (4) `apps/web/src/pages/ApplicationsPage.tsx` — `chad_agency` example text in Copilot agent help text → `my_agent` (4 occurrences). 60 tests pass after fixes. |

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

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-009 |
| **Priority** | P1 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | Renamed `engineer_hourly_rate_gbp` → `engineer_hourly_rate` in `config/policies/investigation.yaml` and updated comment. `corvin/strategy/roi.py:38` now reads `engineer_hourly_rate` with `engineer_hourly_rate_gbp` as a backward-compat fallback. `tests/slices/test_slice_v39_enterprise_polish.py` policy dict updated. 17 tests pass. |

---

### PB-010 — Externalize currency, locale, and voice to application-level config

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-010 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Completed |
| **Resolution** | TD-H3 confirmed not blocking (0013 is already a merge migration). Added `currency_code CHAR(3)`, `locale VARCHAR(20)`, `tts_voice_name VARCHAR(100)` to `ApplicationEnvironmentRow` in `corvin/storage/models.py`. Migration `0025_pb010_app_env_locale_currency.py` created. `InvestigationRepository.get_env_policy_overrides()` added to repository — maps `currency_code` → `blast_radius_currency`/`roi_currency`, `locale` and `tts_voice_name` → policy keys. `get_blast_radius` route updated to merge env overrides. All new columns nullable → existing rows fall back to global policy. |

---

### PB-011 — Externalize blast radius business metrics to application-level config

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-011 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Completed |
| **Resolution** | Added `blast_radius_users_per_replica INT` and `blast_radius_revenue_per_user_per_min DECIMAL(12,6)` to `ApplicationEnvironmentRow` in `corvin/storage/models.py`. Migration `0026_pb011_app_env_blast_radius.py` created. Resolution via `get_env_policy_overrides()` in repository — non-null values override global policy keys `blast_radius_users_per_replica` and `blast_radius_revenue_per_user_per_min` which `blast_radius.py` already reads via `policy.get(...)`. Existing rows get NULL → fall back to global policy. UI: add fields to Application Environment settings panel (deferred to later sprint). |

---

### PB-012 — Externalize SLA targets and MTTR baseline to per-application config

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-012 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Completed |
| **Resolution** | No schema changes needed — `SloConfigRow.target_pct` already stores per-application SLA targets. Added `InvestigationRepository.get_slo_target_pct(service_name, sli_type)` method. `GET /investigations/{id}/sla` route updated: if a `SloConfigRow` exists for the service, its `target_pct` overrides `sla_target_percent` in the global policy dict before calling `build_sla_countdown`. 15 SLA tests pass. |

---

### PB-013 — Add connection test endpoint for connectors

**Completed — already implemented in V5.4**

| Field | Value |
|-------|-------|
| **ID** | PB-013 |
| **Priority** | P1 |
| **Effort** | 0 |
| **Status** | Completed — already implemented |
| **Finding** | `POST /applications/{app_id}/connectors/{src_id}/test` already exists at `apps/api/routes/applications.py:559`. Uses `ConnectorRegistry.get_connector()` + `test_connection()`. Updates `last_tested_at`, `test_status`, `test_message` on `LogSourceRow`. Schema fields confirmed present in `corvin/storage/models.py:366-368`. No action needed. |

---

### PB-014 — Add evidence preview endpoint for connectors

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-014 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Completed |
| **Resolution** | `GET /applications/{app_id}/connectors/{src_id}/evidence/preview?service_name={name}&lookback_minutes=60` implemented at `apps/api/routes/applications.py`. Calls `connector.fetch_logs()` and `connector.fetch_metrics()` with the given lookback. Returns up to 5 items per source, truncated at 500 chars. Errors from adapters return HTTP 502. Route verified registered via import check. |

---

### PB-015 — Add per-application toolset profile

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-015 |
| **Priority** | P1 |
| **Effort** | L |
| **Status** | Completed |
| **Resolution** | TD-H3 confirmed not blocking. Added `toolset_profile JSONB` (nullable) to `ApplicationRow` in `corvin/storage/models.py`. Migration `0027_pb015_app_toolset_profile.py` created. `merge_toolset_profile(global_config, app_profile)` utility added to `corvin/toolsets/registry.py` — merges app `{"enabled": [...], "disabled": [...]}` into the global toolsets config dict (application values take precedence). Note: `get_enabled_toolsets()` is not yet wired to the investigation engine; this migration and utility provide the foundation for that connection in Phase 2. |

---

### PB-016 — Verify and scope demoAlerts.ts productization

**Completed 2026-06-11** — No-op confirmed.

| Field | Value |
|-------|-------|
| **ID** | PB-016 |
| **Priority** | P1 |
| **Effort** | XS |
| **Status** | Completed |
| **Resolution** | `apps/web/src/data/demoAlerts.ts` read and verified in Sprint 3. The file uses `buildDemoAlerts(serviceNames: string[])` — all service names are injected at runtime from caller-provided list (falls back to `service-a/b/c`). Zero CHAD or MetLife references anywhere in the file. No changes required. |

---

### PB-017 — Implement GET /config/branding API and dynamic logo loading

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-017 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Completed |
| **Resolution** | `GET /config/branding` implemented in `apps/api/routes/config.py`. Returns `{product_name, logo_url, primary_color, favicon_url}`. All fields read from env vars (`CORVIN_PRODUCT_NAME`, `CORVIN_LOGO_URL`, `CORVIN_PRIMARY_COLOR`, `CORVIN_FAVICON_URL`) with sane defaults (`"Corvin"`, `"/corvin-logo.svg"`, `"#6366f1"`, `"/favicon.svg"`). Router registered at prefix `/config` in `apps/api/main.py`. Frontend `NavBar.tsx` fetches `/api/config/branding` on mount and drives `logoUrl`/`productName` state. All env vars added to `.env.example` (commented out). Implemented atomically with PB-001. |

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

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-019 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | `apps/web/public/corvin-logo.svg` replaced with a proper SVG logo. Icon: indigo (`#6366f1`) rounded square with a path-drawn "C" arc and `#a5b4fc` signal dot at the terminus. Wordmark: "Corvin" in system-ui sans-serif. viewBox `0 0 160 44`. Uses no embedded fonts — renders consistently in all browser and image contexts. |

---

### PB-020 — Add pre-commit hooks to prevent future customer data commits

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-020 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | `.pre-commit-config.yaml` created with 4 hooks: (1) `detect-secrets` v1.5.0 with baseline file; (2) `no-metlife-refs` — pygrep hook blocks `metlife.com`, `@metlife.`, `MetLife Australia/Global`, `MetLife ·` in production files; (3) `no-chad-hardcoded` — blocks `fundapis`, `fundsso`, `partnerapis`, `chad-fundapis`, `namespace = "chad"` in production code; (4) `no-azure-tenant-ids` — blocks Azure portal URLs with UUIDs. Plus basic hygiene hooks (trailing whitespace, end-of-file, check-yaml, check-json, check-merge-conflict, debug-statements). Exclusions: `knowledge/examples/`, `docs/`, `AGENTS.md`, `README.md` are excluded from contamination guards (historical/reference content). |

---

### PB-021 — Implement prompt registry (migrate prompts from Python to YAML)

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-021 |
| **Priority** | P2 |
| **Effort** | L |
| **Status** | Completed |
| **Resolution** | `corvin/core/prompt_registry.py` — `PromptRegistry` class + `get_prompt_registry()` singleton. Loads `config/prompts/*.v*.yaml` at startup; `config/prompts/overrides/*.yaml` takes precedence. `registry.get(prompt_id, **variables)` renders prompt with `str.format_map()` for Jinja2-style variable substitution. CLI: `python -m corvin.core.prompt_registry --validate`. 11 prompts migrated: `rca_system`, `fix_strategy_system`, `autonomous_agent_system`, `causal_chain`, `comms_draft_{executive,internal,public}`, `chaos_generation`, `nl_to_kql`, `hypothesis_generation`, `runbook_builder_system`. All generators updated to call `get_prompt_registry().get(...)` — embedded strings deleted. `config/models/llm.yaml` now has `prompt_versions:` section. Override mechanism: drop `config/prompts/overrides/<id>.yaml` to override any prompt without code changes. 83 tests pass. |

---

### PB-022 — Update documentation: CHAD = worked example, not core product

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-022 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | `AGENTS.md` updated: (1) catalog.json code examples replaced — `chad-known-errors` → `aks-crashloop` (first) and `apim-5xx` (second); (2) file tree comment updated: `metlife-logo.svg` → `corvin-logo.svg`; (3) Phase 1 focus areas section updated to show all Sprint 1–3 items as ✅ complete. The V5.2 "DB Hygiene" section retained as historical changelog — these records correctly describe what changed in V5.2 (the CHAD demo seed), not current product state. |

---

### PB-023 — Add environment variable validation on startup

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-023 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | `_validate_env()` function added to `apps/api/main.py`, called at top of `_lifespan()`. Checks `AZURE_OPENAI_API_KEY`, `LITELLM_ENDPOINT`, `DATABASE_URL` (skipped when SQLite). Logs `WARNING` for missing required vars. Logs `DEBUG` for unset optional vars (`CORVIN_PRODUCT_NAME`, `CORVIN_LOGO_URL`, `CORVIN_PRIMARY_COLOR`, `CORVIN_ALLOWED_ORIGINS`). Never raises — server always starts in dev mode. |

---

### PB-024 — Add docker-compose.yml API and frontend services

**Completed 2026-06-11**

| Field | Value |
|-------|-------|
| **ID** | PB-024 |
| **Priority** | P2 |
| **Effort** | S |
| **Status** | Completed |
| **Resolution** | `docker-compose.yml` updated with `api` service (uvicorn, port 8000, depends on postgres healthcheck) and `frontend` service (nginx-served React build, port 3000, depends on api healthcheck). `DATABASE_URL` wired to postgres service. `env_file: .env` so credentials don't need to be in compose file. Original `postgres` service unchanged. Usage: `docker compose up` for full stack; `docker compose up postgres api` for backend only. Dockerfiles (`Dockerfile.api`, `apps/web/Dockerfile`) are prerequisite for actual image builds — to be created when CI/CD is set up in Phase 2. |

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

**Completed 2026-06-10**

*Added 2026-06-10 following CHAD asset classification review.*

| Field | Value |
|-------|-------|
| **ID** | PB-032 |
| **Priority** | P1 |
| **Effort** | S |
| **Status** | Completed |
| **Location** | `knowledge/examples/chad/` |
| **Resolution** | Directory complete: `README.md` (created in planning), `runbooks/` (6 CHAD runbooks moved from PB-002), `catalog_chad.json` (all CHAD catalog entries with updated paths), `seed_data_chad.yaml` (copy of original CHAD seed data preserved before PB-005 rename). CHAD is now fully documented as a worked example. |

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
| 2026-06-10 | PB-007 — RunbookRow application_id (already in schema) | Execution Readiness Review |
| 2026-06-10 | PB-008 — KnowledgeBaseRow application_id (already in schema) | Execution Readiness Review |
| 2026-06-10 | PB-031 — knowledge/templates/ runbook template library | Phase 1 planning |
| 2026-06-10 | PB-004 — Remove Azure tenant URL from .env.example | Sprint 1 |
| 2026-06-10 | PB-006 — Replace MetLife emails in test fixtures | Sprint 1 |
| 2026-06-10 | PB-002 — Relocate CHAD runbooks to knowledge/examples/chad/runbooks/ | Sprint 1 |
| 2026-06-10 | PB-003 — Rebuild catalog.json with 2 generic entries only | Sprint 1 |
| 2026-06-10 | PB-032 — Finalise knowledge/examples/chad/ worked example directory | Sprint 1 |
| 2026-06-10 | PB-005 — Rename CHAD service names in seed_data.yaml to Acme Retail topology | Sprint 1 |
| 2026-06-11 | PB-017 — GET /config/branding API endpoint + dynamic frontend logo loading | Sprint 1 |
| 2026-06-11 | PB-001 — Remove MetLife logo, add corvin-logo.svg, generic footer copyright | Sprint 1 |
| 2026-06-11 | TD-H3 — Confirmed not blocking (0013 is already a merge migration, single head) | Sprint 2 |
| 2026-06-11 | PB-009 — Rename engineer_hourly_rate_gbp → engineer_hourly_rate | Sprint 2 |
| 2026-06-11 | PB-012 — SLA countdown reads from SloConfigRow.target_pct | Sprint 2 |
| 2026-06-11 | PB-013 — Connector test endpoint (already implemented in V5.4) | Sprint 2 |
| 2026-06-11 | PB-014 — Evidence preview endpoint added to applications routes | Sprint 2 |
| 2026-06-11 | PB-010 — currency_code/locale/tts_voice_name added to ApplicationEnvironmentRow (migration 0025) | Sprint 2 |
| 2026-06-11 | PB-011 — blast_radius fields added to ApplicationEnvironmentRow (migration 0026) | Sprint 2 |
| 2026-06-11 | PB-015 — toolset_profile JSONB added to ApplicationRow + merge_toolset_profile utility (migration 0027) | Sprint 2 |

---

## See Also

- [docs/PRODUCTIZATION_ASSESSMENT.md](PRODUCTIZATION_ASSESSMENT.md) — full audit report and strategy
- [docs/PROMPT_ARCHITECTURE.md](PROMPT_ARCHITECTURE.md) — prompt registry design (PB-021)
- [docs/TECH_DEBT.md](TECH_DEBT.md) — items that overlap with productization work
- [docs/ROADMAP.md](ROADMAP.md) — Phase 1 in the full product roadmap

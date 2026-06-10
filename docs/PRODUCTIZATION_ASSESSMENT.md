# Corvin — Productization & Genericization Assessment

**Date:** 2026-06-10  
**Phase:** Phase 1 — Productization & Genericization  
**Verdict:** Corvin cannot be adopted by a different customer without source-code changes. The core investigation engine is generic; everything surrounding it is not.

---

## Productization Score

| Domain | Score | Blocker Summary |
|--------|-------|----------------|
| Core Investigation Engine | 9/10 | No customer-specific code — generic by design |
| Configuration Layer | 3/10 | GBP, en-GB, MetLife SLA targets, 400 users/pod hardcoded |
| Knowledge Base | 0/10 | 100% MetLife/CHAD-specific content across 8 runbook files |
| Branding & Assets | 0/10 | MetLife SVG logo is the only logo in public/ |
| Demo & Seed Data | 0/10 | 100% CHAD application topology |
| Prompt Architecture | 5/10 | Prompts are generic in content; no registry, versioning, or override model |
| Connector Model | 6/10 | Adapter pattern is sound; no runtime connector discovery per customer |
| Domain Model | 7/10 | Good abstraction; `ApplicationRow` + `ApplicationServiceRow` is generic |
| Frontend | 6/10 | No hardcoded CHAD logic; MetLife logo and demo data are blockers |
| Test Fixtures | 2/10 | MetLife email addresses hardcoded as expected values |
| Documentation | 3/10 | AGENTS.md, copilot-instructions, and all context docs reference CHAD throughout |

**Overall Productization Readiness: 28% — not deployable for a second customer without code changes.**

---

## Section 1 — Customer-Specific Asset Audit

### 1.1 MetLife References

| File | Lines | Content | Action |
|------|-------|---------|--------|
| `.env` | 47–54 | `AZURE_DEVOPS_ORG=MetLife-Global`, `CORVIN_EMAIL_TO=dilleswar...@metlife.com` | Not committed (should not be); document in `.env.example` as `<placeholder>` |
| `.env.example` | 78 | `https://portal.azure.com/457bc2c0-...` — live Azure tenant ID | **Delete immediately** (TD-C3) |
| `apps/web/public/metlife-logo.svg` | All | MetLife corporate logo | Delete; replace with white-labeling system |
| `knowledge/runbooks/*.md` | ~1,500 lines | Full MetLife CHAD runbooks | Move to customer-specific archive; ship only generic runbooks |
| `tests/slices/test_slice_v399_chaos_sync.py` | 77–133 | `dilleswar...@metlife.com` as expected test value | Replace with generic `sre@example.com` |
| `tests/slices/test_slice_ev1_connectors.py` | 399–406 | `MetLife-Global`, `Australia IT_AMS` | Replace with `<org>`, `<project>` placeholders in fixtures |

### 1.2 CHAD Service References

`fundapis`, `fundsso`, `partnerapis` appear throughout:

- `config/demo/seed_data.yaml` — all three are the seeded service names
- `knowledge/runbooks/catalog.json` — all CHAD keywords in the matcher
- `knowledge/runbooks/chad-*.md` — all eight runbook files

The investigation engine itself is clean — no CHAD names appear in `corvin/investigation/` or `corvin/strategy/`. The contamination is at the data and configuration layer only.

---

## Section 2 — Configuration Audit

### 2.1 Hardcoded Business Values

| Key | Location | Current Value | Problem | Fix |
|-----|----------|---------------|---------|-----|
| `blast_radius_currency` | `config/policies/investigation.yaml:33` | `GBP` | UK-only | Move to application config or tenant config |
| `engineer_hourly_rate_gbp` | `config/policies/investigation.yaml:44` | `120` | Name encodes currency assumption | Rename to `engineer_hourly_rate`; add `engineer_rate_currency` key |
| `roi_currency` | `config/policies/investigation.yaml:46` | `GBP` | UK-only | Move to application config or tenant config |
| `voice_name` | `config/policies/investigation.yaml:52` | `en-GB-RyanNeural` | UK English voice | Move to application config or tenant config |
| `blast_radius_users_per_replica` | `config/policies/investigation.yaml:29` | `400` | MetLife insurance load profile | Move to per-application config (`ApplicationEnvironmentRow`) |
| `blast_radius_revenue_per_user_per_min` | `config/policies/investigation.yaml:31` | `0.003` | MetLife-specific revenue model | Move to per-application config |
| `sla_target_percent` | `config/policies/investigation.yaml:75` | `99.9` | MetLife enterprise SLA | Move to per-application `SloConfigRow` |
| `sla_amber_seconds` | `config/policies/investigation.yaml:77` | `7200` | MetLife-specific SLA window | Move to per-application `SloConfigRow` |
| `sla_red_seconds` | `config/policies/investigation.yaml:78` | `1800` | MetLife-specific SLA window | Move to per-application `SloConfigRow` |
| `baseline_mttr_minutes` | `config/policies/investigation.yaml:42` | `45` | MetLife pre-Corvin MTTR baseline | Move to per-application or per-tenant config |

### 2.2 Code-Level Hardcodings

| File | Key | Current Default | Fix |
|------|-----|-----------------|-----|
| `corvin/strategy/roi.py:38` | `engineer_hourly_rate_gbp` | `120` | Rename key; read from policy without GBP assumption |
| `corvin/strategy/roi.py:39` | `roi_currency` | `"GBP"` | Read from application config first, fall back to policy |
| `corvin/strategy/blast_radius.py:78` | `blast_radius_users_per_replica` | `400` | Read from `ApplicationEnvironmentRow.blast_radius_config` |
| `corvin/strategy/blast_radius.py:89` | `blast_radius_currency` | `"GBP"` | Read from application config |

### 2.3 Target Configuration Hierarchy

The configuration model should resolve values in this order (most specific wins):

```
Request Context
    └─▶ Application-level config (ApplicationRow / ApplicationEnvironmentRow)
            └─▶ Tenant-level config (tenants.feature_flags, tenants.currency_code)
                    └─▶ Global policy file (config/policies/investigation.yaml)
                                └─▶ Hardcoded default in code (last resort)
```

Every business value (currency, SLA target, MTTR baseline, voice name, user load estimate) must be resolvable at the application level without requiring a global policy change.

---

## Section 3 — Knowledge Base Audit

### 3.1 Current State

The `knowledge/runbooks/` directory is the primary source of customer contamination at runtime.

| File | Lines | Status |
|------|-------|--------|
| `aks-crashloop.md` | ~100 | Generic — keep |
| `apim-5xx.md` | ~100 | Generic — keep |
| `chad-api-spec.md` | ~150 | 100% CHAD — remove or relocate to customer archive |
| `chad-dependencies.md` | ~100 | 100% CHAD — remove or relocate |
| `chad-known-errors.md` | ~200 | 100% CHAD — remove or relocate |
| `chad-service-inventory.md` | ~150 | 100% CHAD — remove or relocate |
| `chad-service-topology.md` | ~180 | 100% CHAD — remove or relocate |
| `chad-security-context.md` | ~100 | 100% CHAD — remove or relocate |
| `fundapis.md` | 1 line | Stub — remove |
| `catalog.json` | 208 lines | All CHAD keywords — rebuild with only generic entries |

**Runtime risk:** The keyword matcher in `catalog.json` is global. Any service with alert text matching CHAD keywords will have CHAD runbook content injected into the LLM prompt — providing wrong, customer-specific debugging steps to a completely different customer.

### 3.2 Knowledge Base Productization Design

The knowledge base must become customer-scoped. Two approaches:

**Option A — Application-Scoped Runbooks (Recommended for Phase 1)**

Each `RunbookRow` has an `application_id` FK. The `KnowledgeLoader` filters runbooks by the triggering application. Generic runbooks (AKS, APIM) have `application_id = NULL` and are included for all customers.

```python
# Proposed loader signature
def load_matching_runbooks(service_name: str, application_id: UUID | None) -> list[str]:
    # First: application-specific runbooks matching service name
    # Then: generic runbooks (application_id IS NULL) matching service name
    # Merge and deduplicate
```

**Option B — Tenant-Scoped Runbooks (Phase 4, multi-tenant)**

Each `RunbookRow` has both `application_id` (optional) and `tenant_id`. Queries filter by tenant first, then by application.

**Phase 1 action:** Remove all CHAD runbooks from disk. Move them to `docs/archive/customer-examples/chad/`. Rebuild `catalog.json` with only the generic AKS and APIM entries. New customer runbooks are added through the UI Runbook Management feature (already built in V5.4) — not committed to disk.

### 3.3 Runbook Disk/DB Strategy

The current two-tier system (DB first, disk fallback via `catalog.json`) is correct but creates a risk: disk files ship in the product container image. After Phase 1:

- **Disk (`knowledge/runbooks/`):** Only generic, product-level runbooks. Two initial entries: `aks-crashloop.md`, `apim-5xx.md`. These are examples and documentation, not customer-specific knowledge.
- **Database (`RunbookRow`):** All customer-specific runbooks. Created via the Runbook Management UI. Not committed to the repository.

---

## Section 4 — Generic Domain Model Assessment

### 4.1 What Is Already Generic

The domain model in `corvin/storage/models.py` is well-designed for multi-customer use:

| Model | Generic? | Notes |
|-------|---------|-------|
| `ApplicationRow` | Yes | `name`, `description`, `environment`, `team_name` — all customer-supplied |
| `ApplicationServiceRow` | Yes | `service_name`, `namespace`, `connector_type` — generic |
| `InvestigationRequestRow` | Yes | Linked to `ApplicationServiceRow` — inherits customer context |
| `RCAOutputRow` | Yes | All fields are LLM-generated from customer evidence |
| `LogSourceRow` | Yes | Credentials encrypted; type is an enum |
| `SloConfigRow` | Yes | But default values in code assume MetLife SLA targets |
| `RunbookRow` | Partial | No `application_id` FK — needs adding for scope isolation |
| `KnowledgeBaseRow` | Partial | No `application_id` FK — global knowledge leaks between applications |

### 4.2 Required Domain Model Changes

**Add `application_id` FK to scoped tables:**

```python
# corvin/storage/models.py — additions needed
class RunbookRow(Base):
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True, index=True
    )
    # NULL = generic (available to all applications)
    # Set = application-specific (available only to that application)

class KnowledgeBaseRow(Base):
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True, index=True
    )
```

**Add business config fields to `ApplicationEnvironmentRow`:**

```python
class ApplicationEnvironmentRow(Base):
    # New fields for productization
    blast_radius_users_per_replica: Mapped[int | None]     # overrides global policy
    blast_radius_revenue_per_user_per_min: Mapped[float | None]
    blast_radius_currency: Mapped[str | None]              # ISO 4217
    baseline_mttr_minutes: Mapped[int | None]
    voice_name: Mapped[str | None]                         # Azure TTS voice
```

### 4.3 Ownership Model

The current model has no application ownership concept. Any user (when authentication is added) can operate on any application. For productization:

- Phase 1: No enforcement needed (single-tenant, internal deployment)
- Phase 3 (Enterprise Foundation): Add `ApplicationMemberRow` junction table — SREs are assigned to applications. RBAC checks application membership before allowing investigation actions.

---

## Section 5 — Connector Productization Assessment

### 5.1 Current Connector Model

The adapter registry pattern in `corvin/connectors/` is sound. Connectors are defined as classes with a consistent interface. `LogSourceRow` stores credentials encrypted. `toolsets.yaml` enables/disables connector types globally.

**What works:**
- Adapter pattern isolates integration code
- AES-256-GCM credential encryption is correct
- Type enum (`LogSourceType`) prevents free-form connector configs
- `SecretRefResolver` can read credentials from environment or Key Vault

**What doesn't work for productization:**
- No UI-driven connector creation flow for new customers (partially built in EV1)
- `toolsets.yaml` enables/disables connector types globally — a new customer cannot disable connectors that don't apply to them without editing the file
- No connection testing in the UI — a customer cannot verify their LogAnalytics workspace ID is correct before saving
- `LogSourceRow.service_name` is nullable — connectors can be created without being assigned to a service, which creates orphaned connectors

### 5.2 Generic Connector Onboarding Model

For a new customer to onboard connectors without code changes:

**Step 1 — Application Registration** (already supported)
Customer creates an application with services via the UI (`ApplicationsPage`).

**Step 2 — Connector Assignment** (partially supported)
For each service, customer selects connector type (Elasticsearch, LogAnalytics, AKS, etc.) and provides credentials. These are stored encrypted in `LogSourceRow`.

**Step 3 — Connection Verification** (missing)
A `POST /applications/{id}/services/{id}/connectors/{id}/test` endpoint validates the credential can reach the target system. Returns success/failure with human-readable error.

**Step 4 — Toolset Profile** (missing)
Each application (or tenant in Phase 4) has a `toolset_profile` that overrides the global `toolsets.yaml`. A pure-Kubernetes customer should not see Elasticsearch options; a pure-cloud customer should not see AKS options.

**Step 5 — Evidence Preview** (missing)
A `GET /applications/{id}/services/{id}/evidence/preview` endpoint runs the evidence collection adapters against a sample lookback window and returns sample records. Lets a customer verify data is flowing before the first incident.

### 5.3 Outbound Connector Productization

The outbound connector builder (V5.2) is already generic:
- `teams_webhook`, `servicenow`, `email`, `pagerduty`, `generic_http`
- Template variables: `{{service_name}}`, `{{rca_summary}}`, `{{confidence}}`
- Auth types: none, bearer, api_key, basic, oauth2

This is productized. No CHAD-specific logic. The main gap is that connector configs are global — a new customer's PagerDuty connector is visible alongside CHAD's Teams webhook until multi-tenancy is added.

---

## Section 6 — Prompt Architecture Assessment

See `docs/PROMPT_ARCHITECTURE.md` for the full design. Summary:

**Current state:** All prompts are embedded in Python code. No registry. No versioning. No customer override mechanism. However, the prompt content itself is already generic — no customer-specific language in any generator.

**Required:** A prompt registry that:
1. Makes prompts auditable and reviewable independent of code
2. Allows version pinning per deployment
3. Supports customer-specific prompt overrides without forking the codebase
4. Enables A/B prompt testing during enterprise evaluation

---

## Section 7 — Frontend Productization Assessment

### 7.1 What Works

- Component library uses shadcn/ui — no customer-specific components
- All data comes from API — no hardcoded backend URLs
- React Query handles all data fetching — no direct state coupling
- Routing is dynamic (`ApplicationsPage` lists all applications from DB)

### 7.2 What Doesn't Work

| Issue | Location | Fix |
|-------|----------|-----|
| MetLife logo in public/ | `apps/web/public/metlife-logo.svg` | Delete; add `GET /config/branding` API endpoint; load logo URL dynamically |
| Demo data hardcoded in source | `apps/web/src/data/demoAlerts.ts` | Move to `GET /triggers/simulate/scenarios`; load from API |
| GBP currency symbol rendered | Components referencing ROI/blast radius | Read currency from investigation result, not hardcoded |
| No theming system | All CSS | Add CSS custom property system for brand colors; read from `GET /config/branding` |

### 7.3 Branding API Design

A new `GET /config/branding` endpoint returns:

```typescript
interface BrandingConfig {
  product_name: string;      // "Corvin" by default
  logo_url: string | null;   // Served from blob storage or null for default
  primary_color: string;     // Hex, e.g. "#6366F1"
  favicon_url: string | null;
}
```

The frontend reads this on startup and applies values to CSS custom properties. No hardcoded logo in the bundle.

---

## Section 8 — Demo & Seed Data Assessment

### 8.1 Current State

`config/demo/seed_data.yaml` is 600+ lines of CHAD-specific content:
- Application: "CHAD", team: "CHAD Engineering"
- Services: `fundapis`, `fundsso`, `partnerapis`
- 11 simulator presets targeting CHAD services
- 6 detailed CHAD runbooks

`apps/api/seed_demo.py` reads this file and creates the CHAD topology in the database when `CORVIN_DEMO_MODE=true`.

### 8.2 Target State

The demo seed should create a generic, illustrative topology:
- Application: "Acme Retail Platform" (or similar clearly-fictional name)
- Services: `checkout-api`, `inventory-service`, `payment-gateway`
- Scenarios: generic e-commerce failure patterns (payment timeouts, inventory lag, checkout errors)
- Runbooks: generic Kubernetes and API management runbooks

This gives a compelling demo without implying MetLife ownership.

### 8.3 Migration Path

1. Archive CHAD seed data to `docs/archive/customer-examples/chad/seed_data_chad.yaml`
2. Replace `config/demo/seed_data.yaml` with generic Acme Retail topology
3. Update `apps/api/seed_demo.py` to support `--reset` flag for re-seeding during development
4. Move simulator preset logic from static frontend (`demoAlerts.ts`) to API endpoint

---

## Section 9 — Recommended Target Architecture

After Phase 1 (Productization), a new customer onboards as follows:

```
1. Deploy Corvin (Docker Compose or Azure App Service)
2. Set environment variables (.env):
   - LLM endpoint + API key
   - PostgreSQL connection string
   - Azure credentials (for AKS/LogAnalytics/APIM adapters)
3. Open Corvin UI
4. Create an Application (name, description, team)
5. Add Services (name, namespace, connector type, credentials)
6. Test connector — verify data flows
7. Configure SLO targets and alert thresholds
8. Upload runbooks via Runbook Management UI
9. Send a test alert via Alert Simulator
10. Review the generated RCA
```

No source code changes. No YAML files with customer-specific data. No logo files to replace.

---

## Section 10 — Migration Strategy

### Phase 1 execution sequence:

**Week 1 — Eliminate hard blockers**
1. Delete MetLife logo from `apps/web/public/`
2. Remove CHAD runbooks from `knowledge/runbooks/` (archive to `docs/archive/customer-examples/chad/`)
3. Remove `.env.example` Azure tenant URL (TD-C3)
4. Replace `config/demo/seed_data.yaml` with generic Acme Retail topology
5. Fix test fixtures (replace MetLife emails with generic addresses)

**Week 2 — Configuration externalization**
1. Rename currency-specific config keys (remove `_gbp` from key names)
2. Add currency/locale/voice resolution to ApplicationEnvironmentRow
3. Add business metric fields to ApplicationEnvironmentRow (users_per_replica, revenue_per_user_min)
4. Update `corvin/strategy/roi.py` and `blast_radius.py` to read from application-level config first

**Week 3 — Knowledge base genericization**
1. Add `application_id` FK to `RunbookRow` and `KnowledgeBaseRow`
2. Create Alembic migration
3. Update `KnowledgeLoader` to filter by application_id (null = generic)
4. Rebuild `catalog.json` with only generic AKS and APIM entries

**Week 4 — Connector onboarding hardening**
1. Add connection test endpoint
2. Add evidence preview endpoint
3. Add per-application toolset profile override
4. Update Runbook Management UI to show application scoping

**Week 5 — Branding and demo**
1. Create `GET /config/branding` endpoint
2. Update frontend to load logo and colors from API
3. Move demo scenarios from `demoAlerts.ts` to `GET /triggers/simulate/scenarios`
4. Remove `apps/web/src/data/demoAlerts.ts`

**Week 6 — Prompt architecture and documentation**
1. Create `config/prompts/` directory with versioned prompt YAML files
2. Migrate all prompts from Python code to YAML registry
3. Update generators to load from prompt registry
4. Create customer onboarding guide (`docs/ONBOARDING_GUIDE.md`)

---

## See Also

- [docs/PRODUCTIZATION_BACKLOG.md](PRODUCTIZATION_BACKLOG.md) — actionable backlog with priorities and effort
- [docs/PROMPT_ARCHITECTURE.md](PROMPT_ARCHITECTURE.md) — prompt registry and versioning design
- [docs/ROADMAP.md](ROADMAP.md) — Phase 1 in context of the full product roadmap
- [docs/TECH_DEBT.md](TECH_DEBT.md) — technical debt that overlaps with productization gaps

# CHAD Asset Classification & Template Strategy

**Date:** 2026-06-10  
**Phase:** Phase 1 — Productization & Genericization  
**Reviewers:** Engineering Lead  
**Status:** Approved — supersedes PB-002, PB-003, PB-005, PB-022 original scope

---

## Premise

CHAD is not purely customer contamination. It is also the most complete example of Corvin in use — a real AKS Java microservices platform with real incidents, real runbooks, and real failure patterns. Much of this content has **generic reuse value** that would be lost if deleted.

The correct question for each asset is not "does this contain CHAD?" but "what does this teach about running Corvin, and can that knowledge benefit any customer?"

---

## Classification Framework

| Category | Definition | Action |
|----------|-----------|--------|
| **A — Customer Contamination** | MetLife-specific identifiers: tenant IDs, subscription IDs, IP ranges, employee emails, live URLs, company-specific branding | Remove immediately |
| **B — Reference Example** | CHAD-specific but valuable as a complete worked example showing what Corvin documentation looks like when fully populated | Relocate to `knowledge/examples/chad/` — preserved, not deleted |
| **C — Generic Template** | Structure and patterns that apply to any AKS microservices deployment; customer-specific values replaced with `<PLACEHOLDER>` | Extract to `knowledge/templates/` |

---

## Asset-by-Asset Classification

---

### `knowledge/runbooks/chad-service-topology.md`

**What it contains:**
- AKS namespace and deployment structure
- Pod labels and HPA configuration (3 HPAs, 70% CPU target)
- Health probe patterns (startup 90s, readiness 15s, liveness 30s)
- Kubernetes security context (non-root, no privilege escalation)
- Istio service mesh with AuthorizationPolicy
- OTEL/Elastic telemetry tagging

**Customer-specific elements (Category A):**
- ACR registry URL: `acr14470aepr011.azurecr.io`
- OTEL service name tags: `ChAD`, `EAI14470-Prod`
- Specific hostnames: `chad-fundapis`, deployment suffixes

**Generic elements (Category C):**
The entire *structure* — how to document namespace, deployment names, HPAs, probes, security context, Istio policies, OTEL tagging — is exactly what Corvin's LLM needs to reason about any AKS deployment. This is the most operationally valuable runbook template in the set.

**Decision: B + C**
- Move original to `knowledge/examples/chad/runbooks/chad-service-topology.md`
- Extract template to `knowledge/templates/runbooks/service-topology.md`
- Template replaces ACR URL, OTEL tags, deployment names with `<PLACEHOLDER>` blocks

---

### `knowledge/runbooks/chad-service-inventory.md`

**What it contains:**
- Service table: Maven artifactId, main Spring Boot class, port, AKS deployment name, purpose
- Inter-service dependency matrix
- Architecture risk flags (no shared DB, no message bus)

**Customer-specific elements (Category A):**
- Package names: `au.com.metlife.channel.*`, `au.com.metlife.fundapi`
- Specific `@SpringBootApplication` class names

**Generic elements (Category C):**
This is essentially an **onboarding checklist** for any Java Spring Boot microservices deployment. The column structure (artifactId, class, port, deployment name, purpose) tells Corvin exactly how to map a Kubernetes deployment to a service's codebase. The inter-service dependency matrix is fundamental topology knowledge.

Any Java microservices customer on AKS would fill in this exact template.

**Decision: B + C**
- Move original to `knowledge/examples/chad/runbooks/chad-service-inventory.md`
- Extract template to `knowledge/templates/runbooks/service-inventory.md`

---

### `knowledge/runbooks/chad-security-context.md`

**What it contains:**
- Auth architecture: JWT validated at APIM, services trust APIM (no double-validation)
- Azure AD tenant and audience config
- IP allowlist (MetLife Australia/India ranges, IPv6 blocked)
- Azure Workload Identity with federated credentials
- OTEL Java Agent 2.8.0 + Micrometer OTLP metrics
- **SRE decision guide:**
  - 401 = token issue (not service issue)
  - 403 + `IP_NOT_ALLOWED` = APIM IP allowlist (not service code)
  - Pod crash-loop → check Key Vault connectivity

**Customer-specific elements (Category A):**
- Specific managed identity client ID: `94148a30-...`
- Specific Azure tenant: `ca56a4a5-...`
- MetLife Australia/India IP ranges
- Specific Key Vault name: `kyv14470aepr0101`

**Generic elements (Category C):**
The Workload Identity pattern (service account → federated credential → managed identity → Key Vault) is the **recommended production pattern for any Azure AKS deployment**. The SRE decision guide for HTTP errors (401 = token, 403+IP_NOT_ALLOWED = APIM allowlist) is **generic Azure APIM knowledge** that any customer should have.

**Decision: B + C**
- Move original to `knowledge/examples/chad/runbooks/chad-security-context.md`
- Extract template to `knowledge/templates/runbooks/service-security-context.md`
- The SRE notes about Azure error codes move into the generic template (they apply universally)

---

### `knowledge/runbooks/chad-api-spec.md`

**What it contains:**
- Three service API specs with: base path, auth, rate limits, failure modes, edge cases
- APIM policy summary: JWT validation, Azure AD config, rate limits per IP, IP allowlist, payload size limits

**Customer-specific elements (Category A):**
- Azure AD tenant: `ca56a4a5-...`
- Specific base paths: `/b2bservice/v1/schemes/`
- MetLife domain: `auth.asia.metlife.com`
- MetLife production endpoints: `channels.metlife.com.au`
- IP allowlist ranges

**Generic elements (Category C):**
The **per-service API spec format** (base path, auth type, rate limit, failure modes, edge cases) is an excellent template for documenting any API-exposed service. The **APIM policy summary format** (JWT validation config, rate limiting config, IP allowlist, payload limits) is directly applicable to any Azure APIM deployment.

This template teaches Corvin how to reason about APIM-level failures vs. service-level failures.

**Decision: B + C**
- Move original to `knowledge/examples/chad/runbooks/chad-api-spec.md`
- Extract template to `knowledge/templates/runbooks/service-api-spec.md`
- Extract APIM policy template to `knowledge/templates/apim/apim-policy-summary.md`

---

### `knowledge/runbooks/chad-known-errors.md`

**What it contains:**
- Java GlobalExceptionHandler error types per service
- APIM-level error codes with HTTP status and meaning

**Customer-specific elements (Category A):**
- Java package names: `au.com.metlife.channel.exception.GlobalExceptionHandler`
- MetLife-specific exception names: `XSDFileNameException`, `BusinessValidationException`

**Generic elements — CRITICAL:**
The **APIM error code table** is entirely generic:
- `IP_NOT_ALLOWED` (403) — IP not in APIM allowlist
- `IPV6_NOT_SUPPORTED` (403) — IPv6 not allowed
- `PAYLOAD_TOO_LARGE` (413) — exceeds size policy
- `QUOTA_EXCEEDED` (429) — rate limit hit
- Unauthorized (401) — JWT invalid or missing
- Rate limit exceeded (429) — per-IP limit

Every customer using Azure APIM will see these exact error codes. This should become a **generic Azure APIM reference** in the template library, not buried in CHAD content.

The **GlobalExceptionHandler pattern** (each Java Spring Boot service has a structured exception handler that maps exceptions to HTTP status codes) is a design pattern template, not CHAD-specific.

**Decision: B + C (split)**
- Move original to `knowledge/examples/chad/runbooks/chad-known-errors.md`
- Extract APIM error codes to `knowledge/templates/apim/apim-error-reference.md` (generic — no placeholders needed, these ARE the actual codes)
- Extract Java error handler template to `knowledge/templates/runbooks/service-known-errors.md`

---

### `knowledge/runbooks/chad-dependencies.md`

**What it contains:**
- Primary data store: Cosmos DB containers and their purpose
- Credential store: Azure Key Vault secrets
- External services: PingFederate, inter-service HTTP calls
- Telemetry: OTLP endpoint, metrics path
- Architecture facts: synchronous-only, no message queues

**Customer-specific elements (Category A):**
- Cosmos DB account name: `cdb14470aepr0101`
- Key Vault name: `kyv14470aepr0101`
- Container names: `FundRequest`, `MemberProfile`, `ProxyAuditLog` etc.
- PingFederate endpoint, MetLife-specific configuration

**Generic elements (Category C):**
The **dependency documentation format** (data stores → auth stores → external services → telemetry → architecture constraints) is exactly what Corvin's LLM needs to build a causal chain. Knowing "this service depends on Cosmos DB" helps the LLM infer "a Cosmos DB throttling event could cause this service to fail."

The "no message queues (synchronous HTTP only)" fact is particularly valuable — it tells Corvin the blast radius propagates synchronously.

**Decision: B + C**
- Move original to `knowledge/examples/chad/runbooks/chad-dependencies.md`
- Extract template to `knowledge/templates/runbooks/service-dependencies.md`

---

### `knowledge/runbooks/catalog.json`

**What it contains:**
- Product-level runbook index: keyword → file → match_patterns
- Currently has 8 entries, all CHAD-specific (except aks-crashloop and apim-5xx)

**Classification:**
- The **structure** of catalog.json is Category C (the format is the product interface)
- The CHAD keyword entries are Category A (they match against customer alerts and inject wrong runbooks)
- The `aks-crashloop` and `apim-5xx` entries are Category B (generic, keep)

**Decision:**
Rebuild catalog.json with only generic entries. The CHAD catalog entries move to `knowledge/examples/chad/catalog_chad.json` — showing new customers what a fully-populated catalog entry looks like for a Java AKS deployment.

---

### `config/demo/seed_data.yaml`

**What it contains (624 lines):**
1. Application and service definitions with CHAD names
2. SLO profiles with specific targets
3. 8 simulator presets (failure scenarios)
4. Environment definitions (prod/staging/dev pattern)
5. 6 detailed runbooks embedded in YAML

**Classification of the 6 embedded runbooks:**

| Runbook | Failure Pattern | Generic? |
|---------|----------------|---------|
| Fund APIs — 503 Error Rate Spike | APIM → backend 503 pattern | **Yes — any API gateway** |
| Fund APIs — Heap Memory Pressure & OOM | JVM heap exhaustion pattern | **Yes — any Java/JVM service** |
| Fund SSO — Identity Cache Poisoning & 401 Spike | Auth cache corruption pattern | **Yes — any SSO/auth service** |
| Partner APIs — HPA Controller Failure & Scale Lag | Kubernetes HPA not scaling pattern | **Yes — any AKS deployment** |
| AKS — Pod CrashLoop & Eviction Response | Pod eviction pattern | **Yes — any Kubernetes** |
| APIM — Gateway Degradation & Backend Failover | APIM upstream failover pattern | **Yes — any Azure APIM** |

**Critical finding:** All 6 runbooks describe **universal cloud microservices failure patterns**. None of the investigation steps are CHAD-specific. The only CHAD contamination is the service names in headings (`fundapis`, `partnerapis`). The content — what evidence to collect, what root causes to consider, what fix actions to take — is valid for any customer.

**Classification of simulator presets:**
All 8 presets model generic failure modes: HPA failure, 503 spike, auth errors, memory leak, chaos experiments. The only CHAD content is the `service_name` field pointing to CHAD services.

**Decision: Generalize (not replace)**
- Rename CHAD → `acme-retail`, `fundapis` → `checkout-api`, `fundsso` → `auth-service`, `partnerapis` → `partner-api`
- Preserve ALL 6 runbooks with renamed service references
- Preserve ALL 8 simulator presets with renamed service references
- Archive original as `knowledge/examples/chad/seed_data_chad.yaml`
- Total change: ~15 string substitutions, not a content rewrite

This is a much smaller change than the original PB-005 specification.

---

### `knowledge/runbooks/aks-crashloop.md` and `apim-5xx.md`

**Classification: Already Generic (keep in place)**

Both are well-structured, product-level runbooks with no customer-specific content. No changes needed. These are the **reference implementations** showing what a generic runbook looks like.

---

### `knowledge/runbooks/README.md`

**Classification: Generic (update)**

Good structure guide. Update to reference the template library so new customers know templates exist.

---

## Summary Decision Table

| Asset | Category | Decision | Destination |
|-------|----------|----------|-------------|
| `chad-service-topology.md` | B + C | Move + Extract Template | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-topology.md` |
| `chad-service-inventory.md` | B + C | Move + Extract Template | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-inventory.md` |
| `chad-security-context.md` | B + C | Move + Extract Template | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-security-context.md` |
| `chad-api-spec.md` | B + C | Move + Extract Template | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-api-spec.md` + `knowledge/templates/apim/apim-policy-summary.md` |
| `chad-known-errors.md` | B + C | Move + Extract Templates | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-known-errors.md` + `knowledge/templates/apim/apim-error-reference.md` |
| `chad-dependencies.md` | B + C | Move + Extract Template | `knowledge/examples/chad/runbooks/` + `knowledge/templates/runbooks/service-dependencies.md` |
| `catalog.json` (CHAD entries) | A | Remove CHAD entries, keep generic | Rebuild for aks-crashloop + apim-5xx only; CHAD entries → `knowledge/examples/chad/catalog_chad.json` |
| `config/demo/seed_data.yaml` | B → Generalize | Rename service names only | Preserve all runbooks and scenarios; rename CHAD→Acme Retail; archive original |
| `apps/web/public/metlife-logo.svg` | A | Delete | Archive to `knowledge/examples/chad/assets/` |
| `aks-crashloop.md` | Generic | Keep in place | No change |
| `apim-5xx.md` | Generic | Keep in place | No change |
| `.env.example` Azure tenant URL | A | Delete immediately | TD-C3 |
| MetLife emails in tests | A | Replace with `sre@example.com` | Test fixtures only |

---

## Template Library Structure

```
knowledge/
  runbooks/                         ← runtime-loaded, generic only
    aks-crashloop.md                ← keep (generic)
    apim-5xx.md                     ← keep (generic)
    catalog.json                    ← rebuild (generic entries only)
    README.md                       ← update to reference templates

  templates/                        ← NEW: reference templates for customer use
    README.md                       ← how to use templates
    runbooks/
      service-topology.md           ← from chad-service-topology.md
      service-inventory.md          ← from chad-service-inventory.md
      service-security-context.md   ← from chad-security-context.md
      service-api-spec.md           ← from chad-api-spec.md
      service-dependencies.md       ← from chad-dependencies.md
      service-known-errors.md       ← from chad-known-errors.md
    apim/
      apim-policy-summary.md        ← from chad-api-spec.md APIM section
      apim-error-reference.md       ← from chad-known-errors.md (generic Azure codes)
    kql/
      README.md                     ← placeholder for Phase 2

  examples/                         ← NEW: complete worked examples
    chad/
      README.md                     ← "Worked example: MetLife CHAD Java/AKS platform"
      runbooks/
        chad-service-topology.md    ← original preserved
        chad-service-inventory.md
        chad-security-context.md
        chad-api-spec.md
        chad-known-errors.md
        chad-dependencies.md
      catalog_chad.json             ← original CHAD catalog entries
      seed_data_chad.yaml           ← original CHAD demo seed data

config/
  demo/
    seed_data.yaml                  ← RENAMED: CHAD → Acme Retail (content preserved)
```

---

## Backlog Revisions

The following backlog items require modification based on this classification:

### PB-002 — Revised

| Field | Before | After |
|-------|--------|-------|
| **Title** | Remove CHAD runbooks from disk knowledge base | Relocate CHAD runbooks to examples/ and extract template library |
| **Priority** | P0 | P0 (urgent to avoid wrong runbook injection) |
| **Effort** | XS | M (extraction requires creating 6 templates + 2 APIM docs) |
| **Action** | Delete | Move originals to `knowledge/examples/chad/runbooks/`; create templates in `knowledge/templates/runbooks/` |
| **Rationale** | CHAD runbooks contain valuable structural patterns. Extraction preserves the knowledge. |

**New sub-items:**
- PB-002a: Move CHAD runbook files to `knowledge/examples/chad/runbooks/`
- PB-002b: Create `knowledge/templates/runbooks/` with 6 templates
- PB-002c: Create `knowledge/templates/apim/` with APIM policy summary and error reference
- PB-002d: Create `knowledge/examples/chad/README.md` explaining the worked example

### PB-003 — Unchanged

Rebuild `catalog.json` with only generic entries (aks-crashloop, apim-5xx). CHAD entries go to `knowledge/examples/chad/catalog_chad.json`. No change to priority or effort.

### PB-005 — Revised

| Field | Before | After |
|-------|--------|-------|
| **Title** | Replace CHAD seed data with generic Acme Retail topology | Generalize seed_data.yaml names from CHAD → Acme Retail (preserve all content) |
| **Priority** | P0 | P0 |
| **Effort** | M (rewrite) | XS (rename only, ~15 substitutions) |
| **Action** | Replace content | String rename: `CHAD` → `Acme Retail`, `CHAD Engineering` → `Acme SRE Team`, `fundapis` → `checkout-api`, `fundsso` → `auth-service`, `partnerapis` → `partner-api` |
| **Rationale** | All 6 embedded runbooks describe universal failure patterns. All 8 simulator presets model generic failure modes. Only the names are CHAD-specific. |

### PB-022 — Revised

| Field | Before | After |
|-------|--------|-------|
| **Title** | Update documentation to remove all CHAD references | Relocate CHAD as worked example; update docs to reference examples/ |
| **Scope change** | Remove all CHAD mentions | Keep CHAD mentions where they explain the worked example; remove from "current state" docs |
| **Rationale** | AGENTS.md and copilot-instructions.md already updated to explain CHAD's history. The examples/ directory IS the appropriate home for CHAD context. |

### New Item: PB-031 — Create knowledge/templates/ library

| Field | Value |
|-------|-------|
| **ID** | PB-031 |
| **Priority** | P1 |
| **Effort** | M |
| **Status** | Planned |
| **Description** | Create the `knowledge/templates/` directory with 6 runbook templates, 2 APIM templates, and a README explaining how to use them for onboarding new applications. |
| **Value** | Every new customer needs to create runbooks for their services. Without templates, they write from scratch or don't write at all. Templates reduce onboarding time from days to hours. |
| **Dependencies** | PB-002 (move CHAD originals first; templates are extracted from them) |

### New Item: PB-032 — Create knowledge/examples/chad/ worked example

| Field | Value |
|-------|-------|
| **ID** | PB-032 |
| **Priority** | P1 |
| **Effort** | S |
| **Status** | Planned |
| **Description** | Create `knowledge/examples/chad/` with all original CHAD runbooks, catalog entries, seed data, and a README explaining: "This is a complete example of Corvin configured for a MetLife-style Java Spring Boot / AKS / Azure APIM deployment. Use it as a reference when onboarding similar applications." |
| **Value** | New engineers and customers can see exactly what a fully-configured Corvin deployment looks like. Removes the need to understand CHAD vs. product — it's explicitly labeled as an example. |
| **Dependencies** | PB-002a (files must be moved before this README is written) |

---

## Net Effect on Productization Score

| Domain | Before Classification | After Classification |
|--------|-----------------------|---------------------|
| Knowledge Base | 0/10 | 4/10 (templates created; CHAD moved to labeled examples) |
| Demo & Seed Data | 0/10 | 6/10 (rename only; content preserved and generic) |
| Documentation | 3/10 | 5/10 (CHAD examples = documented onboarding material) |

The classification approach preserves more value while still achieving the productization goal.

---

## See Also

- [docs/PRODUCTIZATION_BACKLOG.md](PRODUCTIZATION_BACKLOG.md) — backlog items PB-001 through PB-030 (items PB-002, PB-005, PB-022 revised; PB-031, PB-032 new)
- [docs/PRODUCTIZATION_ASSESSMENT.md](PRODUCTIZATION_ASSESSMENT.md) — full productization audit
- [docs/ROADMAP.md](ROADMAP.md) — Phase 1 milestone map

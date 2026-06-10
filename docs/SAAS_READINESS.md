# Corvin — SaaS Readiness Assessment

**Last Updated:** 2026-06-10  
**Current Maturity Level:** Level 0 — Not SaaS-Ready

The platform is architecturally single-tenant at every layer. There is no tenant concept in the data model, configuration system, or deployment architecture. SaaS enablement requires completing the Enterprise Readiness track (EV1–EV3) first.

---

## Hard Blockers

These must be resolved before any SaaS motion:

| Blocker | Current State | Required |
|---------|--------------|---------|
| No tenant isolation | All data in shared tables, no `tenant_id` anywhere | Every table needs `tenant_id` FK with row-level security |
| No authentication | Open API | OAuth2/OIDC with tenant-scoped tokens before any SaaS work |
| Single global LLM config | One `config/models/llm.yaml` for all | Per-tenant LLM provider and model selection (BYOK support) |
| Single encryption key | One `CORVIN_ENCRYPTION_KEY` env var | Per-tenant encryption key derivation (Azure Key Vault + tenant KID) |
| Single database | One Postgres instance for all data | Shared schema + RLS (recommended) or database per tenant |
| Hardcoded business config | `GBP`, `en-GB-RyanNeural`, MetLife assets | All values move to per-tenant configuration |
| No onboarding flow | Manual env vars + YAML files | Self-service tenant onboarding wizard |

---

## Multi-Tenancy Strategy

### Recommended: Shared Schema + Row Level Security (RLS)

Best for: standard SaaS serving 100–10,000 tenants.

**Approach:**
- All tables get a `tenant_id UUID NOT NULL` column
- PostgreSQL RLS policies enforce `tenant_id = current_setting('app.tenant_id')`
- Application middleware injects `tenant_id` from the JWT claim into each DB session
- One schema, one codebase, strong isolation through the DB engine

**Pros:** Scales to 10k+ tenants. Single codebase. Simple operational model.  
**Cons:** RLS policy coverage must be tested exhaustively. Cross-tenant queries require admin bypass.

### Alternative: Schema per Tenant
Best for: SMB SaaS or high-compliance customers needing schema-level isolation.  
Rejected for initial SaaS offering due to schema sprawl and migration complexity at scale.

### Alternative: Database per Tenant
Best for: large enterprise customers with contractual data residency requirements.  
Available as an option for premium tier but not the default deployment model.

---

## Tables Requiring `tenant_id`

Every table must have `tenant_id UUID NOT NULL REFERENCES tenants(id)`:

```
investigation_requests      rca_outputs                fix_strategy_outputs
evidence_bundles            post_mortems               chat_messages
corvin_sessions             corvin_messages            runbook_sessions
applications                application_services       application_environments
log_sources                 outbound_connectors        notification_contacts
slo_configs                 slo_snapshots              knowledge_base
runbooks                    simulator_presets          playwright_scripts
playwright_runs             chaos_runs                 predictive_alerts
predictive_penalties        validation_definitions     validation_runs
approval_decisions          validation_automation_policies
```

---

## Tenant Configuration Table (to be created)

```sql
CREATE TABLE tenants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                VARCHAR(100) UNIQUE NOT NULL,   -- subdomain / URL segment
    display_name        VARCHAR(255) NOT NULL,
    -- LLM configuration
    llm_provider        VARCHAR(50),                    -- azure_openai | openai | anthropic
    llm_model           VARCHAR(100),                   -- per-tenant model override
    llm_endpoint        TEXT,                           -- per-tenant API endpoint (BYOK)
    llm_api_key_ref     VARCHAR(255),                   -- Azure Key Vault secret reference
    -- Credential management
    encryption_key_id   VARCHAR(255),                   -- Azure Key Vault KID for credential encryption
    -- Branding
    logo_url            TEXT,
    primary_color       VARCHAR(20),
    custom_domain       VARCHAR(255),
    -- Locale
    currency_code       CHAR(3) DEFAULT 'USD',
    locale              VARCHAR(20) DEFAULT 'en-US',
    tts_voice_name      VARCHAR(100),
    -- Subscription
    subscription_tier   VARCHAR(50) DEFAULT 'trial',   -- trial | starter | professional | enterprise
    feature_flags       JSONB DEFAULT '{}',             -- per-tier entitlements
    -- Lifecycle
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    suspended_at        TIMESTAMPTZ,
    trial_expires_at    TIMESTAMPTZ
);
```

---

## SaaS Capability Gap Map

| Capability | Status | Priority | Notes |
|-----------|--------|---------|-------|
| Tenant isolation (data model) | Missing | P0 | Foundation — nothing else works without this |
| Authentication with tenant context | Missing | P0 | JWT must carry `tenant_id` claim |
| Tenant onboarding wizard | Missing | P0 | Self-service: create account → configure connectors → invite users |
| Subscription / billing integration | Missing | P0 | Stripe or Azure Marketplace |
| Feature entitlement flags per plan | Missing | P0 | Gate features by `subscription_tier` |
| Usage metering | Missing | P0 | Track LLM tokens + investigation count per tenant per billing period |
| Per-tenant LLM configuration | Missing | P1 | BYOK (bring your own key) for enterprise |
| Per-tenant encryption keys | Missing | P1 | Azure Key Vault + per-tenant KID |
| Per-tenant branding / white-labeling | Missing | P1 | Logo, primary color, custom domain |
| Tenant admin portal | Missing | P1 | User management, connector management, billing overview |
| Per-tenant rate limiting | Missing | P1 | Prevent one tenant from starving others |
| Self-service connector management | Partial | P1 | Application Panel exists; needs tenant scoping |
| Tenant data export API (GDPR) | Missing | P1 | Full data export + deletion |
| SCIM user provisioning | Missing | P2 | For enterprise customers using external IdPs |
| Usage analytics dashboard | Missing | P2 | Show tenants their investigation counts, LLM costs, MTTR |
| Tenant-specific SLA agreements | Missing | P2 | Configurable SLA targets per tenant |
| Cross-tenant benchmarking | Missing | P3 | Anonymized industry comparisons |
| Azure Marketplace listing | Missing | P3 | One-click deploy for new customers |

---

## Multi-Tenant Migration Strategy

### Phase A — Authentication Foundation (prerequisite, EV2)
Before any tenant work begins:
1. Implement OIDC authentication. JWT carries `tenant_id` claim.
2. Middleware injects `tenant_id` into all requests.
3. `get_tenant_id()` helper reads from request context, never from request body.

### Phase B — Tenant Table and Config (EV4)
1. Create `tenants` table with the schema above.
2. Seed a `default_tenant` for the existing single-tenant deployment.
3. Migrate `config/models/llm.yaml`, `config/policies/investigation.yaml` values to per-tenant config.
4. Create tenant configuration API: `GET/PATCH /admin/tenants/{id}`.

### Phase C — Schema Migration (EV4)
1. Add `tenant_id UUID NOT NULL DEFAULT '<default_tenant_uuid>'` to all 28 tables.
2. Backfill existing rows with `default_tenant_uuid`.
3. Apply PostgreSQL RLS policies.
4. Add CI test: assert every query result is tenant-scoped (attempt cross-tenant read and expect 0 results).

### Phase D — Tenant Isolation Hardening (EV4)
1. SQLAlchemy session hook: `SET LOCAL app.tenant_id = :tenant_id` on every connection checkout.
2. RLS bypass role for admin/migration operations only.
3. Connection pool per active tenant (or connection proxy).

### Phase E — SaaS Operations (EV5)
1. Tenant provisioning API with onboarding wizard.
2. Billing integration (Stripe checkout + webhook for subscription events).
3. Usage metering: write to a `usage_events` table on every investigation + LLM call.
4. Feature entitlement enforcement via `tenant.feature_flags`.

---

## Pricing Tier Model (Recommended)

| Tier | Investigations/month | Features | Target |
|------|---------------------|---------|--------|
| Trial | 50 | Core investigation, web dashboard | Evaluation |
| Starter | 500 | + Teams ChatOps, post-mortems | Small teams |
| Professional | 5,000 | + Predictive alerts, chaos, DORA | Mid-market |
| Enterprise | Unlimited | + SSO, SCIM, BYOK, custom domain, SLA | Large enterprise |

Feature flags per tier are stored in `tenants.feature_flags JSONB` and enforced at the route level.

---

## See Also

- [docs/ENTERPRISE_READINESS.md](ENTERPRISE_READINESS.md) — identity, audit, and security gaps that must be resolved first
- [docs/ROADMAP.md](ROADMAP.md) — EV1–EV5 build sequence
- [docs/TECH_DEBT.md](TECH_DEBT.md) — technical debt that complicates SaaS migration

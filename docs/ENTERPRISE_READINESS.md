# Corvin — Enterprise Readiness Assessment

**Last Updated:** 2026-06-10  
**Assessed Against:** Enterprise SaaS production standards  
**Current Maturity Level:** Level 1 — Proof of Concept (out of 5)

The platform has exceptional functional depth — V5.4 capabilities from a project that began as a hackathon entry. The architecture has strong design instincts: contracts-first, config-driven, adapter registry, dependency injection. The path to enterprise readiness is clear and executable. The blocker is foundation-layer gaps: authentication, authorization, audit, and tenant isolation.

**The first and non-negotiable deliverable before any external customer deployment is authentication (TD-C1).**

---

## Maturity Score by Domain

| Domain | Score | Notes |
|--------|-------|-------|
| Authentication & Identity | 0/10 | Zero — no auth on any endpoint |
| Authorization & RBAC | 0/10 | Zero — no role enforcement |
| Audit & Compliance | 2/10 | `approval_decisions` table exists but identity is unverified |
| API Maturity | 3/10 | No versioning, no rate limiting, no structured errors |
| Operational Observability | 2/10 | Basic health endpoint only; no tracing, no metrics |
| Security Controls | 3/10 | AES-256-GCM creds (good); no WAF, no dependency scanning |
| Scalability | 3/10 | Synchronous pipeline, per-worker background tasks |
| Multi-tenancy | 0/10 | Single-tenant throughout |
| Test Coverage | 7/10 | Comprehensive slice tests; missing integration test harness |
| Domain Architecture | 6/10 | Clean contracts, good separation; some fat routes |
| AI/Feature Depth | 8/10 | V5.4 capabilities are genuinely impressive |
| Documentation | 7/10 | Improved as of this assessment |

---

## Identity & Access Management — Gap Detail

### Authentication (0% implemented)
- **Finding:** All 30+ API routes are fully open. No JWT, no API key, no OAuth2, no mTLS.
- **Impact:** Any user with network access can read all investigations, approve fixes, execute Kubernetes actions, and delete sessions.
- **Required:** OIDC/JWT middleware using Azure Entra ID. Token validation in FastAPI middleware before any route handler executes.
- **Priority:** P0 — nothing else in this section matters without auth.

### Authorization / RBAC (0% implemented)
- **Finding:** No role enforcement exists anywhere. All users (if any were authenticated) would have identical access.
- **Required roles:**
  - `sre` — trigger, review, approve/reject, execute investigations for their applications
  - `viewer` — read-only access to investigations and dashboards
  - `admin` — full platform access including application registration and connector management
  - `executive` — read-only access to dashboards, briefings, and post-mortems only
- **Implementation:** FastAPI `Depends()` guards per route. Role claims in JWT token.

### Attribute-Based Access Control (ABAC) (0% implemented)
- **Finding:** No application-level access scoping. An authenticated SRE can operate on any application.
- **Required:** SREs should only be able to approve/execute investigations for applications assigned to them. This requires an `application_access` junction table and application-scoped authorization checks.

### Identity in Approval Records (0% implemented)
- **Finding:** `approved_by` is accepted as a freeform query string (`?approved_by=some_name`). No identity verification.
- **Impact:** Audit trail is meaningless — any string can be submitted as the approver identity.
- **Required:** Derive approver identity from JWT `sub` or `preferred_username` claims in the authenticated request context.

### SSO (0% implemented)
- **Required:** SAML 2.0 / OIDC federation with enterprise IdPs. Azure Entra ID first (natural fit for Azure-native platform), then other IdPs via standard OIDC.

### SCIM (0% implemented)
- **Required for:** Enterprise customer user provisioning (add/remove users, assign roles from the customer's IdP).

---

## Audit & Compliance — Gap Detail

### Audit Trail
- **Finding:** The `approval_decisions` table captures approval and rejection events. `ApprovalStatus` transitions are recorded with `approved_by` (unverified string) and `approved_at`. The UI shows an "Audit Trail" section in `AuditTrailSection.tsx`.
- **Gap:** The audit trail does not capture: investigation triggers, evidence collection events, config changes, connector onboarding, user login/logout, session creation/deletion.
- **Gap:** Identity in audit records is not cryptographically bound to the authenticated user.
- **Required:** A dedicated `audit_events` table, append-only, written by a service that reads identity from the authenticated request context. Schema: `(id, event_type, actor_id, actor_email, resource_type, resource_id, timestamp, details_json)`.

### Tamper-Evident Audit Store
- **Finding:** The `CompliancePack` module (`corvin/strategy/compliance_pack.py`) generates a ZIP bundle for SOX/SOC2/ISO27001 auditors. However, the underlying event store is not tamper-evident.
- **Required:** Route audit events to Azure Event Hub (append-only) or Azure Immutable Blob Storage for WORM compliance.

### Data Retention
- **Finding:** No TTL or retention policy on any table. Investigations, evidence bundles, and chat messages accumulate indefinitely.
- **Required:** Configurable data retention policy per data category (investigations: 1 year, evidence bundles: 90 days, chat messages: 30 days). Enforced by a background job.

### GDPR Right to Erasure
- **Finding:** No data deletion API. No tenant-scoped purge.
- **Required:** `DELETE /admin/tenants/{tenant_id}/data` endpoint that cascades deletion across all tables for a given tenant.

---

## Operational Reliability — Gap Detail

### Health Check
- **Finding:** `GET /health` returns `{"status": "ok"}` unconditionally. No dependency checks.
- **Required:** Liveness probe (current behavior is fine) + Readiness probe that checks DB connectivity and at least one critical dependency.

### Distributed Tracing
- **Finding:** Zero OpenTelemetry instrumentation. No trace IDs in logs. No correlation between HTTP requests and background tasks.
- **Required:** OpenTelemetry SDK + Azure Monitor exporter. Inject trace context into all LLM calls, DB queries, and evidence adapter calls.

### Structured Logging
- **Finding:** Python `logging` module used throughout but in plain text format. No `request_id` correlation. No log levels enforced per module.
- **Required:** JSON-structured logging with `trace_id`, `request_id`, `tenant_id` (once multi-tenant), and `user_id` fields on every log line. Route to Azure Monitor Log Analytics.

### Metrics
- **Finding:** Zero Prometheus/StatsD instrumentation. No dashboards. No alerting on the platform itself.
- **Required:** Prometheus `/metrics` endpoint or OTLP push to Azure Monitor. Key metrics: investigation duration p50/p95/p99, LLM token usage per call, evidence adapter error rate, background task lag.

### Circuit Breakers
- **Finding:** Evidence adapters have bare `try/except Exception: return []` fallbacks. No circuit breaker pattern — a failed dependency causes every adapter call to timeout before falling back.
- **Required:** Circuit breaker via `pybreaker` or similar. Open circuit after N consecutive failures; half-open after timeout; track state per adapter instance.

---

## Security Controls — Gap Detail

### Credential Encryption
- **Finding:** AES-256-GCM encryption in `corvin/connectors/crypto.py` — correctly implemented. DB-stored connector credentials are encrypted at rest.
- **Gap:** `CORVIN_ENCRYPTION_KEY` must be present as an env var. No key rotation mechanism. No Azure Key Vault integration for key management.

### Secret Management
- **Finding:** All secrets are environment variables. No Azure Key Vault integration.
- **Required:** Azure Key Vault for all secrets. LLM API keys, DB passwords, service principal credentials should all be KV references, not env vars.

### Input Validation
- **Finding:** Pydantic validates all request bodies. SQLAlchemy ORM prevents SQL injection. No XSS risk in the API layer.
- **Gap:** No SSRF protection on outbound connector calls (generic_http connector can call any URL). No validation that webhook payloads are signed.

### Azure Alert Webhook Authentication
- **Finding:** `POST /triggers/azure-alert` has a `AZURE_ALERTS_WEBHOOK_SECRET` env var but the validation logic needs review.
- **Required:** HMAC signature validation on all inbound webhook payloads.

### Dependency Scanning
- **Finding:** No `dependabot.yml`. No `trivy` or `safety` in CI pipeline.
- **Required:** Dependabot for Python and npm. `trivy` container scan in CI.

---

## Recommended Target Architecture for Enterprise

```
Identity Plane:         Azure Entra ID (OIDC) ── SCIM provisioning
                              │
                              ▼
API Gateway:            Azure API Management (JWT validation, rate limiting, versioning)
                              │
                              ▼
Application Tier:       FastAPI (stateless, 3+ replicas) ── OpenTelemetry → Azure Monitor
                              │
                              ▼
Background Jobs:        Celery/ARQ workers (investigations, predictive monitor, SLO snapshots)
                              │
                              ▼
Storage:                Azure PostgreSQL Flexible Server (HA, geo-backup, PITR)
                        Azure Key Vault (all secrets and encryption keys)
                              │
                              ▼
Audit Store:            Azure Event Hub (append-only) or Azure Immutable Blob Storage
```

---

## Prioritized Remediation Sequence

1. **Remove sensitive data from git history** (TD-C3, TD-C4) — immediate, no code change
2. **Implement OIDC authentication** (TD-C1, EV2) — all routes gated before any external exposure
3. **Derive identity from JWT claims** (TD-C2) — part of EV2
4. **Add `/v1/` API prefix and rate limiting** (TD-M3, TD-M4) — needed for any API consumer
5. **Fix `get_session()` usage** (TD-H1) — prevents connection leaks under load
6. **Make investigation async** (TD-H2) — required for production throughput
7. **Fix Alembic migration numbering** (TD-H3) — required before any new team member onboards
8. **Azure Key Vault integration** (Security) — part of EV2
9. **Structured audit log table** (Compliance) — part of EV2
10. **OpenTelemetry instrumentation** (Observability) — enables production debugging

See `docs/ROADMAP.md` for the full enterprise build sequence.

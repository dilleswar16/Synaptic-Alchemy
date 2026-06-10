# Corvin — Technical Debt Register

**Last Updated:** 2026-06-10  
**Status:** Authoritative. Supersedes `docs/gaps.md` for technical debt tracking.  
**Source:** Enterprise & SaaS Readiness Assessment (2026-06-10)

See `docs/gaps.md` for SRE canon gap analysis (functional gaps, not implementation debt).

---

## Critical (Address Before Any External Deployment)

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-C1 | **No authentication on any API endpoint** | All routes in `apps/api/routes/` | Any user with network access can read all investigations, approve/reject fixes, execute Kubernetes actions | Data breach, unauthorized execution, regulatory violation | Implement OIDC/JWT middleware (Azure Entra ID) before any external exposure. All 30+ routes must be protected. |
| TD-C2 | **`approved_by` accepted as an unvalidated query string** | `apps/api/routes/investigations.py:1660` | Approval identity can be forged by any caller — audit trail is non-repudiable in name only | Non-repudiation failure; compliance violation | Derive identity from JWT token claims. Never accept identity assertions from request parameters. |
| TD-C3 | **Live Azure portal URL with tenant/subscription ID in `.env.example`** | `.env.example:78` | URL `https://portal.azure.com/457bc2c0-...` exposes an internal Azure tenant ID | Reconnaissance attack surface | Remove immediately. Rotate/audit the subscription if this repo was ever public. |
| TD-C4 | **Database backup files committed to repository** | `corvin.db`, `corvin.db.backup-20260531-140805`, `apps/web/corvin.db` | Investigation data (RCA outputs, service topology, connector configs) in version control | PII/sensitive data exposure; data governance violation | Remove from git history using `git filter-repo`. Add `*.db` and `*.db.backup*` to `.gitignore`. |

---

## High

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-H1 | **`get_session()` used as iterator bypassing context manager** | `apps/api/main.py:70-71` — `db = next(get_session())` in seed block | Session is never closed on exception — connection leak | DB pool exhaustion under any load | Replace with `with get_session() as db:` pattern. Audit all call sites for the same pattern. |
| TD-H2 | **Synchronous `engine.run()` blocks the HTTP worker thread** | `apps/api/routes/investigations.py:261` | POST /investigations blocks for the full investigation duration (30-90s LLM call) | All API workers stall under concurrent investigations | Offload to a background queue (Celery/ARQ). Return HTTP 202 Accepted + `request_id`. Client polls or subscribes via SSE. |
| TD-H3 | **Duplicate Alembic migration version numbers** | `alembic/versions/` — three files prefixed `0012_*` | Alembic cannot deterministically apply migrations; DB state is ambiguous | Silent data loss or migration failure on fresh deployment | Renumber conflicting migrations with sequential prefixes. Add `alembic check` as a CI gate. |
| TD-H4 | **SQLite manual migration shadow system** | `corvin/storage/db.py:109-162` — `_SQLITE_COLUMN_MIGRATIONS` list | Must be kept in sync with Alembic by hand; already shows drift potential | Schema divergence between dev (SQLite) and prod (Postgres) | Remove `_SQLITE_COLUMN_MIGRATIONS`. Document SQLite as test-only. Tests should not depend on schema migration behaviour. |
| TD-H5 | **MetLife branding hardcoded in frontend assets** | `apps/web/public/metlife-logo.svg`, `apps/web/public/metlife-logo-*` | Platform cannot be white-labeled or productized | Trademark risk; blocks SaaS packaging | Extract all customer-specific assets to a configurable theme directory. Logo URL should come from tenant config. |
| TD-H6 | **CORS wildcard (`*`) disables protection** | `apps/api/main.py:113-126` | When `CORVIN_ALLOWED_ORIGINS=*`, CORS protection is completely disabled | CSRF-style attacks; XSS amplification | Enforce an explicit origin allowlist in all environments. Remove wildcard support from production config path. |
| TD-H7 | **`PredictiveMonitor` and SLO monitor start per-worker** | `apps/api/main.py:83-95` | Multiple Uvicorn workers each start their own background tasks — duplicate DB writes, duplicate LLM calls | Data integrity issues; 2x–Nx LLM cost | Implement leader election (Redis lock or Postgres advisory lock) or run background tasks in a dedicated worker/process separate from the API. |

---

## Medium

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-M1 | **Business logic computed inline in route handlers** | `investigations.py:435` (DORA), `investigations.py:413` (ROI) | Cannot be reused, tested in isolation, or cached | Regression risk on route changes | Extract to `AnalyticsService` in `corvin/strategy/`. Routes should call the service and return the result. |
| TD-M2 | **`get_topology_live` — 400+ line route handler** | `investigations.py:620` | Impossible to unit test; dense fallback ladder with multiple bare `except Exception` blocks | Silent error swallowing; correctness bugs invisible in production | Extract to `TopologyService`. The route handler should be <30 lines. |
| TD-M3 | **No API versioning** | `apps/api/main.py:128-136` — all routes at root prefix | Breaking changes immediately break all clients | No safe upgrade path for enterprise customers | Add `/v1/` prefix to all routes via a versioned router. Implement content negotiation for transition. |
| TD-M4 | **No rate limiting** | All routes | Investigation endpoint with LLM call has zero throttle | DoS via alert flood; uncontrolled LLM cost | Add `slowapi` rate-limiting middleware. Limit `/investigations` POST per IP and per service name. |
| TD-M5 | **Hardcoded currency and locale in policy config** | `config/policies/investigation.yaml:32-48` — `GBP`, `en-GB-RyanNeural` | Platform uses MetLife/UK assumptions for all deployments | Multi-region/multi-customer deployment blocked | Move currency, locale, voice name to per-application or per-tenant configuration table. |
| TD-M6 | **Demo data hardcoded in frontend source** | `apps/web/src/data/demoAlerts.ts` | Demo mode cannot be disabled; test data ships in the production bundle | Customer data confusion; bundle bloat | Serve demo scenarios from the `/triggers/simulate` API endpoint. Remove static demo data from frontend. |
| TD-M7 | **Application version frozen at `0.1.0`** | `apps/api/main.py:110` | Version mismatch with V5.4 actual feature state; cannot diff API capabilities between deployments | Support and debugging confusion | Implement semantic versioning. Read version from `pyproject.toml` at startup. Tie version bumps to git tags via CI. |
| TD-M8 | **Dual runbook storage (DB + disk) with overlapping responsibility** | `corvin/core/knowledge_loader.py` | Two sources of truth; runbooks silently diverge between environments | Stale runbooks injected into LLM prompts | Commit to DB-only as the write target. One-time migration of all disk runbooks to `RunbookRow`. Keep disk as a read-only cold backup. |
| TD-M9 | **No structured error response contract** | All route handlers — freeform `HTTPException(detail=...)` strings | Clients cannot programmatically handle error types; any error message reword is a breaking change | Fragile client error handling | Adopt RFC 7807 Problem Details (`application/problem+json`) for all error responses. Define an error code enum. |
| TD-M10 | **Presentation files, decks, and notes committed to repo root** | Root directory — multiple `.html`, `.pptx`, `.md` files | Repo size; developer onboarding confusion; accidental exposure of internal sales materials | Not a correctness risk but a governance risk | Files archived to `docs/archive/presentations/` as part of this cleanup. |

---

## Low

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-L1 | **`litellm.drop_params = True` set globally at module import** | `corvin/strategy/rca_generator.py:25` | Silently drops unsupported params for all LLM calls in all modules sharing the process | Debugging difficulty; unexpected model behaviour | Move to per-call configuration or per-request LiteLLM client instantiation. |
| TD-L2 | **`pyproject.toml` and `requirements.txt` coexist** | Root directory | Duplicate dependency specifications; risk of version divergence between pip and pyproject | Dependency conflicts in CI | Consolidate to `pyproject.toml` only. Remove `requirements.txt`. Update CI to use `pip install -e ".[dev]"`. |
| TD-L3 | **SQLite database file in `apps/web/` directory** | `apps/web/corvin.db` | Database co-located with frontend assets — no logical reason | Developer confusion; accidental frontend reference to backend data | Remove. Add `apps/web/*.db` to `.gitignore`. |
| TD-L4 | **Background task cancellation swallows errors silently** | `apps/api/main.py:97-103` | Background task failures (predictive monitor, SLO snapshot) are invisible to operators | Production silent failures | Add structured error logging on cancellation and any exception caught in the task loop. |
| TD-L5 | **`startup_test.py` and `lifespan_test.py` in repository root** | Root directory | Test files outside the `tests/` directory — ignored by the default pytest invocation | False confidence in CI | Move to `tests/`. Update pytest `testpaths` in `pyproject.toml`. |

---

## Debt Introduced vs. Suppression Window

The investigation alert suppression window (`alert_suppression_window_minutes: 15` in `investigation.yaml`) is a correct design decision — it prevents alert storms. However, it is currently only configurable globally, not per-service. High-volume services may need a longer window; newly onboarded services may need zero suppression during initial tuning.

**Recommendation:** Make suppression window configurable at the `ApplicationEnvironmentRow` level.

---

## Resolved Debt (for historical reference)

| Debt | Resolution | Version |
|------|-----------|---------|
| DB runbooks ignored by prompt builder (service_name=None bug) | Fixed — `prompt_builder.py` now passes `service_name` to both `load_site_knowledge()` and `load_matching_runbooks()` | V5.4 |
| Hardcoded MetLife service topology in code | Replaced with DB-driven `ApplicationServiceRow` + AKS connector config | V4.5 |
| In-memory runbook session state lost on restart | Replaced with `RunbookSessionRow` in Postgres | V5.3 |
| `response_format: json_schema` causing Azure OpenAI buffering in streaming mode | Removed from streaming path; `json_object` mode only | V2.x |

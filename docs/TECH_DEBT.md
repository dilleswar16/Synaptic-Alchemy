# Corvin — Technical Debt Register

**Last Updated:** 2026-06-12  
**Status:** Authoritative. Supersedes `docs/gaps.md` for technical debt tracking.  
**Source:** Enterprise & SaaS Readiness Assessment (2026-06-10)

See `docs/gaps.md` for SRE canon gap analysis (functional gaps, not implementation debt).

---

## Critical (Address Before Any External Deployment)

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-C1 | **No authentication on any API endpoint** | All routes in `apps/api/routes/` | Any user with network access can read all investigations, approve/reject fixes, execute Kubernetes actions | Data breach, unauthorized execution, regulatory violation | Implement OIDC/JWT middleware (Azure Entra ID) before any external exposure. All 30+ routes must be protected. |
| TD-C2 | **`approved_by` accepted as an unvalidated query string** | `apps/api/routes/investigations.py:1660` | Approval identity can be forged by any caller — audit trail is non-repudiable in name only | Non-repudiation failure; compliance violation | Derive identity from JWT token claims. Never accept identity assertions from request parameters. |
| TD-C3 | ~~**Live Azure portal URL with tenant/subscription ID in `.env.example`**~~ | `.env.example` | **Remediated 2026-06-10 (PB-004)** — stray URL removed. |
| TD-C4 | **Database backup files committed to repository** | `corvin.db`, `corvin.db.backup-20260531-140805`, `apps/web/corvin.db` | Investigation data (RCA outputs, service topology, connector configs) in version control | PII/sensitive data exposure; data governance violation | Remove from git history using `git filter-repo`. Add `*.db` and `*.db.backup*` to `.gitignore`. |

---

## High

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-H1 | ~~**`get_session()` used as iterator bypassing context manager**~~ | `apps/api/main.py` | **Resolved 2026-06-12** — Worse than documented: `get_session()` is a `@contextmanager`, so `next(get_session())` raised `TypeError`, silently swallowed by the seed block's broad `except` — demo seeding never worked with `CORVIN_DEMO_MODE=true`. Replaced with `with get_session() as db:`. Audit confirmed this was the only iterator-style call site. Regression test added in `tests/api/test_observability_and_versioning.py`. |
| TD-H2 | **Synchronous `engine.run()` blocks the HTTP worker thread** | `apps/api/routes/investigations.py:261` | POST /investigations blocks for the full investigation duration (30-90s LLM call) | All API workers stall under concurrent investigations | Offload to a background queue (Celery/ARQ). Return HTTP 202 Accepted + `request_id`. Client polls or subscribes via SSE. |
| TD-H3 | ~~**Duplicate Alembic migration version numbers**~~ | `alembic/versions/` | **Resolved 2026-06-11** — Re-investigated during Sprint 2. All three `0012_*` files have unique revision IDs; `0013_add_acknowledged_status` already uses `down_revision = (tuple)` as a proper merge migration. `alembic heads` reports a single head (`0024`). New migrations generate cleanly from `0024`. No action required. |
| TD-H4 | **SQLite manual migration shadow system** | `corvin/storage/db.py:109-162` — `_SQLITE_COLUMN_MIGRATIONS` list | Must be kept in sync with Alembic by hand; already shows drift potential | Schema divergence between dev (SQLite) and prod (Postgres) | Remove `_SQLITE_COLUMN_MIGRATIONS`. Document SQLite as test-only. Tests should not depend on schema migration behaviour. |
| TD-H5 | ~~**MetLife branding hardcoded in frontend assets**~~ | `apps/web/public/` | **Resolved 2026-06-11 (PB-001, PB-019)** -- MetLife logo removed; `corvin-logo.svg` added; `GET /config/branding` API serves logo URL from env var. |
| TD-H6 | **CORS wildcard (`*`) disables protection** | `apps/api/main.py` | When `CORVIN_ALLOWED_ORIGINS=*`, CORS protection is completely disabled | CSRF-style attacks; XSS amplification | Full hardening deferred by decision 2026-06-12. **Mitigation shipped:** startup logs a loud warning whenever the wildcard is configured. Enforce an explicit allowlist before any non-local deployment. |
| TD-H7 | **`PredictiveMonitor` and SLO monitor start per-worker** | `apps/api/main.py` | Multiple Uvicorn workers each start their own background tasks — duplicate DB writes, duplicate LLM calls | Data integrity issues; 2x–Nx LLM cost | Leader election deferred by decision 2026-06-12 (pairs with TD-H2 worker design). **Mitigation shipped:** startup warns when `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1. Run a single API worker until this lands. |

---

## Medium

| ID | Issue | Location | Impact | Risk | Remediation |
|----|-------|----------|--------|------|-------------|
| TD-M1 | **Business logic computed inline in route handlers** | `investigations.py:435` (DORA), `investigations.py:413` (ROI) | Cannot be reused, tested in isolation, or cached | Regression risk on route changes | Extract to `AnalyticsService` in `corvin/strategy/`. Routes should call the service and return the result. |
| TD-M2 | **`get_topology_live` — 400+ line route handler** | `investigations.py:620` | Impossible to unit test; dense fallback ladder with multiple bare `except Exception` blocks | Silent error swallowing; correctness bugs invisible in production | Extract to `TopologyService`. The route handler should be <30 lines. |
| TD-M3 | ~~**No API versioning**~~ | `apps/api/middleware.py` | **Resolved 2026-06-12** — `ApiVersionMiddleware` serves every endpoint under `/v1/...` (canonical for new clients) while root paths remain for backward compatibility with the existing frontend. All responses carry `X-API-Version: 1`. Pure ASGI — does not interfere with SSE streaming. |
| TD-M4 | **No rate limiting** | All routes | Investigation endpoint with LLM call has zero throttle | DoS via alert flood; uncontrolled LLM cost | Decision 2026-06-12: throttling is delegated to the APIM gateway in front of the API (Azure-native). **Deployment requirement:** backend must not be directly reachable — APIM must be the only network entry point, enforced via VNet/access restrictions. No application-level limiter planned. |
| TD-M5 | ~~**Hardcoded currency and locale in policy config**~~ | `config/policies/investigation.yaml` | **Resolved 2026-06-11 (PB-009, PB-010)** — `engineer_hourly_rate_gbp` renamed to `engineer_hourly_rate`; `currency_code`, `locale`, `tts_voice_name` added as per-application columns (migration 0025). |
| TD-M6 | **Demo data hardcoded in frontend source** | `apps/web/src/data/demoAlerts.ts` | Demo mode cannot be disabled; test data ships in the production bundle | Customer data confusion; bundle bloat | Serve demo scenarios from the `/triggers/simulate` API endpoint. Remove static demo data from frontend. |
| TD-M7 | **Application version frozen at `0.1.0`** | `apps/api/main.py:110` | Version mismatch with V5.4 actual feature state; cannot diff API capabilities between deployments | Support and debugging confusion | Implement semantic versioning. Read version from `pyproject.toml` at startup. Tie version bumps to git tags via CI. |
| TD-M8 | **Dual runbook storage (DB + disk) with overlapping responsibility** | `corvin/core/knowledge_loader.py` | Two sources of truth; runbooks silently diverge between environments | Stale runbooks injected into LLM prompts | Commit to DB-only as the write target. One-time migration of all disk runbooks to `RunbookRow`. Keep disk as a read-only cold backup. |
| TD-M9 | ~~**No structured error response contract**~~ | `apps/api/errors.py` | **Resolved 2026-06-12** — App-level exception handlers convert every HTTPException, validation failure, and unhandled error into RFC 7807 `application/problem+json` (`type/title/status/detail/instance/request_id`). `detail` remains a plain string so existing clients reading `payload.detail` are unaffected; validation errors expose field breakdown in an `errors` extension. Error code enum still open for a later pass. |
| TD-M10 | **Presentation files, decks, and notes committed to repo root** | Root directory — multiple `.html`, `.pptx`, `.md` files | Repo size; developer onboarding confusion; accidental exposure of internal sales materials | Not a correctness risk but a governance risk | Files archived to `docs/archive/presentations/` as part of this cleanup. |
| TD-M11 | **ServiceNow route has broken import** | `apps/api/routes/investigations.py` — `from corvin.storage.database import get_session` inside `sync_servicenow()` | Module `corvin.storage.database` does not exist — ServiceNow sync route raises `ModuleNotFoundError` on every call | Route is dead code; `test_sync_endpoints_exist` always fails | Replace `from corvin.storage.database import get_session` with the correct import (likely `from corvin.storage.repository import get_session`). Found during Sprint 1 testing 2026-06-10. |
| TD-M12 | ~~**`FakeKnowledgeLoader` does not match current `KnowledgeLoader` interface**~~ | `tests/slices/test_slice5_knowledge_injection.py`, `tests/slices/test_slice_v3_incident_memory.py` | **Resolved 2026-06-12** — Both fakes updated to accept the `service_name` kwarg, matching `KnowledgeLoader`. All 18 affected tests pass; the `--ignore=tests/slices/test_slice5_knowledge_injection.py` workaround is no longer needed. |
| TD-M14 | ~~**Test suite not isolated — ran against live `corvin.db` and real delivery channels**~~ | `tests/conftest.py` (new) | **Resolved 2026-06-12** — Suite previously (a) attempted real RCA email delivery on every `POST /investigations/` test (hung on restricted networks, would spam real inboxes), (b) wrote fixture penalty rows into the live `corvin.db`, (c) appended fake `penalty-*.md` files to `knowledge/learnings/` which were injected into real LLM prompts. New root conftest force-disables email, points the suite at a throwaway temp SQLite DB, and no-ops disk learning writes. **Follow-up 2026-06-12:** owner chose to disable the penalty feature entirely (`prediction_penalty_enabled: false` in `config/policies/investigation.yaml`) rather than clean repeatedly — both the write path (`penalize_prediction`) and the prompt-injection read path are gated; `knowledge/learnings/` is now empty. ~180 fixture-service penalty rows remain in live `corvin.db` but are inert (injection gated off); real fundapis/partnerapis rows preserved. |
| TD-M13 | ~~**2 tests in `test_ado_wiki_adapter.py` patch a renamed function**~~ | `tests/adapters/test_ado_wiki_adapter.py:284,305` | **Fixed 2026-06-11** — Tests patched `load_config` (renamed to `resolve_outbound_connector_config` in commit `8bfa405`). Updated to patch `resolve_ado_wiki_config_for_service`. |

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
| Circular import: `engine` → `enrichment_service` → `aks_adapter` → `connectors` → `aks_adapter` | Fixed 2026-06-12 — `corvin/connectors/aks.py` now imports `AKSAdapter` lazily inside `test_connection()`. Direct `InvestigationEngine` import (CLI, scripts) no longer fails depending on import order. | Phase 2-lite |
| Accumulated test drift: 34 tests asserting superseded contracts (`_build_card` signature, bot environment prompt, lookback default, stream `environment` param, `requires_approval` policy, `_client_mode` attr) | Fixed 2026-06-12 — tests updated to the current intended contracts; one new test covers the all-informational acknowledge path. | Phase 2-lite |
| No structured logging / no request correlation | Resolved 2026-06-12 — `corvin/core/logging_config.py` (JSON formatter) + `corvin/core/request_context.py` (request-ID ContextVar) + `RequestContextMiddleware` (X-Request-ID header, access log line per request). `CORVIN_LOG_FORMAT=text` for dev. | Phase 2-lite |
| DB runbooks ignored by prompt builder (service_name=None bug) | Fixed — `prompt_builder.py` now passes `service_name` to both `load_site_knowledge()` and `load_matching_runbooks()` | V5.4 |
| Hardcoded MetLife service topology in code | Replaced with DB-driven `ApplicationServiceRow` + AKS connector config | V4.5 |
| In-memory runbook session state lost on restart | Replaced with `RunbookSessionRow` in Postgres | V5.3 |
| `response_format: json_schema` causing Azure OpenAI buffering in streaming mode | Removed from streaming path; `json_object` mode only | V2.x |

# 16 — Hardening plan (review findings → fixes → features → UI)

Started 2026-11-20 after a full code review. This document tracks what was found, what was agreed, and the status of
each fix. Update the status column as work lands; record design decisions in `09_LEARNINGS_LOG.md`.

## Context and agreed decisions

- **Mocks are intentional.** SQLite, the mock LLM and simulated integrations stand in while the infra team provisions
  Azure (Azure SQL, Key Vault, APIM, AKS). The goal is code that switches to live resources by configuration only.
- **APIM owns the edge.** Rate limiting, request size limits and edge security are APIM policies, so app-level rate
  limiting is not extended. The in-process limiter stays as a local convenience only.
- **Git.** Work happens on the local branch `keigan-hardening` (baseline commit `3cf95ef`). It is not pushed unless asked.
- **Schema changes are incremental, with Alembic as the single source of truth.** How the schema is managed today:
  local SQLite is created from the entities at start-up (`AUTO_CREATE_SCHEMA=true`); a new Azure SQL database is created
  once from `database/azure_sql/01-06` (script 05 stamps the Alembic baseline `94692c828bd3`); every later release runs
  `alembic upgrade head` from the Helm pre-upgrade job. So each schema change gets:
  1. a new Alembic revision (the initial migration is never rewritten);
  2. regenerated `02-04` scripts (`backend/scripts/generate_azure_sql_ddl.py`) and the `05` stamp moved to the new head, so a fresh database starts current;
  3. a delta script generated from Alembic offline mode (`--sql`) for DBAs who apply changes by hand. It is never hand-written, so it cannot drift from or double-apply with the Helm job;
  4. a passing drift test (`alembic upgrade head` on an empty database must match the entities).
- **Engineering standards.** Proper fixes, no workarounds; no hard-coded values (settings or resource catalogs); modular code following existing patterns; test first for every fix.
- **Prompt review is static for now.** Prompts and guardrails are reviewed by reading code and running against the mock.
  A live-model eval waits until an LLM endpoint is available.
- **Tests: backend pytest first.** Frontend unit and e2e tests come later. Ground rule 8 in `00_INDEX.md` is updated.

## Order of work

1. Baseline: run the app, seed, capture every screen (done, see below).
2. Backend pytest suite that pins today's behaviour on the core paths, before any fix.
3. Correctness and security fixes (table below), each with a test, an Alembic revision and SQL script where the schema changes.
4. Independent prompt and security review.
5. Features, then UI polish.

## Baseline (2026-11-20)

- Seed: 5 applications, 19 services, about 34 s.
- `frontend/scripts/capture-screens.mjs`: 31/31 screens, 0 console, page or API errors at 1440 px (light theme).
- Phone width (390 px): every screen renders 491 px wide, so the page scrolls horizontally by about 100 px. Shell-level cause, to fix in the UI phase.
- Visible copy issues: raw enum values in the UI ("Tier tier_2" on Home), wrong plural ("1 occurrences" on Alerts).
- No automated tests exist (backend or frontend).

## Findings and status

Status: ⬜ open · 🔄 in progress · ✅ fixed and tested · ➖ not doing (reason given)

| # | Finding | Where | Status |
|---|---|---|---|
| H1 | Custom SLI KQL runs without query validation | `services/sli_measurement_reader.py:88-89` | ✅ (stream A, tracked as V14): custom SLI KQL is validated on save and again before every run; a stored bad query fails only that SLI |
| H2 | KQL validator checks only tables before the first pipe, plus `join`/`lookup`; a later `| union <table>` is not checked (`find` is already rejected by the allowlist, verified by test) | `utils/query_safety.py:79-89` | ✅ (stream A, tracked as V4): KQL tokenizer checks every table reference; tests in `tests/unit/utils/test_query_safety.py` |
| H3 | Duplicate alerts across pods: dedup relies on an in-process lock; fingerprint index not unique | `services/alert_pipeline_service.py:30,89`, `entities/alert_entities.py:48` | ✅ (stream E): unique index `uq_alert_open_fingerprint` (one `firing` alert per application and fingerprint); the losing pod merges into the winner in a savepoint. Tests in `test_alert_pipeline_service.py` |
| H4 | Job deduplication is check-then-insert with no unique constraint | `workers/job_queue.py:44-58` | ✅ (stream E): unique index on the active deduplication key; enqueue returns the winner's job. Leasing now uses a guarded UPDATE because SQLAlchemy emits no row lock for SQL Server |
| H5 | Job lease (10 min) is never renewed; a long investigation can be run twice | `workers/job_queue.py:25` | ✅ (stream E): a heartbeat renews the lease while a handler runs (`JOB_LEASE_RENEWAL_INTERVAL_SECONDS`) |
| H6 | Local auth (passwordless, any user incl. admin) is only blocked when `ENVIRONMENT=prod`; default signing secret is accepted | `config/settings.py:96,213-227` | ✅ (stream C, tracked as V15) |
| H7 | App roles also match Entra group display names (not unique, mutable) | `services/authorization_service.py:61-71` | ✅ (stream B): in Entra mode groups match by object id only; an app without ids is denied with a message that says to run "Check in Entra"; `go_live` needs both ids |
| H8 | Entra token accepted when `tid` is absent | `services/authentication_service.py:168` | ✅ (stream C): `tid` must equal `ENTRA_TENANT_ID`; tests in `tests/unit/services/test_authentication_service.py` |
| H9 | Uvicorn trusts forwarded headers from any IP | `deploy/docker/backend.Dockerfile:34` | ✅ (stream C): uvicorn reads `FORWARDED_ALLOW_IPS` (image default `127.0.0.1`); Helm `api.forwardedAllowIps` sets it and refuses `*`. Not rendered with helm yet (see go-live prerequisites) |
| H10 | Retention never removes incidents, investigations or evidence although `INCIDENT_RETENTION_DAYS` exists | `services/administration_service.py:219-237` | ✅ (stream E): `services/incident_retention.py` removes expired incidents and investigations in batches, children first |
| H11 | Many-to-many links stored as JSON id lists (incident, investigation and alert-group services; conversation applications; maintenance windows) | `entities/incident_entities.py:53,82,208`, `entities/alert_entities.py:103,133` | ⬜ |
| H12 | `application_id` without a foreign key on alert, SLO and intelligence tables (orphans on delete) | `entities/alert_entities.py`, `entities/slo_entities.py` | ⬜ |
| H13 | No CHECK constraints on status columns | all entities | ⬜ |
| H14 | Two-way soft links between alert group, investigation and incident can disagree | `entities/alert_entities.py:108-109`, `entities/incident_entities.py:71-72` | ⬜ |
| H15 | SLI list runs two queries per SLI | `services/slo_service.py:308-319` | ✅ (stream A): SLI list uses 3 queries instead of 2 per SLI; query-count test |
| H16 | Backend has no dependency lock file; Docker builds from version ranges | `backend/pyproject.toml` | ✅ (stream C): `backend/requirements.lock` (pinned, sha256 hashes, includes `azuresql` extra); the image installs only from it with `--require-hashes --only-binary=:all:`. Regenerate with the command in the lock file header after changing `pyproject.toml`. Docker build not run yet |
| H17 | Contrast below WCAG AA: `text-subtle` 3.25:1, success text on success background 4.17:1 | `frontend/src/styles/tokens.css:47,65-67` | ⬜ |
| H18 | Horizontal scroll at phone width; raw enum labels; plural bug | frontend shell and pages | ⬜ |
| H19 | Dead or leftover files: `app/PlaceholderPage.tsx`, `frontend/FOUNDATION_READY.md` | frontend | ⬜ |
| H20 | `es-MX` locale has 12 of 15 namespaces (auth, common, navigation missing) | `frontend/src/i18n/locales/es-MX` | ⬜ |
| H21 | No check that Alembic migrations, entities and the Azure SQL scripts agree (three copies of the schema) | `backend/migrations`, `database/azure_sql` | ✅ (stream E): `tests/integration/migrations/test_schema_drift.py` compares Alembic, entities and the generated Azure SQL scripts and delta scripts |
| R1 | In-process rate limiter and Content-Length-only body check | `security/security_middleware.py` | ➖ APIM policies own this |

## Security and prompt review findings (V-series)

Independent review, full detail and proofs in [`17_SECURITY_AND_PROMPT_REVIEW.md`](17_SECURITY_AND_PROMPT_REVIEW.md).
Where a V-item covers an H-item above, the V-item is the one tracked (noted in the last column).

| # | Severity | Finding | Status |
|---|---|---|---|
| V1 | Critical | Webhook accepted an HMAC signature forged with the all-zero placeholder key (no token needed) | ✅ fixed: only real secret hashes are candidates; tests in `tests/unit/services/test_alert_source_service.py` |
| V1b | Medium | HMAC key is the stored secret hash, so database read access is enough to sign alerts | ✅ fixed (stream E): signing uses the plaintext secret kept in the secret store (name in `webhook_secret_name`); the stored hash can no longer sign. Legacy sources are token-only until their secret is rotated |
| V3 | High | AI-written reports, emails and Teams comments go out without human approval (`AUTO_SEND_PRELIMINARY_REPORT=true`) | ➖ accepted by design (2026-11-20): Keigan only informs, it does not act, so auto-send stays. The content itself is still made safe through V7 (untrusted input) and V8 (link filtering on every outgoing field) |
| V2 | High | A `requested` app's creator is its admin and can point log sources at another team's workspace (confused deputy) | ✅ fixed (stream B): telemetry is read only for approved applications and only from resources inside the application's verified components (`services/telemetry_access_policy.py`, enforced in the gateway, in chat and at save time) |
| V4 | High | KQL validator bypasses: later `union`/`join`/`lookup`/`toscalar`; a `"//"` string hides the rest of the line from all checks | ✅ fixed (stream A, covers H2): see H2 |
| V5 | High | SPL: no index restriction, deny-list instead of allow-list, `tstats` unbounded, no API time bounds | ✅ fixed (stream A): SPL allow-list from `catalogs/query_safety.yaml`, one index per log source, bounded `tstats`, API time bounds |
| V7 | High | Uploaded knowledge, runbooks, prior RCAs and the chat agent are treated as trusted prompt input | ⬜ |
| V14 | Medium | Custom SLI KQL runs without validation | ✅ (stream A, = H1) |
| V15 | Medium | Default signing secret accepted outside prod; local auth allowed in dev/test | ✅ fixed (stream C, covers H6): `AUTH_MODE=local` and default or short secrets are refused unless `ENVIRONMENT` is `local` or `test`; the secret store no longer derives its key from the signing secret outside local/test. Tests in `tests/unit/config/test_settings.py`, `tests/unit/integrations/test_secret_store.py` |
| V13 | Medium | Teams bot answers (and runs log queries for) anyone in the chat; tenant not checked | ⬜ |
| V8 | Medium | Link filter bypassable and missing on many AI outputs; markdown images render | ⬜ |
| V11 | Medium | PII masker gaps (full-width text, JP numbers without separators, tokens, snake_case keys) | ✅ fixed (stream F): NFKC normalisation, new catalog patterns (JP/international phones, IPv6, GitHub/Slack/sk- tokens, Basic auth, URL credentials, password assignments), normalised JSON keys, My Number check digit; 47 tests in `tests/unit/utils/test_pii_masker.py`. Accepted residuals: masking errs on the safe side (e.g. `password: required` is masked); header rule expects one space after `Authorization:` |
| V12 | Medium | Chat history, activity-log callers, Teams names and alert rule names reach storage or the LLM unmasked | 🔄 done: activity-log callers and descriptions (A), alert rule names (E). Open: chat history and Teams names (stream D). Not masked on purpose: `rule_id`, `resource_ref`, `service_hint`, `link` (fingerprints, mute rules and URLs need them verbatim) |
| V16 | Medium | SSRF and credential redirect: changing a connection's endpoint keeps its stored credential; no egress policy | ✅ fixed (stream B): outbound URL policy (https only, no private or internal addresses after DNS, allow and deny lists from `OUTBOUND_*`); changing an endpoint or sign-in method deletes the stored credential. Egress NetworkPolicy from stream C |
| V6 | Medium | Elastic script check bypassable with JSON unicode escapes; size not validated | ✅ fixed (stream A): Elastic query is checked as parsed JSON (forbidden keys, size clamp, depth limit) |
| V9 | Medium | Command risk classifier misses `kubectl -n x delete`, `terraform destroy`, SQL `DELETE` | ⬜ |
| V10 | Medium | Planner queries reuse the investigation window for the baseline, so they always look "new" | ✅ fixed (stream A): the baseline query is hardened against the baseline window |
| V17 | Low | Token budget skipped in the chat agent and multi-app chat; manual investigation window not clamped | ⬜ |
| V18 | Low | Sanitizer misses Unicode tag characters; injection detector easy to evade (advisory only) | ⬜ |
| V19 | Low | Upstream error bodies shown to users | 🔄 done: log tool clients and SLI proposals (A). Open: other callers (stream D) |
| V20 | Low | Citation validation inconsistent with prompts (`K#` stripped or unchecked) | ⬜ |
| V21 | Low | Webhook `?token=` ends up in access logs; needs APIM / ingress log redaction | ⬜ (infra) |
| V22 | Low | Request bodies can set arbitrary secret-name pointers | ✅ fixed (stream B): clients can no longer set secret-name pointers; credentials are write-only (`credentialValue`) and stored under a generated name |
| S1 | Medium | Teams bot: the token's `serviceurl` claim was not bound to the activity, so a valid token could send Keigan's bot token to any host | ✅ fixed (stream C): inbound `serviceurl` must equal the activity `serviceUrl` and be https on `BOT_FRAMEWORK_SERVICE_URL_HOST_PATTERNS`; outbound `send_activity` re-checks every URL. Tests in `tests/unit/integrations/test_bot_framework_client.py`, `tests/integration/controllers/test_teams_bot_controller.py` |
| S5 | Medium | Entra tokens without Keigan's delegated scope (or app-only tokens) were accepted as users | ✅ fixed (stream C): `scp` must contain `ENTRA_REQUIRED_DELEGATED_SCOPE` (default: last part of `ENTRA_API_SCOPE`), or `roles` must contain one of `ENTRA_ALLOWED_APP_ROLES` (empty by default); otherwise 403 with a plain message |

Prompt-quality notes per prompt are in doc 17 ("Prompt quality") and are handled with V7 and V20.

## Priority order (agreed working order)

1. V1 ✅ → V2 → V4 + V14 → V5 → V7 → V15 → V13 (security first: these are reachable without special access)
2. H3, H4, H5 (multi-pod correctness; schema changes through Alembic)
3. V8, V11, V12, V16, V6, V9, V10, H7, H8, H9, H10
4. Data model H11-H14, H21 drift check, H15, H16
5. Remaining low items, then features, then UI (H17-H20)

## Execution (parallel, by file ownership)

Started 2026-11-20. Each workstream runs in its own git worktree with a fixed set of files, works test-first, and is merged
into `keigan-hardening` by the lead after review. Only the lead edits `My Plans/`. Only workstream E changes the schema.

**Wave 1**

| Stream | Scope | Findings |
|---|---|---|
| A | Query safety: validators, SLI queries, evidence planner, log tool clients | V4/H2, V14/H1, V5, V6, V10, S2, H15, parts of V12 and V19 |
| B | Tenancy and access: approved-apps-only telemetry, log-source ownership, outbound URL policy | V2, H7, V16, V22 |
| C | Authentication, configuration, deployment | V15/H6, H8, S1, S5, H9, H16, egress NetworkPolicy |
| D | Prompt and AI-output safety, Teams bot access | V7, V8, V9, V12, V13, V17, V18, V19, V20, prompt quality |
| E | Job queue, alert pipeline, all schema changes (Alembic + Azure SQL scripts + drift test) | H3, H4, H5, H10, H21, V1b, part of V12 |
| F | PII masking patterns | V11 |
| G | Frontend: phone width, labels and plurals, contrast, safe markdown, locales, dead files | H17, H18, H19, H20, V8 (UI) |

**Wave 2** (after wave 1 is merged): data model H11-H14 (join tables, foreign keys, CHECK constraints, soft links),
an error-handling sweep across the remaining services, wiring any cross-stream follow-ups the wave-1 reports list,
then an independent review of the combined change and a full smoke run (seed, all screens, test suite).

**Wave 1 progress**

| Stream | Status |
|---|---|
| A | ✅ merged |
| B | ✅ merged |
| C | ✅ merged (166 passed, 3 xfailed after merge) |
| D | 🔄 running |
| E | ✅ merged (556 passed after merge, no xfails left) |
| F | ✅ merged |
| G | 🔄 running |

### Follow-ups reported by the streams

| From | Follow-up | Owner / status |
|---|---|---|
| A | Chat passes the log source scope to the validator and shows the model a "Query limits" section; offline mock no longer writes `index=*` | ✅ done by the lead after merge |
| A | `investigation_graph.planner_node` must add `PromptSection("Query limits per service", EvidenceService.describe_query_limits_for_planner(...))` and pass its `masking_context` to `collect_change_evidence` | ⬜ after stream D merges (D owns the file) |
| A | Chat cannot-answer path: `ChatQueryResult` allows an empty `query_text` with an `explanation`, and chat shows it instead of "The query is empty or too long." | ⬜ wave 2 |
| A | Review the SLI table list in `catalogs/query_safety.yaml` (`kql.sli_allowed_tables`) | ⬜ owner review |
| B | Frontend `IntegrationCard.tsx` still shows a `credential_secret_name` field; replace it with a write-only `credentialValue` password field | ⬜ frontend task after stream G merges |
| B | `catalogs/integration_field_schemas.yaml`: replace the `credential_secret_name` fields (CMDB, EI portal, knowledge) with a secret input | ⬜ wave 2 |
| B | Apply the outbound URL policy to integration `base_url` fields when the CMDB, EI portal and knowledge readers are built | ⬜ with those features |
| B | `MicrosoftGraphClient.find_group` takes the first group with a matching name; it must refuse to link when two groups share the name | ⬜ wave 2 |
| B | The access policy opens a short DB session per telemetry call; consider a per-request scope cache | ⬜ optional, measure first |
| E | `03_DATABASE_DESIGN.md`, `15_ENTITY_RELATIONSHIP_DIAGRAM.md`, `05_API_CONTRACT.md` still describe the old `alert_source` columns and signature wording | ⬜ docs pass at the end of wave 2 |
| E | SQL Server leasing and the H3 race were verified by compiling for mssql and on SQLite only | ⬜ infra go-live check against real Azure SQL |
| all | New settings: `OUTBOUND_ALLOWED_HOSTS`, `OUTBOUND_DENIED_HOST_SUFFIXES`, `WORKSPACE_IDENTITY_CACHE_SECONDS`, `JOB_LEASE_DURATION_SECONDS`, `JOB_LEASE_RENEWAL_INTERVAL_SECONDS`, `WORKER_HEARTBEAT_INTERVAL_SECONDS`, `RETENTION_DELETE_BATCH_SIZE` (all in `backend/.env.example`); query limits live in `keigan/resources/catalogs/query_safety.yaml` | ✅ documented |

Schema: three Alembic revisions on top of `94692c828bd3` (`89afa8e088ba`, `1fa7018ae4d6`, `3be32fbc3e37`), Azure SQL scripts 02-04 regenerated,
the 05 stamp moved to `3be32fbc3e37`, and delta scripts for existing databases are in `database/azure_sql/migrations/`.

### Go-live prerequisites created by the hardening (infra checklist)

These are safe-by-default settings that need real values before the first Azure deployment.

- `api.forwardedAllowIps` (Helm): the ingress controller pod CIDR. Left as the placeholder, no proxy is trusted and the API logs the ingress address as the client.
- `egress.destinations.*.cidrs`, `egress.logTools`, `egress.additional` (Helm): the egress NetworkPolicy is on by default and denies everything except DNS and the listed CIDRs. Fill every range (Azure SQL, Key Vault, Entra and Graph, Azure Monitor, LLM gateway, Bot Framework, ServiceNow, each log tool) or outbound calls fail.
- Key Vault secret `keigan-local-token-signing-secret` (48 random bytes, base64): prod refuses to start on the default signing secret even in Entra mode.
- `ENTRA_API_SCOPE` or `ENTRA_REQUIRED_DELEGATED_SCOPE`: Entra mode refuses to start without the delegated scope name.
- Run `helm lint` and `helm template` on the chart, and build the backend image once, before relying on the stream C changes (neither could run in the build sandbox).

## After hardening: roadmap

Agreed 2026-11-20. Each phase starts when the previous one is done, except where noted.

| # | Phase | Goal | Starts when |
|---|---|---|---|
| 1 | Hardening wave 1 and 2 | Every H and V finding fixed with a test, accepted by design, or waiting on infra | In progress |
| 2 | **Feature audit** | Confirm every existing feature is correctly conceived, configured, architected, access-controlled and labelled before anything new is built | Wave 2 merged and green |
| 3 | New features | Build the next features on a verified base | Feature audit findings fixed |
| 4 | UI/UX polish | Design polish beyond the hardening fixes | Mostly after the features it touches |
| 5 | Frontend tests | Vitest unit tests and Playwright end-to-end tests | Any time (not blocked) |
| 6 | Infra go-live checks | Run against real Azure SQL, Entra, ServiceNow, Teams, Log Analytics; APIM and ingress log redaction (V21) | Infra team ready |
| 7 | Live prompt evaluation | Evaluate prompts on real model output with a small RCA eval set | An LLM endpoint or key is available |

### Feature audit (phase 2): method

Scope: every feature in `12_FEATURE_TRACKER.md` (sections A to O). Output: `18_FEATURE_AUDIT.md` with one row per feature,
an access matrix, and a findings list that feeds the same status workflow as this plan.

For each feature the audit answers, with file:line evidence:

1. **Idea.** Does the behaviour match the product specification (`01_PRODUCT_SPECIFICATION.md`), and does it solve the user's real problem?
   Gaps, contradictions, or behaviour nobody asked for.
2. **Access (RBAC).** Who can see it and who can change it: Keigan admin, application admin, application reader, no access.
   One matrix row per API route (method, path, required role, object-level check) and per screen or button (shown or hidden,
   enabled or disabled). The backend check and the UI gating must agree; the backend is the source of truth.
3. **Configuration.** Every threshold, interval, model and mode comes from settings or a catalog with a safe default and an
   `.env.example` entry. Simulated and live modes behave the same apart from the data source.
4. **Architecture.** Logic sits in the right layer (controller, service, integration, worker); one owner per capability; no
   duplicated rules; data model and jobs fit the flow; works with more than one pod.
5. **Labelling.** Names, terms and statuses are consistent across UI, API and docs; no raw enum values; every string in all locales.
6. **Errors and empty states.** Clear messages for every failure and permission case; useful empty and loading states.
7. **Tests.** The behaviour and its access rules are covered by tests.

Verdict per feature: ✅ correct · 🟡 works but needs changes · 🔴 wrong idea or design, rethink before building on it.
New features are planned only after the 🔴 and 🟡 items are resolved or explicitly accepted.

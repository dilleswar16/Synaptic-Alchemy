# 16 — Hardening plan (review findings → fixes → features → UI)

Started 2026-11-20 after a full code review. This document tracks what was found, what was agreed, and the status of
each fix. Update the status column as work lands; record design decisions in `09_LEARNINGS_LOG.md`.

## Context and agreed decisions

- **Mocks are intentional.** SQLite, the mock LLM and simulated integrations stand in while the infra team provisions
  Azure (Azure SQL, Key Vault, APIM, AKS). The goal is code that switches to live resources by configuration only.
- **APIM owns the edge.** Rate limiting, request size limits and edge security are APIM policies, so app-level rate
  limiting is not extended. The in-process limiter stays as a local convenience only.
- **Git.** Work happens on the local branch `keigan-hardening` (baseline commit `3cf95ef`). It is not pushed unless asked.
- **Schema changes are incremental.** The initial Alembic migration is never rewritten. Each change gets a new Alembic
  revision plus a numbered incremental script in `database/azure_sql/`; the full create scripts are kept in sync.
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
| H1 | Custom SLI KQL runs without query validation | `services/sli_measurement_reader.py:88-89` | ⬜ |
| H2 | KQL validator checks only tables before the first pipe; `union` / `find` later in the query are not checked | `utils/query_safety.py:79-89` | ⬜ |
| H3 | Duplicate alerts across pods: dedup relies on an in-process lock; fingerprint index not unique | `services/alert_pipeline_service.py:30,89`, `entities/alert_entities.py:48` | ⬜ |
| H4 | Job deduplication is check-then-insert with no unique constraint | `workers/job_queue.py:44-58` | ⬜ |
| H5 | Job lease (10 min) is never renewed; a long investigation can be run twice | `workers/job_queue.py:25` | ⬜ |
| H6 | Local auth (passwordless, any user incl. admin) is only blocked when `ENVIRONMENT=prod`; default signing secret is accepted | `config/settings.py:96,213-227` | ⬜ |
| H7 | App roles also match Entra group display names (not unique, mutable) | `services/authorization_service.py:61-71` | ⬜ |
| H8 | Entra token accepted when `tid` is absent | `services/authentication_service.py:168` | ⬜ |
| H9 | Uvicorn trusts forwarded headers from any IP | `deploy/docker/backend.Dockerfile:34` | ⬜ (restrict to APIM / ingress) |
| H10 | Retention never removes incidents, investigations or evidence although `INCIDENT_RETENTION_DAYS` exists | `services/administration_service.py:219-237` | ⬜ |
| H11 | Many-to-many links stored as JSON id lists (incident, investigation and alert-group services; conversation applications; maintenance windows) | `entities/incident_entities.py:53,82,208`, `entities/alert_entities.py:103,133` | ⬜ |
| H12 | `application_id` without a foreign key on alert, SLO and intelligence tables (orphans on delete) | `entities/alert_entities.py`, `entities/slo_entities.py` | ⬜ |
| H13 | No CHECK constraints on status columns | all entities | ⬜ |
| H14 | Two-way soft links between alert group, investigation and incident can disagree | `entities/alert_entities.py:108-109`, `entities/incident_entities.py:71-72` | ⬜ |
| H15 | SLI list runs two queries per SLI | `services/slo_service.py:308-319` | ⬜ |
| H16 | Backend has no dependency lock file; Docker builds from version ranges | `backend/pyproject.toml` | ⬜ |
| H17 | Contrast below WCAG AA: `text-subtle` 3.25:1, success text on success background 4.17:1 | `frontend/src/styles/tokens.css:47,65-67` | ⬜ |
| H18 | Horizontal scroll at phone width; raw enum labels; plural bug | frontend shell and pages | ⬜ |
| H19 | Dead or leftover files: `app/PlaceholderPage.tsx`, `frontend/FOUNDATION_READY.md` | frontend | ⬜ |
| H20 | `es-MX` locale has 12 of 15 namespaces (auth, common, navigation missing) | `frontend/src/i18n/locales/es-MX` | ⬜ |
| R1 | In-process rate limiter and Content-Length-only body check | `security/security_middleware.py` | ➖ APIM policies own this |

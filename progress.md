# Corvin Progress

## Status Legend

- [ ] Not started
- [~] In progress
- [x] Complete

## Current Goal

**V3.95 "AWESTRUCK" COMPLETE — 435/435 tests passing. Submission ready for Hackathon.**  
**V4.1 "ENTERPRISE MATURITY" COMPLETE — 437/437 tests passing. Final Sign-Off for Hackathon Submission.**  
See `docs/copilot-context/versions/v4_enterprise_maturity.md` for the priority logic and UI hierarchy specs.

---

## V4.1 — Enterprise Maturity & UI Polish (COMPLETE)

**Exit criteria:** ✅ P1/P2/P3 logic active. Single-column "Cause ➔ Action" flow. Evidence logs collapsed. Dashboard triaged.

- [x] **Automatic Priority Classification** — Logic in `contracts.py` automatically flags `fundsso` as P1 and `dev`/`predictive` as P3. Database migration `21871e3fb4d7` applied.
- [x] **Progressive Disclosure UI** — Overhauled `InvestigationDetailPage.tsx` to hide dense Telemetry and Audit logs by default. Moved RCA and Visual Traces to the top.
- [x] **SRE Triage Dashboard** — Reordered `DashboardPage.tsx` to put the "Active Investigation Queue" at the very top for immediate triage.
- [x] **Red Team Console** — Final styling and branding for the Chaos Engineering Console.
- [x] **High-Contrast Badges** — Integrated P1/P2/P3 badges into every list and header across the platform.
  
See `docs/copilot-context/versions/v3/03_v3_95_awestruck_scope.md` for the full submission specs.

---

## V3.95 — "Awestruck" Hackathon Submit (COMPLETE)

**Exit criteria:** ✅ 435 tests green. Mermaid diagrams streaming flawlessly. Command Center supports speculative analysis. Predicted Outcome gauges active.

- [x] **Mermaid v11 Integration** — Created a bulletproof `MermaidChart` component in `apps/web/src/components/common/`. Uses unique IDs per render, handles streaming token-by-token evolution, and suppresses syntax errors during construction.
- [x] **Investigation Transparency Trace** — `TransparencyTrace` component in `InvestigationDetailPage`. Generates a live Mermaid flowchart showing the path from Trigger → AI Analysis → Root Cause.
- [x] **Platform Pulse** — `PlatformPulse` ticker on the Dashboard. Real-time cycling of platform health events, monitoring activities, and trend detections.
- [x] **Predicted Outcome Gauge** — Visual health-restoration simulation in `ApprovalSection.tsx`. Shows judges the "Before" vs. "After" impact of a proposed fix (e.g., 25% → 90%).
- [x] **Premium Metrics Overhaul** — Refactored `ToolResultCard.tsx` with high-fidelity executive visuals. Added circular SVG gauges for scores and glassmorphic gradients for ROI metrics.
- [x] **Speculative Analysis** — Updated `agent_tools.py` and `agent_service.py` to support "What-if" blast radius analysis without an existing incident.
- [x] **Bug Fix: Python 3.10 Datetime** — Fixed critical `ValueError` in `repository.py` caused by `isoformat` not supporting "Z" suffix in Python 3.10.
- [x] **Bug Fix: Chat Streaming** — Updated `test_slice11_chat_service.py` to match the latest `litellm` response schema (`type: text`).


---

### Latest Frontend Redesign Slice

- [x] Introduced dual-theme design system (light + dark) with CSS tokens for palette, spacing, radius, elevation, type scale, and motion.
- [x] Implemented `ThemeProvider` + persisted theme selection + system preference detection + anti-FOUC inline script.
- [x] Added animated `ThemeToggle` with sun/moon transition and focus-visible behavior.
- [x] Refactored navigation to responsive header with mobile drawer, sticky glass nav, and desktop CTA.
- [x] Added semantic footer and improved layout rhythm while preserving all existing routing and data-fetch behavior.

---

## V3.5 — Demo Core (COMPLETE)

- [x] **Corvin Score** — `repository.get_service_score()`: weighted 0–100 score from incident frequency, RCA confidence, MTTR, recency. `GET /investigations/score` endpoint registered BEFORE `/{id}` route. Green ≥80, amber 50–79, red <50.
- [x] **Blast Radius Estimator** — `corvin/strategy/blast_radius.py`: pure calculation from EvidenceBundle (no LLM). Output: `BlastRadiusEstimate` (affected services, estimated users, revenue risk/min, replica count, rationale). `GET /investigations/{id}/blast-radius` endpoint.
- [x] **Alert Simulator** — `POST /triggers/simulate`: 4 presets (hpa_failure, five_zero_three_spike, auth_errors, memory_leak). Reuses existing `_run_investigation_in_background`. Returns request_id immediately for SSE stream redirect.
- [x] **Teams Adaptive Card** — `TeamsAdapter._build_card()` now accepts optional `BlastRadiusEstimate`. Blast radius section (💥) injected with affected services, estimated users, revenue risk, replica count. Colour-coded by severity.
- [x] **ServiceHealthGauge** — SVG arc gauge (220° sweep, ease-out cubic animation), 3 services on Dashboard (fundapis, fundsso, partnerapis). Click → filtered investigations list.
- [x] **BlastRadiusCard** — Amber/red banner at top of InvestigationDetailPage. Lazy-loads from `/blast-radius` endpoint. Shows severity chip, users, services, revenue risk/min, rationale.
- [x] **SimulateAlertPanel** — Dashboard widget with 4 preset buttons, optional description, fire button. Navigates to new investigation detail on success.
- [x] **Config additions** — `config/policies/investigation.yaml`: `blast_radius_users_per_replica`, `blast_radius_revenue_per_user_per_min`, `blast_radius_currency`, `simulator_presets`.
- [x] **client.ts** — `ServiceScore`, `BlastRadiusEstimate`, `SimulateAlertPayload/Response` types. `fetchServiceScore()`, `fetchBlastRadius()`, `simulateAlert()` functions.
- [x] **V3.5 tests** — `tests/slices/test_slice_v35_features.py`: 20 tests covering blast radius calculation, score repository, simulate endpoint, score endpoint, blast radius 404.

---

## V3+ Hackathon Enhancement Backlog

Priority order. Work through these in sequence before considering V4.

### ✅ Done (post-V3 polish)
- [x] StreamingProgress: all blue → amber signal colour
- [x] InvestigationDetailPage: hero redesign, RCA redesign (confidence bar, red root cause card, numbered factors)
- [x] FixStrategyPage: full redesign (2-col grid, risk-coloured borders, colour-mix circles)
- [x] Dashboard: error card with retry, VerticalBars gradient fix (colour-mix), NavBar clock fix
- [x] InvestigationsPage: table column widths, badge justifySelf, timeAgo column
- [x] StreamingProgress TypewriterPanel → amber skeleton loader (deferred until thinking model)
- [x] **gpt-5.1 + Responses API + ThinkingPanel** ← COMPLETED
  - Upgraded primary model to `azure/responses/gpt-5.1` (Azure AI Foundry Responses API path)
  - `AZURE_API_VERSION=2025-04-01-preview` in `.env` (Responses API requires ≥ 2025-03-01-preview)
  - `litellm.drop_params = True` in both generators — silently drops `temperature` unsupported by reasoning models
  - `litellm.reasoning_auto_summary = True` in both generators — injects `summary="detailed"` so `delta.reasoning_content` is populated in streaming chunks
  - `reasoning_effort: medium` in `config/models/llm.yaml` (simplified from dict — auto_summary handles summary injection)
  - `corvin/investigation/stream.py` routes `__thinking__:` prefixed tokens to `stage: 'thinking'` SSE events
  - `ThinkingPanel` component in `StreamingProgress.tsx` — purple-tinted, collapsible, char-count header, auto-scroll, blinking cursor
  - Wired into RCA `StagePanel` — shows above TypewriterPanel when `streamText['thinking']` has content
  - DB migration `0007_add_confidence_reasoning.py` applied (fixes `confidence_reasoning` column missing)
  - Confirmed live: 1065 chars of chain-of-thought visible in UI during real `fundapis/dev` investigation
  - 380/380 tests passing
- [x] **#4 — Incident Memory** ← COMPLETED
  - `InvestigationRepository.get_similar_incidents(service, env, n=3)` — SQLAlchemy join, newest-first, session-safe
  - `PromptBuilder.build()` injects "Similar Past Incidents (same service)" section when memory exists
  - `GET /investigations/memory?service_name=X&environment=Y&n=N` API endpoint
  - UI: `SimilarIncidentsSection` card on `InvestigationDetailPage` between Evidence and RCA
  - `client.ts`: `fetchSimilarIncidents()` + `SimilarIncident` type
  - Bug fixed: `LogAnalyticsAdapter` and `ContainerLogsAdapter` datetime serialisation (`.isoformat()`)
  - Bug fixed: `ContainerLog` query via `KubePodInventory` join (Name/Image columns were empty)
  - Bug fixed: stale test `test_streamer_emits_evidence_complete_event_with_sources` updated for `{name,count}` sources format
  - 380/380 tests passing

### � Queued (do in order)
- [x] **#1 — Loosen post-mortem gate** ← DONE
  - `PostMortemSection` renders whenever `data.rca` exists (any approval status)
  - Yellow `PREVIEW` chip shown when status is not `executed`

- [x] **#2 — Search/filter on investigations list** ← DONE
  - `searchQuery` + `statusFilter` state in `InvestigationsPage`
  - `filteredItems` client-side filter: `service_name.toLowerCase().includes(q)` + status match
  - Empty state shows "No matches / Try adjusting your search" when filtered

- [x] **#3 — Evidence Accordion (Phase 1)** ← DONE
  - Backend: `_evidence_sources()` in `stream.py` emits `[{name, count}]` on `evidence.complete` event
  - Frontend: `EvidenceAccordion` component in `StreamingProgress.tsx` — ●/○ dots, adapter names, counts
  - Phase 2 (live per-tool-call events) deferred until thinking model

- [x] **#4 — Incident Memory** ← DONE (see Done section above)

- [x] **#5 — Surface Replay / Transparency** ← DONE
  - `ReplayPayload` type + `fetchReplay()` added to `apps/web/src/api/client.ts`
  - `AuditTrailSection` component added to `InvestigationDetailPage` — collapsible, rendered at bottom after Post-Mortem
  - Premium vertical amber timeline: 6 stages (Triggered → Evidence → RCA → Fix Strategy → Approval → Complete)
  - Each stage: dot with glow, color-coded by confidence/status, inline chip badge, right-aligned mono timestamps + delta elapsed time
  - Header shows "Audit Trail · 6 stages · completed in Xm Xs" when collapsed; lazy-loaded, collapses by default

- [x] **#6 — Morning Briefing** ← DONE
  - `InvestigationRepository.get_briefing(hours)` — real Postgres query for last N hours window
  - `_build_briefing_narrative()` — deterministic plain-English SRE narrative
  - `GET /investigations/briefing?hours=24` — registered BEFORE `/{id}` route; returns `BriefingResponse` Pydantic model
  - `BriefingWidget` on DashboardPage: atmospheric grid, hour-aware greeting, `useTypewriter` hook, confidence mini-chart, service chips, urgent amber pulse when high-confidence pending
  - `BriefingPayload` type + `fetchBriefing()` in `client.ts`

- [x] **#8 — Live Evidence Collection Progress** ← DONE
  - `max_tokens` raised to 8192 in `config/models/llm.yaml` (was 4096; comment explains it's a ceiling, not a target)
  - `_timed_step()` module-level generator in `enrichment_service.py`: yields running+done progress dicts with `source_status`, `source`, `table`, `count`, `elapsed_ms`; wraps any adapter call; captures result via `StopIteration.value` (PEP 380)
  - `enrich_streaming()` on `EnrichmentService`: additive alongside existing `enrich()` (all tests unchanged); 4 `yield from _timed_step(...)` calls: `container_logs→ContainerLog·chad`, `apim_logs→ApiManagementGatewayLogs`, `aks_context→KubePodInventory·KubeEvents`, `activity_changes→AzureActivity`; final `yield None, bundle`
  - `corvin/investigation/stream.py`: replaced single `enrich()` call with loop over `enrich_streaming()`; emits `evidence.fetching` SSE events with `source_status` field (not `status` — avoids `**progress` collision with SSE-level `status`); `evidence.complete` now carries `sources` list + `total_elapsed_ms`
  - `useInvestigationStream.ts`: `fetchingEvents: StageEvent[]` state; deduplication by `source` key (running→done replacement); returned from hook
  - `EvidenceAccordion` in `StreamingProgress.tsx` fully rewritten: 4-column grid (icon | label+table | count | elapsed), `⟳`/`●`/`○` status icons, `animate-pulse-glow` while running, fmtMs helper (Xs/Xms), auto-opens via `useEffect` during evidence stage, total wall-clock footer, header summary `N sources · M records · Xs`
  - Fallback path: if `fetchingEvents` is empty (historical investigation), reads `latest.sources` from `evidence.complete` SSE event
  - Confirmed live in browser: `"2 sources · 201 records · 27.6s"`, expanded rows show `Container Logs / ContainerLog · chad / 200 / 8.7s`, `AKS Context / KubePodInventory · KubeEvents / 1 / 4.0s`

- [x] **#7 — Full Application Audit + Refactor** ← DONE
  - `InvestigationDetailPage.tsx`: 1484 → 266 lines (extracted 9 components)
  - New `apps/web/src/components/investigation/` directory:
    - `WorkflowStepper.tsx` (82L), `StickyApprovalBar.tsx` (88L), `EvidenceSection.tsx` (149L)
    - `SimilarIncidentsSection.tsx` (108L), `RcaSection.tsx` (176L), `ApprovalSection.tsx` (91L)
    - `ExecutionSection.tsx` (94L), `PostMortemSection.tsx` (87L), `AuditTrailSection.tsx` (237L)
  - New shared modules: `components/Section.tsx`, `components/StatusBadge.tsx`, `components/CopyableId.tsx`
  - New shared utils: `utils/time.ts` (`fmtTs`, `timeAgo`, `deltaLabel`, `totalDuration`) — eliminates duplication
  - New hook: `hooks/useTypewriter.ts` — extracted from DashboardPage
  - `DashboardPage.tsx`: imports shared utils + hook (32 lines removed)
  - `InvestigationsPage.tsx`: imports shared utils + `STATUS_CLS` (20 lines removed)
  - `pages/NotFoundPage.tsx` — 404 route added to `App.tsx`
  - Backend: `BriefingResponse` Pydantic model replaces `response_model=dict` on briefing endpoint
  - Loading skeleton panels on detail page (animated shimmer) instead of bare "Loading…" text
  - **380/380 tests passing, TypeScript build clean**

### 🔒 Deferred
- [ ] **Streaming typewriter (Option A — delimiter)** — defer until thinking model upgrade
  - See `/memories/repo/streaming-todo.md` for full implementation plan
- [ ] **V4 — Semantic Search / Vector RAG**
  - Current `get_similar_incidents()` matches by `service_name + environment` only (investigation history, not true similarity)
  - V4 upgrade: embed `root_cause` text → pgvector cosine search → return incidents with similar failure patterns across services
  - UI label to update then: "Similar Past Incidents" (currently honest label is "past investigations for same service")
  - Requires: pgvector extension on Azure Postgres, embedding model call, migration
- [ ] **V4.5 — Hackathon Killer Features**
  - **AI Chaos Monkey:** Auto-inject realistic failures and auto-heal them.
  - **Root Cause Debate Mode:** Multi-agent hypothesis generation and debate.
- [ ] **V4.6 — Advanced Visualizations**
  - **Time-Travel Incident Replay:** Visual slider to rewind system state graph.
- [ ] **V4.7 — Source Code Insights**
  - **"Git Blame" Code-Level Root Cause:** Correlate infrastructure alerts to exact GitHub commits.
- [ ] **V4.8 — FinOps**
  - **Cost-Aware Remediation:** Attaching live price tags to fix strategies.


---

**V3 code-complete. 363/363 tests passing.** Post-mortem auto-generator, SRE health dashboard, streaming AI visualizer, and full dark glassmorphism UI overhaul are done.

---

### V3 — Premium React UI + Post-Mortem Auto-Generator (2026-05-XX)

**Scope:** Post-Mortem Auto-Generator (rendered in-page + .md download), SRE Health Dashboard (real Postgres data), Streaming AI Visualizer (token typewriter), and Tailwind dark-mode glassmorphism UI overhaul.

**Exit criteria:** ✅ 363 tests passing, TypeScript build clean (exit 0), all 6 slices complete.

#### Slice 1 — Post-Mortem API + contract

- [x] `PostMortemOutput` Pydantic contract added to `corvin/core/contracts.py`
- [x] `PostMortemRow` SQLAlchemy ORM model added to `corvin/storage/models.py`
- [x] Alembic migration `0006_v3_add_post_mortems_table.py` — `post_mortems` table with FK to `investigation_requests`
- [x] `corvin/strategy/postmortem_service.py` — deterministic section builders + LLM prevention recommendations + markdown assembly
- [x] `InvestigationRepository.save_post_mortem()`, `get_post_mortem()` — upsert + retrieve
- [x] `POST /investigations/{id}/postmortem` — generates + caches (no re-generation on repeat)
- [x] `GET /investigations/{id}/postmortem` — returns cached, 404 if not generated
- [x] 18 tests covering service, repo, and API routes

#### Slice 2 — SRE Health Stats API

- [x] `InvestigationRepository.get_investigation_stats()` — real aggregates from Postgres
  - `total_investigations`, `today_count`, `confidence_distribution` (from `rca_outputs`), `approval_distribution`, `avg_mttr_minutes`, `auto_resolved_rate`, `recent_services` (last 5 unique)
- [x] `GET /investigations/stats` — registered BEFORE `/{request_id}` to avoid routing conflict
- [x] 9 tests (repo + API)

> **V3 backend test count:** 27 new tests → **363 total passing** (320 pre-V3 + 16 V2.5 + 27 V3)

#### Slice 3 — SRE Health Dashboard (React)

- [x] `apps/web/src/pages/DashboardPage.tsx` — new dashboard with real stats from `GET /investigations/stats`
  - KPI cards: total, today, avg MTTR, auto-resolved rate
  - Mini bar charts: RCA confidence + approval pipeline
  - Recent services chips + recent investigation rows with status badges
  - TanStack Query with 30s auto-refresh
- [x] `apps/web/src/components/NavBar.tsx` + `Layout.tsx` — sticky glassmorphism nav, consistent max-width layout
- [x] `App.tsx` routing updated: `/` → DashboardPage, `/investigations` → InvestigationsPage

#### Slice 4 — Streaming AI Visualizer

- [x] `StreamingProgress.tsx` fully rewritten — V3 token typewriter renderer
  - Stage tracker with animated nodes (evidence → RCA → fix_strategy)
  - `TypewriterPanel` with live token scroll + blinking cursor (`animate-cursor`)
  - `RCASummary` + `FixStrategySummary` structured cards after each stage completes
  - Degraded/fallback banners surfacing `generation_status`
  - Dark glassmorphism `StagePanel` cards with active border glow

#### Slice 5 — Post-Mortem UI (rendered in-page + download)

- [x] `PostMortemSection` component in `InvestigationDetailPage.tsx`
  - Only visible when `approval_status === 'executed'`
  - "Generate Post-Mortem" button → `POST /investigations/{id}/postmortem` mutation
  - `react-markdown` renders `pm.markdown` with `.pm-prose` styling
  - "Download .md" button — Blob + `URL.createObjectURL` + `<a download>` — no server round-trip
  - Auto-loads cached post-mortem on page load (GET)

#### Slice 6 — Tailwind dark-mode glassmorphism overhaul

- [x] `apps/web/src/index.css` — full Corvin design system
  - Tailwind v4 via `@import "tailwindcss"` (no config file — plugin approach)
  - CSS variables: `--c-bg`, `--c-surface`, `--c-accent`, `--c-green`, `--c-yellow`, `--c-red`, `--c-purple`
  - Body: radial-gradient atmospheric background
  - Font: IBM Plex Mono / JetBrains Mono monospace (SRE terminal aesthetic)
  - Component classes: `.glass`, `.glass-accent`, `.badge-*`, `.metric-card`, `.btn-primary`, `.btn-ghost`, `.pm-prose`
  - Animations: `animate-fade-up`, `animate-pulse-glow`, `animate-cursor`
- [x] `vite.config.ts` — `@tailwindcss/vite` plugin added
- [x] `apps/web/package.json` — tailwindcss, @tailwindcss/vite, react-markdown, framer-motion added
- [x] `InvestigationsPage.tsx` — glassmorphism form, row cards with hover glow, `Layout` wrapper
- [x] `InvestigationDetailPage.tsx` — dark-theme sections, badge-based status, `Layout` wrapper
- [x] `FixStrategyPage.tsx` — glass action cards with risk-level color coding, `Layout` wrapper

---

**V2.5 status:** ✅ Complete. 318/318 tests passing on local venv (320/320 on org laptop with botbuilder).

**V2 status:** ✅ Complete. 320/320 tests passing.

### V2.5 — Polish & New Features (2026-05-02)

Three production-quality features added to sharpen the hackathon demo:

- [x] **Feature 1 — Investigation Replay** (`GET /investigations/{id}/replay`)
  - New `get_investigation_replay()` in `InvestigationRepository`: returns a full transparency payload — trigger details, evidence summary, approval audit, RCA, fix strategy.
  - New FastAPI route `GET /investigations/{request_id}/replay` (404 if not found / incomplete).
  - 3 new tests in `test_slice_v2_5_features.py`.

- [x] **Feature 2 — SRE Audit Log** (`approved_by`, `approved_at`)
  - Added `approved_by: str | None` and `approved_at: datetime | None` columns to `InvestigationRequestRow`.
  - Alembic migration `0005_v2_5_audit_log.py` (run `alembic upgrade head` on org laptop).
  - `update_approval_status()` now accepts optional `approved_by` arg; writes `approved_at` as UTC timestamp.
  - `approve` and `reject` API routes accept `?approved_by=` query param for Teams/Web surfaces.
  - `list_investigations()` now surfaces `approval_status`, `approved_by`, `approved_at` in summary rows.
  - Replay payload includes full `approval` section with who approved and when.
  - 5 new tests in `test_slice_v2_5_features.py`.

- [x] **Feature 3 — Confidence Threshold Gate**
  - New `min_confidence_to_suggest_action: medium` key in `config/policies/investigation.yaml`.
  - New `confidence_warning: bool = False` field on `InvestigationResult` contract.
  - `InvestigationEngine.run()` reads policy, computes `_confidence_below_threshold()`, sets `confidence_warning=True` on LOW-confidence RCAs and logs a warning.
  - All existing pipeline tests unaffected (gate defaults to `medium` threshold; HIGH-confidence RCAs never trigger it).
  - 8 new confidence gate tests in `test_slice_v2_5_features.py`.

- [x] **Blocker Fixed** — `botbuilder-core` + `botbuilder-integration-aiohttp` installed in local venv via `pip install`. All 7 previously failing test files now collect and pass.

> **Test count:** 302 previously collectible + 16 new V2.5 tests = **318 passing** on this machine. The org laptop (which had botbuilder installed) shows **320/320** — the 2 difference is 2 botbuilder-specific tests that weren't collecting locally before.

### Post-V2 hardening (audit-driven fixes)

Audit found 3 critical (C-*) and 7 high-priority (H-*) issues. C-2 (auth/RBAC) skipped per scope (hackathon).

A second post-fix audit then surfaced 4 contract-drift criticals (C-A..C-D) inside the C-1 Execute surface plus one new High (H-A). All 5 fixed.

- [x] **H-2** `FixStrategyGenerator.generate_stream` fallback now sets required `justification` field — prevents `pydantic.ValidationError` when streaming + non-streaming both fail. Tests: `test_slice6_llm_generation.py` (+2).
- [x] **H-3** `RCAGenerator` now exposes `last_stream_status` (`ok | insufficient_evidence | degraded_non_streaming | degraded_unparseable | degraded_failed`). `InvestigationStreamer` surfaces this in the SSE `rca.complete` event as `generation_status` + `degraded` so the UI can show degraded results. Tests: `test_slice_v2_s6_streaming_rca.py` (+3).
- [x] **H-4** Approval state machine tightened: only `pending → approved/rejected` is allowed (was leaking `approved → rejected` etc.). Tests: `test_slice_v2_s2_approval_api.py` (+4).
- [x] **H-5** `EnrichmentService` now wraps every adapter call with `try/except` + `logging.getLogger(__name__).warning(...)`. One failing source no longer kills the whole bundle. Tests: `test_slice2_enrichment_service.py` (+1).
- [x] **H-6** `corvin/storage/db.py` now honours `pool_size`, `max_overflow`, `pool_timeout_seconds` from `config/integrations/postgres.yaml` (was hardcoded). Tests: `test_slice_h6_postgres_pool_config.py` (+4, new file).
- [x] **H-7** `POST /triggers/azure-alert` now actually runs the engine + persists + posts to Teams (was just normalising payload + returning 202). Returns 202 even on engine failure (Azure Monitor retries forever — non-2xx triggers infinite retries). Tests: `test_slice_h7_azure_alert_triggers_engine.py` (+3, new file).
- [x] **C-1** Execute surface wired across all delivery channels:
  - Web: `apps/web/src/api/client.ts` + `InvestigationDetailPage.tsx` (new `ExecutionSection`).
  - CLI: `apps/cli/main.py` — `approve <id>`, `reject <id>`, `execute <id>` commands added to REPL + help table.
  - Teams bot: `apps/teams/bot.py` — `approve <id>`, `reject <id>`, `execute <id>` commands wired through `InvestigationRepository` and `ExecutionService`. Tests: `test_slice_v2_s5_teams_bot.py` (+9).
- [x] **H-1** `apps/web/src/api/baseUrl.ts` already correctly prefers `VITE_API_URL`. Documented in `setup/08_azure_deploy.md` Part 2 Step 2 that production **must** set `VITE_API_URL` to the App Service origin so SSE bypasses the SWA proxy buffer (which would otherwise break streaming RCA).
- [x] **C-3** `.github/workflows/azure-static-web-apps.yml` and `.github/workflows/azure-app-service-api.yml` added.
- [ ] ~~**C-2** auth/RBAC~~ — explicitly skipped (hackathon scope).

### Post-fix audit follow-ups (contract drift round)

- [x] **C-A** Teams bot `_handle_execute` was calling `ExecutionService.execute(request_id, namespace=...)` — wrong signature. Real signature is `execute(result: InvestigationResult, approval_status: ApprovalStatus, namespace=None)` and raises `PermissionError` if status != approved. Bot now loads the persisted `InvestigationResult` via `repository.get_investigation_result(request_id)` and passes it through correctly.
- [x] **C-B** Web (`apps/web/src/api/client.ts`, `InvestigationDetailPage.tsx`), CLI (`apps/cli/main.py`), and Teams bot were all reading wrong outcome fields (`action_title`, `succeeded`, `message`). API actually returns `{action_type, title, success, detail}`. All three surfaces now read the real shape.
- [x] **C-C** Teams bot wasn't transitioning approval status from `approved → executed` after a successful run, leaving the persisted record stale relative to the API route (which does transition). Bot now calls `repository.update_approval_status(request_id, ApprovalStatus.EXECUTED)` on success.
- [x] **C-D** Teams bot test fakes (`_FakeRepository`, `_FakeExecutionService`, `_FakeOutcome`, `_FakeExecutionResult`) used invented method signatures and dataclass shapes — they were hiding C-A/C-B/C-C entirely. Rewrote to use the real `ActionOutcome` and `ExecutionResult` dataclasses, the real `ExecutionService.execute(result, approval_status, namespace=None)` signature, and added `_FakeRepository.get_investigation_result`. Added `test_bot_execute_missing_result_returns_friendly_error` for the new error path. Tests: `test_slice_v2_s5_teams_bot.py` rewritten + 1 new test.
- [x] **H-A** `POST /triggers/azure-alert` was running `engine.run` (which can take 60-180s) inline, and Azure Monitor Action Groups have a ~120s HTTP timeout + retry-on-timeout. Race condition: long investigations could trigger duplicate retries. Route now takes a `BackgroundTasks` parameter and queues a worker `_run_investigation_in_background(request, engine, repo, teams)` that runs the full pipeline; webhook returns 202 immediately with `status: "accepted"`. Tests: `test_slice_h7_azure_alert_triggers_engine.py` updated + 1 new regression test (introspects the route to assert `background_tasks.add_task` is wired) — 4/4.
- [x] **M-A** `FixStrategyGenerator.generate_stream` now sets `self.last_stream_status` (`ok | degraded_non_streaming | degraded_unparseable | degraded_failed`) on every yield path, mirroring `RCAGenerator`. `InvestigationStreamer` reads it and emits `generation_status` + `degraded` on the SSE `fix_strategy.complete` event so the UI can show banners for fallback paths. Tests: `test_slice_v2_s6_streaming_rca.py` (+4) — 28/28.

> **Test count:** 314 → **320 passing** (+1 bot-error path, +1 H-A regression, +4 M-A regression). All bot tests now use real `ActionOutcome`/`ExecutionResult` dataclasses instead of fabricated stand-ins, eliminating contract-drift accelerators.

**V2 status:**

V2 Slice 1: `ApprovalStatus` enum, `lookback_minutes`, ORM columns, Alembic migration applied to real Azure Postgres.
V2 Slice 2: `POST /investigations/{id}/approve` and `POST /investigations/{id}/reject` routes with 404/409 guards.
V2 Slice 3: Teams Adaptive Card updated with `Action.OpenUrl` Approve/Reject buttons + full approval UI in React detail page.
V2 Slice 4: `ExecutionService` wired to `AKSAdapter` — pod restart, rollback, scale dispatched from approved fix actions.
V2 Slice 5: Teams ChatOps bot — `CorvinBot(ActivityHandler)` handles `@mention investigate <service> <env>` in Teams.
  - `apps/teams/__init__.py`, `apps/teams/bot.py`, `apps/teams/router.py`
  - `POST /teams/messages` route: returns 501 when `bot_enabled: false` (safe default for CI/local)
  - `_strip_mention_tags` + `_parse_command` helpers handle Teams HTML mention wrappers
  - `_run_investigation_async` runs engine in thread executor, posts result card via `TeamsAdapter`
  - Ack sent immediately to Teams before engine runs (avoids 15s timeout)
  - `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD` added to `.env.example` and `config/integrations/teams.yaml`
  - `bot_enabled: false` config guard means no Bot Framework registration needed for development
  - 38 new tests — 267 total passing
V2 Slice 6: Streaming RCA (SSE) — `GET /investigations/stream` + React consumer.
  - `corvin/investigation/stream.py` — `InvestigationStreamer` runs pipeline stage-by-stage, yields SSE events
  - `GET /investigations/stream` FastAPI route with `StreamingResponse`, registered before `GET /{id}` to avoid routing conflict
  - `apps/web/src/hooks/useInvestigationStream.ts` — React hook wrapping EventSource API
  - `apps/web/src/components/StreamingProgress.tsx` — live stage progress component
  - `InvestigationsPage` form now streams instead of blocking POST; redirects to detail page on completion
  - `setup/07_teams_bot.md` created — full Teams Bot Azure registration walkthrough
  - 21 new tests — **288 total passing**
  - **Post-slice fix:** `generate_stream()` in both `RCAGenerator` and `FixStrategyGenerator` now drops `response_format: json_object` on the streaming path. Azure OpenAI buffers all tokens until full JSON is structurally valid when this flag is set, defeating SSE streaming. Removing it lets tokens flow in real time (~13ms gaps over 6+ seconds for a full RCA). JSON parsing is done client-side after accumulating all tokens. `FakeRCA.generate_stream()` and `FakeFixStrategy.generate_stream()` added to test fakes so the streamer tests no longer fall through to the real LLM.
  - **AKS deployment name fix:** `AKSAdapter._resolve_deployment_name()` added — tries bare `service_name` first, falls back to `{namespace}-{service_name}` (e.g. `chad-partnerapis`) on 404. Matches the Helm chart naming convention used in the `chad` namespace.

> **V1.5 adapter changes:** Elastic replaced by `ContainerLogsAdapter` (org SSO blocks Elastic). Queries `ContainerLog`, `KubePodInventory`, `KubeEvents` tables from `LogAnalytics-AUCHAD-DV01` workspace. Enrichment service wired to use container logs as fallback when Elastic is offline.

> **LLM structured output fix:** Both `RCAGenerator` and `FixStrategyGenerator` switched from `json_schema` strict mode (which requires all fields in `required`) to `json_object` mode. The prompt still instructs the model to match the exact Pydantic schema shape.

> **AKS namespace fix:** `EnrichmentService` no longer passes `request.environment` as the AKS namespace — the AKS adapter now always falls back to `default_namespace` from `config/integrations/aks.yaml` (`chad`).

> **CLI change (post-V1 polish):** The one-shot Typer CLI has been replaced with a fully interactive rich REPL (like Claude Code / Codex style). Entry point is still `corvin`. Commands inside the shell: `investigate`, `list`, `show <id>`, `health`, `clear`, `help`, `exit`. Uses `rich>=13.7.0` and `prompt_toolkit>=3.0.0`. All CLI tests updated to call command functions directly via `monkeypatch` + `StringIO` console capture.

> **Model config change (post-V1 polish):** `config/models/llm.yaml` updated to use `azure/gpt-4o` (primary) and `azure/gpt-4o-mini` (fallback) — LiteLLM Azure routing prefix added.

> **Folder structure change (post-GAP-7):** `runbooks/` and `data/learnings/` have been merged into `knowledge/` subfolders. The repo root now has a single `knowledge/` folder containing `site.md`, `runbooks/`, and `learnings/`. Config paths updated in `config/tools/knowledge.yaml`. `knowledge_loader.py` docstring updated. All references to the old `runbooks/` and `data/` root folders are now invalid.

---

## Scaffold Review Gaps (found in pack review — must fix before Slice 2b)

These items were identified as missing from the initial scaffold. Fix all of them in sequence before wiring real adapters.

### GAP-1 ✅ `corvin/storage/` module
- Created `corvin/storage/__init__.py`, `corvin/storage/models.py` (SQLAlchemy ORM), `corvin/storage/db.py` (engine/session factory).

### GAP-2 ✅ `alembic/` folder initialized
- Ran `alembic init alembic`, wired `env.py` to Corvin ORM base and engine.
- Created manual initial migration: `alembic/versions/0001_create_initial_tables.py`.

### GAP-3 ✅ Azure Activity Log evidence adapter
- Created `corvin/evidence/azure_activity_adapter.py` (stub, matching adapter interface).
- Wired into `EnrichmentService` and `EvidenceBundle.azure_activity_changes`.
- Added adapter stub test.

### GAP-4 ✅ `config/integrations/azure_activity.yaml`
- Created alongside GAP-3.

### GAP-5 ✅ Knowledge layer
- Created `knowledge/site.md` (static infra facts).
- Created `runbooks/README.md`, `runbooks/apim-5xx.md`, `runbooks/aks-crashloop.md`.
- Created `data/learnings/general.md`.
- Created `config/tools/knowledge.yaml`.
- Created `corvin/core/knowledge_loader.py` (site knowledge, runbook matching, learnings loading).

### GAP-6 ✅ Web app detail and fix strategy pages
- Created `InvestigationDetailPage.tsx` and `FixStrategyPage.tsx`.
- Added routes `/investigations/:id` and `/investigations/:id/fix-strategy` in `App.tsx`.

### GAP-7 ✅ Toolset registry
- Created `corvin/toolsets/__init__.py`, `base.py` (`Toolset` ABC with `get_tools`, `execute`, `check_prerequisites`), `registry.py` (`@register_toolset` decorator, `get_enabled_toolsets`).
- Created six toolset stubs: `elastic.py`, `log_analytics.py`, `aks.py`, `azure_activity.py`, `knowledge.py`, `runbooks.py`.
- Created `runbooks/catalog.json` with two entries: `apim-5xx` and `aks-crashloop`.
- Created `config/tools/toolsets.yaml` with per-toolset `enabled` flags.

### GAP-8 🟡 Azure Cost Management scheduler not planned
- V2 item. Documented in `versions/v2/01_scope_and_capabilities.md` and `03_architecture.md`.
- Nothing to build yet. Flagged so it is not forgotten when V2 starts.

## V1 Build Tasks

### Foundation (Slice 0 – complete)
- [x] Root project files: `pyproject.toml`, `docker-compose.yml`, `.env.example`
- [x] `corvin/core/contracts.py` – all shared Pydantic models
- [x] `corvin/core/config_loader.py` – YAML config loader with env overlay
- [x] `corvin/triggers/azure_alert.py` – Azure alert normalization adapter
- [x] `corvin/evidence/elastic_adapter.py` – Elastic stub
- [x] `corvin/evidence/log_analytics_adapter.py` – Log Analytics stub
- [x] `corvin/evidence/aks_adapter.py` – AKS stub
- [x] `corvin/enrich/enrichment_service.py` – enrichment orchestrator
- [x] `corvin/strategy/rca_generator.py` – RCA generator stub
- [x] `corvin/strategy/fix_strategy_generator.py` – fix strategy stub
- [x] `corvin/delivery/teams_adapter.py` – Teams delivery stub
- [x] `apps/api/` – FastAPI app with `/investigations` and `/triggers` routes
- [x] `apps/cli/` – Typer CLI with `investigate` and `health` commands
- [x] `apps/web/` – React + Vite + TanStack Query scaffold
- [x] `config/` – All config YAML files (models, integrations, tools, policies, environments)
- [x] `tests/contracts/` – Contract model tests (14 tests)
- [x] `tests/adapters/` – Adapter stub tests (4 tests)
- [x] `tests/slices/` – Slice 1 trigger normalization tests (9 tests) + Slice 2 enrichment tests (3 tests)

### Slice 1 – Azure alert normalization (complete, 9 tests pass)
- [x] `normalize_azure_alert` produces correct InvestigationRequest from Common Alert Schema
- [x] Handles missing fields gracefully

### Slice 2 – Enrichment service graceful degradation (complete, 3 tests pass)
- [x] EnrichmentService returns empty bundle when all adapters are stubs
- [x] EnrichmentService populates bundle when fake adapters are injected

### GAP fixes (complete ✅)
- [x] GAP-1 + GAP-2: `corvin/storage/` + alembic init + initial migration
- [x] GAP-3 + GAP-4: `corvin/evidence/azure_activity_adapter.py` + `config/integrations/azure_activity.yaml`
- [x] GAP-5: `knowledge/site.md`, `runbooks/` stubs, `data/learnings/general.md`, `config/tools/knowledge.yaml`, `corvin/core/knowledge_loader.py`
- [x] GAP-6: `InvestigationDetailPage.tsx`, `FixStrategyPage.tsx`, wired routes in `App.tsx`
- [x] GAP-7: `corvin/toolsets/` with `base.py`, `registry.py`, six stubs; `runbooks/catalog.json`; `config/tools/toolsets.yaml`

### Slice 2b – Elastic adapter wire-up ✅
- [x] Implemented `ElasticAdapter.get_logs` and `get_metrics` with elasticsearch-py
- [x] `environment` is an optional filter; `${ELASTIC_HOST}` / `${ELASTIC_API_KEY}` expanded from env vars
- [x] Graceful degradation: connection errors log a warning and return `[]`
- [x] `ElasticToolset` schemas updated to expose `environment` parameter
- [x] 7 new Slice 2b tests in `tests/slices/test_slice2b_elastic_adapter.py`; 37/37 pass

### Slice 3 – Log Analytics APIM adapter ✅
- [x] Implemented `LogAnalyticsAdapter.get_apim_logs` with `LogsQueryClient` + `ClientSecretCredential`
- [x] `environment` is an optional KQL filter; `${AZURE_*}` placeholders expanded from env vars
- [x] Client built once in `__init__`; empty/invalid credentials produce a `None` client and graceful `[]` return
- [x] `LogAnalyticsToolset` schema updated to expose `environment` parameter
- [x] `azure-identity>=1.15.0` added to `pyproject.toml` dependencies
- [x] 8 new Slice 3 tests in `tests/slices/test_slice3_log_analytics_adapter.py`; 45/45 pass

### Slice 4 – AKS context adapter ✅
- [x] Implemented `AKSAdapter.get_pod_context` with `CoreV1Api` + `AppsV1Api` (kubernetes-client)
- [x] Supports `kube_config_path` (local) and `in_cluster: true` mode; clients built once in `__init__`
- [x] Returns `{pods, events, deployment}` dict; events filtered to service name; missing deployment returns `None` without crash
- [x] `namespace` optional param added; falls back to `default_namespace` from config
- [x] `AKSToolset` schema updated to expose `namespace` as optional parameter
- [x] `kubernetes>=29.0.0` added to `pyproject.toml` dependencies
- [x] 9 new Slice 4 tests in `tests/slices/test_slice4_aks_adapter.py`; 54/54 pass

### Slice 4b – Azure Activity Log adapter ✅
- [x] Implemented `AzureActivityAdapter.get_recent_changes` with `LogsQueryClient` + `ClientSecretCredential`
- [x] `environment` optional param added (interface parity); `${AZURE_*}` placeholders expanded from env vars
- [x] Client built once in `__init__`; empty/invalid credentials log a warning and return `[]`
- [x] Added `workspace_id` field to `config/integrations/azure_activity.yaml`
- [x] `AzureActivityToolset` schema updated to expose `environment` parameter
- [x] 9 new Slice 4b tests in `tests/slices/test_slice4b_azure_activity_adapter.py`; 63/63 pass

### Slice 5 – Knowledge layer injection ✅
- [x] Created `corvin/investigation/prompt_builder.py` (`PromptBuilder` class: loads site knowledge, matches catalog-driven runbooks, appends learnings)
- [x] `PromptBuilder` injected into `InvestigationEngine` as optional constructor param; `build(request)` called before RCA stub
- [x] Runbook matching now reads `knowledge/runbooks/catalog.json` and forwards raw alert rule/title metadata from Azure alert payloads
- [x] Runbook section includes precedence note; empty sections skipped cleanly
- [x] 14 Slice 5 tests in `tests/slices/test_slice5_knowledge_injection.py`; 77/77 pass

### Slice 6 – Investigation engine + LLM ✅
- [x] Wired `RCAGenerator.generate` to LiteLLM using the configured primary model, with one retry on `fallback_model`
- [x] RCA uses deterministic messages: system prompt from `PromptBuilder`, user payload with serialized request/evidence and explicit `RCAOutput` JSON instructions
- [x] Enforced `require_evidence_before_rca`: structured-but-empty evidence returns deterministic low-confidence RCA without calling LiteLLM
- [x] Wired `FixStrategyGenerator.generate` to LiteLLM using serialized request + RCA context and `FixStrategyOutput` JSON instructions
- [x] Enforced `fix_strategy_max_actions` and V1 `review_only` policy (`requires_approval = true` for all actions)
- [x] `InvestigationEngine.run()` now passes the built system prompt into RCA generation
- [x] Added 7 Slice 6 tests in `tests/slices/test_slice6_llm_generation.py`; 84/84 pass
- [x] **Review-fix:** Both generators now read `LITELLM_ENDPOINT` / `LITELLM_API_KEY` from environment and forward them as `api_base` / `api_key` to `litellm.completion`
- [x] **Review-fix:** Both generators now set `response_format` with `json_schema` type and the relevant Pydantic schema so the model is constrained to the output shape
- [x] **Review-fix:** Both generators now handle the `.parsed` structured-output path in addition to the text JSON path
- [x] **Review-fix:** 6 additional tests cover proxy forwarding, structured-output mode, and parsed-path handling; 90/90 pass

### Slice 7 – RCA and fix strategy contract validation ✅
- [x] 21 focused contract-validation tests in `tests/slices/test_slice7_contract_validation.py`
- [x] RCAOutput: valid-payload acceptance, enum preservation, auto-populated timestamps, contributing_factors and evidence_references defaults
- [x] RCAOutput: missing summary / root_cause / request_id rejected; invalid confidence value rejected
- [x] FixStrategyOutput: valid-payload acceptance with FixAction, empty actions list, auto-populated timestamp
- [x] FixAction: requires_approval defaults True; can be set False; invalid risk_level rejected; missing title rejected
- [x] FixStrategyOutput: missing summary / justification rejected
- [x] Generator-level: RCAGenerator surfaces ValidationError on malformed LiteLLM response (not swallowed)
- [x] Generator-level: FixStrategyGenerator surfaces ValidationError on malformed LiteLLM response (not swallowed)
- [x] No production behavior changed; slice is contract-validation coverage only; 111/111 pass

### Slice 8 – Postgres persistence ✅
- [x] Added `JSONB_COMPAT = JSONB().with_variant(JSON(), "sqlite")` to `models.py`; all JSONB columns switched to `JSONB_COMPAT` (SQLite in-memory for tests, JSONB on Postgres)
- [x] Added `EvidenceBundleRow` ORM model with `request_id` PK+FK and 5 JSONB list/dict fields + `collected_at`; bidirectional relationship on `InvestigationRequestRow.evidence`
- [x] Created `alembic/versions/0002_add_evidence_bundle_table.py` (down_revision 0001); creates `evidence_bundles` table; additive only
- [x] Created `corvin/storage/repository.py`: `InvestigationRepository` with injectable `session_factory`, `save_investigation_result`, `get_investigation_result`, `_upsert_by_request_id` helper; module-level convenience functions
- [x] `save` uses `session.merge()` for string-PK rows (request, evidence) and query-then-upsert for auto-increment-PK rows (rca, fix_strategy)
- [x] `get` reconstructs all four Pydantic contracts from ORM rows via `model_validate`
- [x] 12 Slice 8 tests in `tests/slices/test_slice8_persistence.py` (SQLite in-memory, no real Postgres required); 123/123 pass

### Slice 9 – REST API and CLI flows ✅
- [x] `apps/api/routes/investigations.py`: added `get_engine()` and `get_repository()` dependency providers (overridable in tests)
- [x] `POST /investigations/` now runs `InvestigationEngine.run()`, persists via `InvestigationRepository`, returns real `request_id` and `status="completed"`
- [x] `GET /investigations/{request_id}` loads full `InvestigationResult` from repository; returns HTTP 404 if not found
- [x] `apps/cli/main.py` `investigate` command updated: POST → extract `request_id` → GET → print `request_id`, `rca.summary`, `rca.confidence`, `fix.summary`; graceful handling of `ConnectError` and `HTTPStatusError`
- [x] Trigger routes untouched (Slice 9 scope is manual API + CLI only)
- [x] 12 Slice 9 tests in `tests/slices/test_slice9_api_cli.py` using `TestClient` + `dependency_overrides` for routes and mocked `httpx` for CLI; 143/143 pass

### Slice 10 – Web app and Teams ✅
- [x] `corvin/storage/repository.py`: added `list_investigations()` — queries only `investigation_requests`, returns lightweight summary dicts ordered newest-first
- [x] `apps/api/routes/investigations.py`: added `GET /` list endpoint; added `get_teams_adapter()` injectable dependency; `POST /` now calls `teams.send_result(result)` after persistence; Teams failure is non-fatal (caught, logged, response still 200)
- [x] `corvin/delivery/teams_adapter.py`: implemented `send_result()` — builds an Adaptive Card envelope (type=message + adaptive card attachment) with service/environment/confidence FactSet, RCA summary, fix strategy summary, and actions list; POSTs via `httpx`; raises `ValueError` on missing/unresolved webhook URL; no-ops when `enabled: false`
- [x] `apps/web/src/api/client.ts`: added `InvestigationSummary` and `InvestigationResult` TypeScript interfaces; typed `fetchInvestigations` to return `InvestigationSummary[]`; added `fetchInvestigation(id)` function
- [x] `apps/web/src/pages/InvestigationsPage.tsx`: replaced raw JSON dump with a proper investigation table (service, environment, trigger, completed time, link to detail page) and a Start Investigation form (POST → navigate to detail page on success)
- [x] 12 Slice 10 tests in `tests/slices/test_slice10_web_teams.py`: list endpoint (empty/populated/required fields/trigger_source/growth), TeamsAdapter (card structure, service+RCA in body, disabled no-call, missing URL, unresolved placeholder), route integration (spy verifies send_result called, Teams failure does not break route); 155/155 pass

## V1.5 Build Tasks – Real Cloud Integration Validation

### Integrations wired and validated
- [x] Azure OpenAI (`azure/gpt-4.1-mini`) – `json_object` mode, real completions working
- [x] Azure Postgres (`synaptic-postgres-db.postgres.database.azure.com`) – Alembic migrations applied, save+retrieve confirmed
- [x] Log Analytics APIM workspace (`LogAnalytics-APIM-DV01`) – 66 real `ApiManagementGatewayLogs` rows
- [x] AKS adapter (`azaustaekub14470dv0101`) – kubeconfig local, pod context from `chad` namespace, namespace passthrough bug fixed
- [x] ContainerLogsAdapter – `ContainerLog` (200 rows), `KubePodInventory` (7 rows), `KubeEvents` (12 rows) from CHAD LA workspace
- [x] `knowledge/site.md` – populated with real infra: cluster, services, namespaces, APIM, both workspaces, known issues
- [x] End-to-end investigation – `partnerapis / chad` → HIGH confidence RCA produced from real evidence

### Blocked / deferred to V2
- [ ] Elastic – blocked by org SSO; replaced by ContainerLogsAdapter for V1.5
- [ ] Azure Activity Log – Diagnostic Setting not configured; portal step needed (send Activity to `LogAnalytics-APIM-DV01`)

## V1.5 Exit Criteria
- [x] All core adapters connected to real Azure cloud services
- [x] End-to-end CLI investigation with real evidence produces a meaningful RCA
- [x] No mocks in the happy path

---

## V2 Build Tasks

### V2 Slice 1 – ApprovalStatus model + DB columns ✅
- [x] Added `ApprovalStatus` enum (`pending` / `approved` / `rejected` / `executed`) to `corvin/core/contracts.py`
- [x] Added `approval_status: ApprovalStatus = ApprovalStatus.PENDING` field to `InvestigationRequest`
- [x] Added `lookback_minutes: int` field to `InvestigationRequest` with `@model_validator` auto-set (15 min for `AZURE_ALERT`, 60 min for manual triggers)
- [x] Added `approval_status` and `lookback_minutes` columns to `InvestigationRequestRow` ORM model (`corvin/storage/models.py`)
- [x] Created Alembic migration `05ac79937721_v2_slice_1_add_approval_status_lookback_.py` with `server_default` to handle existing rows without NOT NULL violations
- [x] Applied migration to real Azure Postgres; migration head confirmed at `05ac79937721`
- [x] Added `ConfigDict(extra="forbid")` to `RCAOutput`, `FixAction`, `FixStrategyOutput` for JSON schema generation
- [x] 4 V2 Slice 1 tests in `tests/slices/test_slice_v2_s1_approval_model.py`; 159/159 pass

### V2 Slice 3 – Teams Adaptive Card with Approve / Reject buttons ✅
- [x] Updated `corvin/delivery/teams_adapter.py` — `_build_card` now reads `web_base_url` from config (env: `CORVIN_WEB_BASE_URL`; fallback: `http://localhost:5173`) and injects an `actions` array into the Adaptive Card
- [x] Two `Action.OpenUrl` buttons: **✅ Approve** (`style: positive`) and **❌ Reject** (`style: destructive`) — URLs point to `{web_base_url}/investigations/{request_id}?action=approve|reject`
- [x] Added a `Warning`-coloured review-reminder TextBlock above the action buttons
- [x] Trailing slash on `web_base_url` is stripped to prevent double-slash URLs
- [x] No bot needed for this slice — buttons open the Corvin web app in a browser (upgraded to `Action.Execute` Universal Actions in Slice 5 when the bot exists)
- [x] Updated `config/integrations/teams.yaml` — added `web_base_url: "${CORVIN_WEB_BASE_URL}"` setting
- [x] Updated `.env.example` — added `CORVIN_WEB_BASE_URL=http://localhost:5173`
- [x] Updated `apps/web/src/api/client.ts` — added `approveInvestigation()`, `rejectInvestigation()` API functions; added `ApprovalResponse` interface; added `approval_status` to `InvestigationResult.request` TypeScript type
- [x] Rewrote `apps/web/src/pages/InvestigationDetailPage.tsx` — full Approval section with status badge, Approve/Reject buttons, 2-step confirmation dialog, `?action=approve|reject` URL param support (Teams card button → auto-confirm prompt), success/error feedback, query invalidation after action
- [x] 19 V2 Slice 3 tests in `tests/slices/test_slice_v2_s3_teams_approval_card.py`; 194/194 pass
- [x] Added `get_approval_status(request_id)` and `update_approval_status(request_id, new_status)` to `InvestigationRepository`
- [x] `update_approval_status` commits inside its own session; returns updated row or `None` if ID not found
- [x] Added `POST /investigations/{request_id}/approve` route — 404 if not found, 409 if already `executed`, else transitions to `approved`
- [x] Added `POST /investigations/{request_id}/reject` route — 404 if not found, 409 if already `executed`, else transitions to `rejected`
- [x] Gate rule enforced at route level: no execution path exists without `ApprovalStatus.APPROVED`
- [x] Added `ApprovalResponse` Pydantic model (`request_id`, `approval_status`, `message`) as route response model
- [x] Fixed `_sqlite_session_factory` in test helpers to use `StaticPool` so TestClient thread shares the same in-memory DB
- [x] Fixed `test_evidence_adapters.py` — `ClientSecretCredential` patches replaced with `DefaultAzureCredential` (V1.5 adapter migration)
- [x] Fixed `enrichment_service.py` — `get_pod_context` now passes `environment=request.environment` (was missing positional arg)
- [x] 16 V2 Slice 2 tests in `tests/slices/test_slice_v2_s2_approval_api.py`; 175/175 pass

## V1 Exit Criteria
- [ ] CLI, API, web app, and Teams can all start an investigation
- [ ] Azure alerts auto-trigger the flow
- [ ] Structured RCA and fix strategy produced and persisted
- [ ] Key slices have isolated tests

## Build Tasks (Pack – historical)

- [x] Finalize pack structure
- [x] Create export progress tracker
- [x] Write workspace instructions
- [x] Write scoped instructions
- [x] Write reusable prompts
- [x] Write shared context docs
- [x] Write V1 plan docs
- [x] Write V2 plan docs
- [x] Write V3 plan docs
- [x] Write config blueprints
- [x] Review pack consistency
- [x] Prepare exportable bundle

## Session Log

| Session | Date | Item | Notes |
|---------|------|------|-------|
| 1 | 2026-04-04 | Pack structure | Created exportable folder layout for `.github`, shared docs, version docs, and config blueprints |
| 1 | 2026-04-04 | Root files | Added the export pack README and the pack progress tracker |
| 1 | 2026-04-04 | Instruction layer | Added the workspace instruction file and five scoped instruction files |
| 1 | 2026-04-04 | Prompt layer | Added reusable prompts for next slice, adapter work, capability delivery, readiness review, and slice-level testing |
| 1 | 2026-04-04 | Shared docs part 1 | Added product overview, target stack, architecture, trigger matrix, workflow, and configurability docs |
| 1 | 2026-04-04 | Shared docs part 2 | Added evidence, surfaces, output contracts, testing, repo structure, and open-decision docs |
| 1 | 2026-04-04 | Version docs | Added V1, V2, and V3 scope documents plus build sequencing and exit criteria |
| 1 | 2026-04-04 | Config blueprints | Added configuration layout, integration files, tool and policy blueprints, and environment strategy docs |
| 1 | 2026-04-04 | Consistency pass | Checked the pack for version and scope mismatches, then corrected the remaining Teams surface inconsistency |
| 1 | 2026-04-04 | Export bundle | Added `BUNDLE_MANIFEST.md` and completed the exportable Corvin context pack |
| 1 | 2026-04-04 | Stack clarification | Added explicit LiteLLM, custom-orchestration, and future LangGraph guidance to the shared docs |
| 2 | 2026-04-04 | V1 scaffold | Created full V1 repository scaffold: corvin, apps (api/cli/web), config, tests; 26/26 tests pass |
| 2 | 2026-04-04 | GAP fixes | Resolved GAP-1 through GAP-6: storage+alembic, Azure Activity adapter, knowledge layer, web detail pages; 30/30 tests pass |
| 2 | 2026-04-04 | GAP-7 | Toolset registry: base, registry, 6 stubs, catalog.json, toolsets.yaml; 30/30 tests pass |
| 3 | 2026-04-04 | Slice 2b | Wired ElasticAdapter (get_logs + get_metrics), updated ElasticToolset schemas, 7 new tests; 37/37 pass |
| 3 | 2026-04-04 | Slice 3 | Wired LogAnalyticsAdapter (get_apim_logs), updated LogAnalyticsToolset schemas, 8 new tests, added azure-identity dep; 45/45 pass |
| 3 | 2026-04-04 | Slice 4 | Wired AKSAdapter (get_pod_context), updated AKSToolset schemas, 9 new tests, added kubernetes dep; 54/54 pass |
| 3 | 2026-04-04 | Slice 4b | Wired AzureActivityAdapter (get_recent_changes), updated toolset schema, added workspace_id to yaml, 9 new tests; 63/63 pass |
| 4 | 2026-04-04 | Slice 5 | Created PromptBuilder, fixed catalog-driven runbook matching and raw alert-rule forwarding, wired into InvestigationEngine, 14 Slice 5 tests; 77/77 pass |
| 5 | 2026-04-04 | Slice 6 | Wired RCA and fix strategy generation to LiteLLM, enforced no-evidence and review-only policies, passed system prompt into RCA, added 7 Slice 6 tests; 84/84 pass |
| 5 | 2026-04-04 | Slice 6 review-fix | Added proxy kwargs (LITELLM_ENDPOINT/API_KEY), json_schema structured output mode, parsed-response path handling; 6 more tests; 90/90 pass |
| 6 | 2026-04-04 | Slice 7 | Created test_slice7_contract_validation.py with 21 contract-validation tests for RCAOutput, FixStrategyOutput, FixAction, and generator malformed-response handling; 111/111 pass |
| 7 | 2026-04-04 | Slice 8 | Added JSONB_COMPAT, EvidenceBundleRow ORM model, 0002 Alembic migration, InvestigationRepository (save+get+upsert helper), 12 SQLite-backed persistence tests; 123/123 pass |
| 7 | 2026-04-04 | Slice 8 findings | Fixed completed_at data loss (0003 migration, _as_utc normalisation, round-trip tests); enforced request-id invariant in save (ValueError + 5 new tests); 131/131 pass |
| 8 | 2026-04-04 | Slice 9 | Wired POST /investigations/ and GET /investigations/{id} with injectable engine+repo deps; updated CLI to POST then GET and print RCA+fix fields; 12 API/CLI tests; 143/143 pass |
| 9 | 2026-04-04 | Slice 10 | Added GET /investigations/ list endpoint; implemented TeamsAdapter Adaptive Card delivery with injectable dep and non-fatal failure handling; wired web list page with real table + start investigation form; typed API client; 12 new tests; 155/155 pass |
| 10 | 2026-04-04 | Post-V1 CLI polish | Replaced one-shot Typer CLI with interactive rich REPL (prompt_toolkit + pyfiglet); fixed banner rendering (no Panel, left-aligned, highlight=False); Ctrl+C cancels command not shell; `clear` uses os.system("cls"); CLI tests rewritten to call functions directly |
| 10 | 2026-04-04 | Setup guides | Created setup/ folder with 4 Azure environment setup guides (Azure OpenAI, Log Analytics, Elastic, .env template) |
| 10 | 2026-04-04 | Corvin → Corvin rename | Renamed mgplatform/ → corvin/, updated pyproject.toml, API title, CLI banner and prompt; deleted ghost mgplatform/ folder; 155/155 pass confirmed |
| 11 | 2026-05-xx | V1.5 – Azure OpenAI wired | LiteLLM Azure route (`azure/gpt-4.1-mini`) connected to `australiaeast` endpoint; API version `2025-01-01-preview`; `json_object` response mode |
| 11 | 2026-05-xx | V1.5 – Postgres wired | `synaptic-postgres-db.postgres.database.azure.com` live; all 5 tables migrated via Alembic; Azure CLI credential active |
| 11 | 2026-05-xx | V1.5 – Log Analytics APIM wired | `LogAnalytics-APIM-DV01` workspace; 66 real `ApiManagementGatewayLogs` rows confirmed via smoke test |
| 11 | 2026-05-xx | V1.5 – AKS adapter wired | `azaustaekub14470dv0101` cluster; kubeconfig local; 7 pods in `chad` namespace; AKS namespace passthrough bug fixed |
| 11 | 2026-05-xx | V1.5 – ContainerLogsAdapter created | New adapter querying `LogAnalytics-AUCHAD-DV01`; `ContainerLog` 200 rows, `KubePodInventory` 7 rows, `KubeEvents` 12 rows; replaces Elastic (org SSO blocked) |
| 11 | 2026-05-xx | V1.5 – knowledge/site.md populated | Real infra facts: AKS cluster, namespaces, services table, APIM, both LA workspaces, known issues |
| 11 | 2026-05-xx | V1.5 – End-to-end validated | `partnerapis / chad` investigation: HIGH confidence RCA produced with real evidence; startup probe HTTP 500 failures identified as root cause; HPA metric issue correctly diagnosed |
| 12 | 2026-05-xx | V2 Slice 1 – ApprovalStatus + lookback | Added ApprovalStatus enum, approval_status + lookback_minutes to contracts + ORM models; Alembic migration with server_default applied to real Postgres; 4 new tests; 159/159 pass |
| 12 | 2026-05-xx | V2 Slice 2 – Approve/Reject routes | Added get/update approval_status to repository; POST /approve and /reject routes with 404/409 guards; gate rule enforced; StaticPool fix for SQLite TestClient threading; fixed 3 legacy test regressions (ClientSecretCredential patches, missing environment arg in enrichment_service); 16 new tests; 175/175 pass |
| 12 | 2026-04-26 | V2 Slice 3 – Teams Adaptive Card buttons | Added Action.OpenUrl Approve/Reject buttons to Teams card (web_base_url config, trailing-slash safe, fallback localhost:5173); full Approval UI in React detail page (status badge, confirm dialog, ?action= param support, query invalidation); updated api/client.ts with approval fns + TypeScript types; 19 new tests; 194/194 pass |

## Resume Notes

If work stops mid-way:

1. Read this file first.
2. Find the first unchecked slice in the V1 Build Tasks section above.
3. Read `docs/copilot-context/versions/v1/02_build_sequence_and_exit_criteria.md` for slice ordering.
4. Update the task list and session log after each major file batch.

### Package naming note
The Python package for the control-plane logic is named `corvin/` (not `platform/`)
to avoid shadowing the Python standard library `platform` module.
The folder structure otherwise matches the repo blueprint in `docs/copilot-context/shared/11_repo_structure_blueprint.md`.

### Project rename note (post-V1)
The project was renamed from **Corvin** to **Corvin**:
- `mgplatform/` → `corvin/` (all imports updated to `corvin.*`)
- `pyproject.toml`: `name = "corvin"`, entry point `corvin = "apps.cli.main:app"`
- `apps/api/main.py`: API title updated to "Corvin API"
- `apps/cli/main.py`: banner updated to `CORVIN`; prompt updated to `corvin›`
- Ghost `mgplatform/` folder confirmed deleted
- Install sequence: `pip install hatchling` first, then `pip install -e .` (corp proxy constraint)
- **All 155 tests pass after rename** (verified 2026-04-04)

## 2026-05-13 - RCA PDF Export + Email Delivery Slice

- Added backend RCA PDF generation via `corvin/delivery/rca_pdf.py` (structured report with RCA, evidence, and fix strategy sections).
- Added SMTP email adapter via `corvin/delivery/email_adapter.py` and config in `config/integrations/email.yaml`.
- Added non-fatal RCA email delivery helper via `corvin/delivery/rca_notification.py`.
- Wired auto-email dispatch after RCA generation in:
  - `apps/api/routes/investigations.py` (manual API investigations)
  - `apps/api/routes/triggers.py` (Azure alert + simulator background investigations)
  - `apps/teams/bot.py` (Teams-initiated investigations)
- Added API endpoints:
  - `GET /investigations/{request_id}/rca.pdf` for PDF export
  - `POST /investigations/{request_id}/rca/email` for on-demand email send
- Added UI controls in `apps/web/src/components/investigation/RcaSection.tsx`:
  - `↓ PDF` export button
  - `✉ Send Mail` action button with success/error inline feedback
- Added RCA client helpers in `apps/web/src/api/client.ts` for export and email actions.
- Updated `.env.example` with SMTP/email placeholders.
- Validation:
  - `npm run build` (web) passes
  - `pytest tests/slices/test_slice10_web_teams.py -q` passes (`12 passed`)